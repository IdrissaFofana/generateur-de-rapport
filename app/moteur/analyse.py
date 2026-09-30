"""Consolidation des données d'un client pour un mois donné :
indicateurs, niveau de risque, points de vigilance et plan d'action."""
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from .outils import bornes_mois, date_ksc, fmt_date, fmt_pct, pluriel

LIBELLES_ANOMALIES = {
    "ksn": "Serveurs KSN (cloud Kaspersky) inaccessibles",
    "deconnecte": "Pas de connexion au serveur d'administration depuis longtemps",
    "non_administre": "Appareil plus administré (agent hors gestion)",
    "analyse_ancienne": "Analyse antimalware non exécutée depuis longtemps",
    "bases_depassees": "Bases antivirus dépassées",
    "protection_desactivee": "Protection désactivée",
    "non_installe": "Application de sécurité non installée",
    "redemarrage": "Redémarrage requis",
    "licence": "Problème de licence",
    "autre": "Autre état signalé par l'application",
}
IMPACT_ANOMALIES = {
    "ksn": "Élevé", "deconnecte": "Élevé", "non_administre": "Très élevé",
    "analyse_ancienne": "Modéré", "bases_depassees": "Élevé",
    "protection_desactivee": "Très élevé", "non_installe": "Très élevé",
    "redemarrage": "Faible", "licence": "Élevé", "autre": "Modéré",
}
OS_FIN_SUPPORT = {
    "Windows 7": date(2020, 1, 14), "Windows 8": date(2023, 1, 10),
    "Windows 10": date(2025, 10, 14), "Windows Server 2008": date(2020, 1, 14),
    "Windows Server 2012": date(2023, 10, 10), "Windows Server 2016": date(2027, 1, 12),
}
MOTS_NEUTRALISE = ("bloqué", "empêché", "supprimé", "désinfecté", "quarantaine", "interdit")
# Un hebdo MDR couvre une semaine du lundi au lundi et paraît quelques jours après
DELAI_PUBLICATION_HEBDO = 3


def hebdo_disponible_le(jour):
    """Date à partir de laquelle l'hebdo couvrant ce jour peut avoir été publié."""
    return jour + timedelta(days=7 - jour.weekday() + DELAI_PUBLICATION_HEBDO)


# --------------------------------------------------------------------------- #
# MDR (rapports hebdomadaires)
# --------------------------------------------------------------------------- #
def analyser_mdr(hebdos, tenants, debut, fin, aujourd_hui=None):
    jours, trouve = {}, False
    for h in hebdos:  # les plus récents écrasent les plus anciens
        for tenant, serie in h["postes"].items():
            if tenant in tenants:
                trouve = trouve or bool(serie)
                for j, n in serie.items():
                    if debut <= j < fin:
                        jours[j] = n
    tous = [debut + timedelta(d) for d in range((fin - debut).days)]
    manquants = [j for j in tous if j not in jours]
    # Jours dont l'hebdo ne peut pas encore exister (mois en cours) : attendus, pas manquants
    aujourd_hui = aujourd_hui or date.today()
    a_venir = [j for j in manquants if hebdo_disponible_le(j) > aujourd_hui]

    incidents = {}
    for h in hebdos:
        for inc in h["incidents"]:
            if inc["tenant"] not in tenants:
                continue
            cree = _date_incident(inc["cree"])
            dans_mois = (debut <= cree < fin) if cree else (h["debut"] < fin and h["fin"] > debut)
            if dans_mois:
                incidents[inc["numero"]] = inc  # dernière version connue

    valeurs = [jours[j] for j in sorted(jours)]
    ouvres = [jours[j] for j in sorted(jours) if j.weekday() < 5]
    semaines = [{"debut": h["debut"], "fin": h["fin"], "fichier": h["fichier"]}
                for h in hebdos if h["debut"] < fin and h["fin"] > debut]
    return {
        "tenant_trouve": trouve,
        "jours": sorted(jours.items()),
        "jours_manquants": manquants,
        "jours_a_venir": a_venir,
        "moyenne": sum(valeurs) / len(valeurs) if valeurs else 0,
        "moyenne_ouvres": sum(ouvres) / len(ouvres) if ouvres else 0,
        "max": max(valeurs) if valeurs else 0,
        "min": min(valeurs) if valeurs else 0,
        "incidents": list(incidents.values()),
        "semaines": semaines,
    }


def _date_incident(texte):
    from .outils import date_mdr
    d = date_mdr(texte) or date_ksc(texte)
    if d is None:
        try:
            d = datetime.fromisoformat(texte)
        except (TypeError, ValueError):
            return None
    return d.date()


# --------------------------------------------------------------------------- #
# État de la protection
# --------------------------------------------------------------------------- #
def analyser_protection(p):
    genere = datetime.fromisoformat(p["genere_le"]).date() if p.get("genere_le") else None
    appareils = p["appareils"]
    total = p["nb_appareils"] or len(appareils)
    etats = Counter(a["etat"] for a in appareils)
    anomalies = Counter(x for a in appareils for x in a["anomalies"])
    par_anomalie = defaultdict(list)
    for a in appareils:
        for x in a["anomalies"]:
            par_anomalie[x].append(a["appareil"])

    hors_ligne = []
    for a in appareils:
        d = date_ksc(a["derniere_connexion"])
        if d and genere and (genere - d.date()).days >= 7:
            hors_ligne.append({**a, "jours": (genere - d.date()).days})
    hors_ligne.sort(key=lambda a: -a["jours"])

    systemes = Counter(_os_court(a["os"]) for a in appareils)
    obsoletes = []
    for nom_os, n in systemes.items():
        for cle, fin_support in OS_FIN_SUPPORT.items():
            if nom_os.startswith(cle):
                obsoletes.append({"os": nom_os, "appareils": n, "fin_support": fin_support,
                                  "expire": genere is not None and fin_support <= genere})

    groupes = defaultdict(lambda: Counter())
    for a in appareils:
        groupes[a["groupe"] or "—"][a["etat"]] += 1

    return {
        "genere_le": genere,
        "total": total,
        "critique": etats.get("Critique", 0),
        "avertissement": etats.get("Avertissement", 0),
        "ok": max(total - etats.get("Critique", 0) - etats.get("Avertissement", 0), 0),
        "anomalies": anomalies,
        "par_anomalie": par_anomalie,
        "serveurs": [a for a in appareils if a["serveur"]],
        "serveurs_critiques": [a for a in appareils if a["serveur"] and a["etat"] == "Critique"],
        "hors_ligne": hors_ligne,
        "systemes": systemes,
        "os_obsoletes": obsoletes,
        "groupes": {g: dict(c) for g, c in sorted(groupes.items())},
        "appareils": appareils,
    }


def _os_court(os_):
    return os_.replace("Microsoft ", "").strip() or "Inconnu"


# --------------------------------------------------------------------------- #
# Menaces
# --------------------------------------------------------------------------- #
def analyser_menaces(m, debut, fin):
    detail_complet = m["detail_total"] is None or m["detail_affiche"] == m["detail_total"]
    detections = []
    for d in m["detections"]:
        quand = datetime.fromisoformat(d["detecte"]).date() if d["detecte"] else None
        if quand and debut <= quand < fin:
            detections.append({**d, "jour": quand})

    ksc_debut = date.fromisoformat(m["periode_debut"]) if m["periode_debut"] else debut
    ksc_fin = date.fromisoformat(m["periode_fin"]) if m["periode_fin"] else fin
    couvert_debut, couvert_fin = max(debut, ksc_debut), min(fin - timedelta(1), ksc_fin)

    def neutralisee(d):
        texte = (d["evenement"] + " " + d["resultat"]).lower()
        return any(mot in texte for mot in MOTS_NEUTRALISE)

    categories = Counter(d["categorie"] for d in detections)
    objets = Counter(d["objet"] for d in detections)
    appareils = Counter(d["appareil"] for d in detections)
    utilisateurs = Counter(d["utilisateur"] for d in detections if d["utilisateur"])
    par_jour = Counter(d["jour"] for d in detections)
    non_neutralisees = [d for d in detections if not neutralisee(d)]
    cat_par_appareil = defaultdict(Counter)
    for d in detections:
        cat_par_appareil[d["appareil"]][d["categorie"]] += 1
    exemples = defaultdict(list)
    for s in sorted(m["synthese"], key=lambda s: -s["detections"]):
        if s["categorie"] not in ("Phishing",) and s["objet"] not in exemples[s["categorie"]]:
            exemples[s["categorie"]].append(s["objet"])
    # Le texte superposé du PDF peut brouiller certaines cellules : on ne garde que des valeurs propres
    phishing = sorted({x for x in (_domaine(d["objet"]) for d in detections if d["categorie"] == "Phishing")
                       if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", x)})
    exemples = {k: [o for o in v if " " not in o] for k, v in exemples.items()}

    return {
        "detail_complet": detail_complet,
        "couvert_debut": couvert_debut, "couvert_fin": couvert_fin,
        "detections": len(detections),
        "menaces_distinctes": len(objets),
        "appareils_touches": len(appareils),
        "utilisateurs_touches": len(utilisateurs),
        "neutralisees": len(detections) - len(non_neutralisees),
        "non_neutralisees": non_neutralisees,
        "categories": categories,
        "exemples": {k: v[:3] for k, v in exemples.items()},
        "top_appareils": [(a, n, cat_par_appareil[a].most_common(1)[0][0]) for a, n in appareils.most_common(10)],
        "top_utilisateurs": utilisateurs.most_common(5),
        "par_jour": par_jour,
        "domaines_phishing": phishing,
        "evenements": Counter(d["evenement"] for d in detections),
    }


def _domaine(url):
    u = url.split("://", 1)[-1]
    return u.split("/", 1)[0].split("?", 1)[0]


# --------------------------------------------------------------------------- #
# Vulnérabilités
# --------------------------------------------------------------------------- #
def analyser_vulnerabilites(v):
    # Une même vulnérabilité (KLA) peut toucher plusieurs applications : une ligne par couple.
    # KSC laisse parfois l'application vide : on la retrouve dans le détail si possible.
    appli_detail = defaultdict(set)
    for d in v["detail"]:
        if d["application"]:
            appli_detail[d["kla"]].add(d["application"])
    lignes = {}
    for s in v["synthese"]:
        s = dict(s)
        if not s["application"]:
            connues = appli_detail[s["kla"]] - {x["application"] for x in v["synthese"] if x["kla"] == s["kla"]}
            s["application"] = sorted(connues)[0] if len(connues) == 1 else "Non précisée par KSC (système)"
        lignes.setdefault((s["kla"], s["application"]), s)
    vulns = list(lignes.values())
    distinctes = {s["kla"]: s for s in vulns}
    gravites = Counter(s["gravite"] for s in distinctes.values())

    applis = defaultdict(lambda: {"total": 0, "critiques": 0, "elevees": 0, "appareils": 0,
                                  "editeur": "", "versions": set()})
    for s in vulns:
        a = applis[s["application"]]
        a["total"] += 1
        a["critiques"] += s["gravite"] == "Critique"
        a["elevees"] += s["gravite"] == "Élevé"
        a["appareils"] = max(a["appareils"], s["appareils"])
        a["editeur"] = s["editeur"]
    for d in v["detail"]:
        if d["application"] in applis and d["version"]:
            applis[d["application"]]["versions"].add(d["version"])
    classement = sorted(applis.items(), key=lambda x: (-x[1]["critiques"], -x[1]["total"]))
    correctifs = Counter(d["correctif"] for d in v["detail"])
    return {
        "total": len(distinctes),
        "critiques": gravites.get("Critique", 0),
        "elevees": gravites.get("Élevé", 0),
        "autres": len(distinctes) - gravites.get("Critique", 0) - gravites.get("Élevé", 0),
        "applications": classement,
        "correctif_disponible": fmt_pct(correctifs.get("Oui", 0), sum(correctifs.values())) if correctifs else None,
        "detail_tronque": v["detail_total"] is not None and v["detail_affiche"] != v["detail_total"],
        "detail_total": v["detail_total"],
    }


# --------------------------------------------------------------------------- #
# Synthèse : risque, vigilance, actions
# --------------------------------------------------------------------------- #
GRAVES = ("Cheval de Troie", "Backdoor", "Ver", "Exploit")


def _incidents_ouverts(mdr):
    return [i for i in mdr["incidents"] if i["statut"].lower() not in ("closed", "resolved", "fermé")]


def evaluer_risque(d):
    points, motifs = 0, []
    p, m, v, mdr = d["protection"], d["menaces"], d["vulnerabilites"], d["mdr"]
    if p:
        taux = p["critique"] / p["total"] if p["total"] else 0
        if taux > 0.5:
            points += 3; motifs.append(f"{fmt_pct(p['critique'], p['total'])} des appareils en état critique")
        elif taux > 0.2:
            points += 2; motifs.append(f"{fmt_pct(p['critique'], p['total'])} des appareils en état critique")
        elif taux > 0:
            points += 1
        sans = p["anomalies"].get("protection_desactivee", 0) + p["anomalies"].get("non_installe", 0)
        if sans:
            points += 2; motifs.append(f"{sans} {pluriel(sans, 'appareil')} sans protection active")
        if p["serveurs_critiques"]:
            n = len(p["serveurs_critiques"])
            points += 1; motifs.append(f"{n} {pluriel(n, 'serveur')} en état critique")
    if m:
        n = len(m["non_neutralisees"])
        if n:
            points += 2; motifs.append(f"{n} {pluriel(n, 'détection')} sans blocage confirmé par l'antivirus (à vérifier)")
        graves = sum(m["categories"].get(c, 0) for c in GRAVES)
        if graves:
            points += 1; motifs.append(f"{graves} {pluriel(graves, 'détection')} de logiciels malveillants (chevaux de Troie, backdoors…)")
    if v:
        if v["critiques"] >= 20:
            points += 3; motifs.append(f"{v['critiques']} vulnérabilités critiques non corrigées")
        elif v["critiques"]:
            points += 2; motifs.append(f"{v['critiques']} {pluriel(v['critiques'], 'vulnérabilité critique', 'vulnérabilités critiques')}")
    if mdr:  # uniquement pour les clients qui ont souscrit le MDR
        ouverts = _incidents_ouverts(mdr)
        if any(i["priorite"].lower() == "high" for i in ouverts):
            points += 3; motifs.append("incident MDR de priorité haute en cours")
        elif ouverts:
            points += 1; motifs.append(f"{len(ouverts)} incident(s) MDR en cours")
        if not mdr["tenant_trouve"] or mdr["max"] == 0:
            points += 2; motifs.append("aucun poste ne remonte de télémétrie au service MDR")

    niveau = "Critique" if points >= 8 else "Élevé" if points >= 5 else "Modéré" if points >= 2 else "Faible"
    return {"niveau": niveau, "points": points, "motifs": motifs, "partiel": bool(d["exports_manquants"])}


def construire_actions(d):
    """Plan d'action priorisé déduit des constats."""
    actions = []
    p, m, v, mdr, client = d["protection"], d["menaces"], d["vulnerabilites"], d["mdr"], d["client"]

    def ajouter(priorite, action, responsable, pourquoi):
        actions.append({"priorite": priorite, "action": action, "responsable": responsable, "pourquoi": pourquoi})

    if mdr:
        if not mdr["tenant_trouve"] or mdr["max"] == 0:
            ajouter("Urgente", "Vérifier le déploiement et la connectivité des agents MDR", "ESAY + " + client,
                    "Aucun poste ne transmet de télémétrie : le client n'est pas supervisé.")
        for inc in _incidents_ouverts(mdr):
            ajouter("Urgente", f"Traiter l'incident MDR n° {inc['numero']} ({inc['nom']})", "ESAY + " + client,
                    f"Incident de priorité {inc['priorite']} encore ouvert.")
    if p:
        a = p["anomalies"]
        if a.get("protection_desactivee"):
            n = a["protection_desactivee"]
            ajouter("Urgente", f"Réactiver la protection sur {n} {pluriel(n, 'appareil')}", "ESAY",
                    "Ces appareils sont sans défense et peuvent propager une infection.")
        if a.get("non_installe"):
            n = a["non_installe"]
            ajouter("Urgente", f"Installer Kaspersky Endpoint Security sur {n} {pluriel(n, 'appareil')}", "ESAY",
                    "Appareils totalement hors du périmètre de protection.")
        if a.get("ksn"):
            ajouter("Urgente", "Rétablir l'accès aux serveurs KSN (règles pare-feu / proxy vers les services Kaspersky)",
                    "ESAY + " + client,
                    f"{a['ksn']} appareils privés de la détection cloud en temps réel ; cause principale des états critiques.")
        if a.get("non_administre"):
            n = a["non_administre"]
            ajouter("Urgente", f"Réinstaller ou réaffecter l'agent d'administration sur {n} {pluriel(n, 'appareil')}", "ESAY",
                    "Ces appareils ne reçoivent plus les politiques ni les mises à jour.")
        if a.get("deconnecte"):
            n = a["deconnecte"]
            cible = "l'appareil qui ne communique" if n == 1 else f"les {n} appareils qui ne communiquent"
            ajouter("Haute", f"Identifier et reconnecter {cible} plus avec le serveur d'administration",
                    "ESAY + " + client, "Postes éteints, sortis du réseau ou agent défaillant : à confirmer avec le client.")
        if a.get("bases_depassees"):
            n = a["bases_depassees"]
            ajouter("Haute", f"Mettre à jour les bases antivirus sur {n} {pluriel(n, 'appareil')}", "ESAY",
                    "Des bases anciennes ne détectent pas les menaces récentes.")
        if a.get("analyse_ancienne"):
            n = a["analyse_ancienne"]
            ajouter("Haute", f"Lancer une analyse complète sur {n} {pluriel(n, 'appareil')} et planifier une analyse hebdomadaire automatique", "ESAY",
                    "Aucune analyse complète récente sur ces appareils.")
        for o in p["os_obsoletes"]:
            n = o["appareils"]
            cible = f"de l'appareil sous {o['os']}" if n == 1 else f"des {n} appareils sous {o['os']}"
            if o["expire"]:
                ajouter("Haute", f"Planifier la migration {cible}", client,
                        f"Système plus supporté par Microsoft depuis le {fmt_date(o['fin_support'])} : plus aucun correctif de sécurité.")
            elif (o["fin_support"] - (p["genere_le"] or date.today())).days < 180:
                ajouter("Normale", f"Anticiper le remplacement {cible}", client,
                        f"Fin du support Microsoft le {fmt_date(o['fin_support'])}.")
    if v:
        # Priorité aux applications dont les failles critiques touchent le plus d'appareils
        impact = sorted(v["applications"], key=lambda x: -(x[1]["critiques"] * x[1]["appareils"]))
        for appli, info in [x for x in impact if x[1]["critiques"]][:4]:
            n = info["appareils"]
            pourquoi = (f"{info['total']} {pluriel(info['total'], 'vulnérabilité')} dont {info['critiques']} "
                        f"{pluriel(info['critiques'], 'critique')}, jusqu'à {n} {pluriel(n, 'appareil')} {pluriel(n, 'concerné')}.")
            if "windows" in appli.lower() or "operating system" in appli.lower() or "système" in appli.lower():
                action = f"Appliquer les mises à jour de sécurité Microsoft (Windows Update) — {appli}"
            else:
                action = f"Mettre à jour {appli} vers la dernière version sur tous les postes"
            ajouter("Haute", action, "ESAY + " + client, pourquoi)
        if v["total"]:
            ajouter("Normale", "Mettre en place un processus de gestion des correctifs (patch management) mensuel", "ESAY + " + client,
                    "La majorité des failles provient de logiciels non mis à jour.")
    if m:
        if m["non_neutralisees"]:
            cibles = sorted({f"{x['appareil']} ({x['objet']})" for x in m["non_neutralisees"]})
            ajouter("Haute", "Vérifier les détections sans blocage confirmé : " + ", ".join(cibles[:3]), "ESAY",
                    "L'antivirus n'a pas remonté d'action (blocage, suppression) : confirmer qu'il ne s'agit pas d'un faux positif et que le poste est sain.")
        graves = [a for a, _, c in m["top_appareils"] if c in GRAVES]
        if graves:
            ajouter("Haute", "Réaliser une analyse approfondie des postes touchés par des chevaux de Troie : " + ", ".join(graves[:5]), "ESAY",
                    "S'assurer qu'aucun composant malveillant n'a persisté.")
        if m["categories"].get("Phishing"):
            ajouter("Normale", "Sensibiliser les utilisateurs au phishing", client,
                    f"{m['categories']['Phishing']} tentative(s) d'accès à des sites de phishing bloquée(s).")
        if m["categories"].get("Adware", 0) >= 50:
            poste = m["top_appareils"][0][0]
            ajouter("Normale", f"Nettoyer les navigateurs des postes générant de l'adware (notamment {poste})", "ESAY",
                    "Détections répétées : extension ou site publicitaire récurrent.")
    if mdr and p and mdr["max"] and p["total"] and mdr["max"] < 0.8 * p["total"]:
        ajouter("Haute", "Étendre la supervision MDR à l'ensemble du parc", "ESAY + " + client,
                f"{p['total']} appareils administrés mais au plus {mdr['max']} supervisés par le MDR sur le mois.")
    if d["suggestion_mdr"]:
        ajouter("Normale", "Étudier la mise en place du service Kaspersky MDR (détection et réponse managées 24h/24)",
                "ESAY + " + client, d["suggestion_mdr"])

    manquants = [nom for cle, nom in (("protection", "état de la protection"), ("menaces", "menaces"),
                                      ("vulnerabilites", "vulnérabilités")) if cle in d["exports_manquants"]]
    if manquants:
        ajouter("Normale", "Transmettre les exports mensuels Kaspersky Security Center : " + ", ".join(manquants),
                "ESAY + " + client, "Indispensables pour évaluer l'état du parc, les menaces bloquées et les failles à corriger.")

    ordre = {"Urgente": 0, "Haute": 1, "Normale": 2}
    return sorted(actions, key=lambda x: ordre[x["priorite"]])


def motif_suggestion_mdr(d):
    """Pour un client sans MDR : justification d'une proposition MDR, ou None."""
    p, m = d["protection"], d["menaces"]
    raisons = []
    if m and any(m["categories"].get(c) for c in GRAVES):
        raisons.append("des logiciels malveillants ont été détectés sur le parc")
    if m and m["non_neutralisees"]:
        raisons.append("certaines détections n'ont pas pu être confirmées comme bloquées")
    if p and p["total"] and p["critique"] / p["total"] > 0.2:
        raisons.append("une part importante du parc est en état critique")
    if not raisons:
        return None
    return ("Ce mois-ci, " + " et ".join(raisons) + ". Le service MDR ajoute une surveillance continue par des "
            "analystes SOC qui investiguent et répondent aux menaces avant qu'elles ne deviennent des incidents.")


def comparer(actuels, precedents):
    """Écart avec le mois précédent, uniquement sur les indicateurs présents les deux mois."""
    if not precedents:
        return {}
    return {k: actuels[k] - precedents[k] for k in actuels
            if isinstance(actuels.get(k), (int, float)) and isinstance(precedents.get(k), (int, float))}


def indicateurs_cles(d):
    p, m, v, mdr = d["protection"], d["menaces"], d["vulnerabilites"], d["mdr"]
    return {
        "postes_mdr_moyenne": round(mdr["moyenne_ouvres"] or mdr["moyenne"], 1) if mdr else None,
        "incidents_mdr": len(mdr["incidents"]) if mdr else None,
        "appareils_administres": p["total"] if p else None,
        "appareils_critiques": p["critique"] if p else None,
        "detections": m["detections"] if m else None,
        "appareils_touches": m["appareils_touches"] if m else None,
        "vulnerabilites": v["total"] if v else None,
        "vulnerabilites_critiques": v["critiques"] if v else None,
    }


def consolider(client, annee, mois, hebdos, exports, precedents=None):
    """client : {"nom", "tenants_mdr", "mdr": bool, "suggerer_mdr": bool}
    exports : {type: données lues par lecture_ksc}  ·  precedents : indicateurs du mois précédent."""
    debut, fin = bornes_mois(annee, mois)
    avertissements = []
    d = {"client": client["nom"], "annee": annee, "mois": mois, "debut": debut, "fin": fin,
         "fin_incluse": fin - timedelta(days=1), "avec_mdr": bool(client.get("mdr", True)),
         "mdr": None, "protection": None, "menaces": None, "vulnerabilites": None, "exports": {}}

    if d["avec_mdr"]:
        d["mdr"] = analyser_mdr(hebdos, set(client.get("tenants_mdr", [])), debut, fin)
        a_venir = set(d["mdr"]["jours_a_venir"])
        j = [x for x in d["mdr"]["jours_manquants"] if x not in a_venir]
        if j:
            avertissements.append(f"Données MDR manquantes pour {len(j)} jour(s) du mois "
                                  f"({fmt_date(j[0])} → {fmt_date(j[-1])}) : ajouter le(s) rapport(s) hebdomadaire(s) correspondant(s).")
        if a_venir:
            j = sorted(a_venir)
            avertissements.append(f"Données MDR du {fmt_date(j[0])} au {fmt_date(j[-1])} pas encore disponibles : "
                                  f"le rapport hebdomadaire couvrant ces jours paraîtra à partir du "
                                  f"{fmt_date(hebdo_disponible_le(j[-1]))}.")

    for typ, donnees in exports.items():
        genere = datetime.fromisoformat(donnees["genere_le"]).date() if donnees.get("genere_le") else None
        if genere and not (debut <= genere < fin + timedelta(days=20)):
            avertissements.append(f"Export « {donnees['fichier']} » ignoré : généré le {fmt_date(genere)}, hors de la période.")
            continue
        d["exports"][typ] = {"fichier": donnees["fichier"], "genere_le": genere}
        if typ == "protection":
            d["protection"] = analyser_protection(donnees)
        elif typ == "menaces":
            d["menaces"] = analyser_menaces(donnees, debut, fin)
            if not d["menaces"]["detail_complet"]:
                avertissements.append("Le détail de l'export des menaces est tronqué par KSC : les chiffres peuvent être sous-estimés.")
        elif typ == "vulnerabilites":
            d["vulnerabilites"] = analyser_vulnerabilites(donnees)
            if d["vulnerabilites"]["detail_tronque"]:
                avertissements.append(f"L'export des vulnérabilités limite le détail à 1 000 lignes sur "
                                      f"{d['vulnerabilites']['detail_total']} ; les totaux proviennent du récapitulatif complet.")

    d["exports_manquants"] = [t for t in ("protection", "menaces", "vulnerabilites") if d[t] is None]
    d["suggestion_mdr"] = motif_suggestion_mdr(d) if not d["avec_mdr"] and client.get("suggerer_mdr") else None
    d["risque"] = evaluer_risque(d)
    d["actions"] = construire_actions(d)
    d["indicateurs"] = indicateurs_cles(d)
    d["precedents"] = precedents
    d["evolution"] = comparer(d["indicateurs"], precedents)
    d["avertissements"] = avertissements
    return en_json(d)


def en_json(obj):
    """Convertit le résultat en structure JSON (dates ISO, compteurs triés par fréquence)."""
    if isinstance(obj, Counter):
        return {_cle(k): v for k, v in obj.most_common()}
    if isinstance(obj, dict):
        return {_cle(k): en_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [en_json(x) for x in obj]
    if isinstance(obj, set):
        return sorted(en_json(x) for x in obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _cle(k):
    return k.isoformat() if isinstance(k, (date, datetime)) else k

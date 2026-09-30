"""Statistiques du portefeuille (page Vue d'ensemble), à partir des rapports mensuels validés."""
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select

from . import config, parc
from .modeles import VALIDE, Alerte, Client, Rapport
from .moteur import parc as mparc
from .moteur.outils import bornes_mois, fmt_mois, mois_courant, mois_decale
from .services import INDICATEURS_SUIVIS, MOIS_COURTS

ORDRE_RISQUE = {"Critique": 0, "Élevé": 1, "Modéré": 2, "Faible": 3}
CLASSES_RISQUE = {"Critique": "critique", "Élevé": "eleve", "Modéré": "modere", "Faible": "faible"}
PROFILS = {"mdr-ksc": "MDR + KSC", "mdr": "MDR seul", "ksc": "KSC seul"}  # filtre → Client.profil
OUVERTES = ("À faire", "En cours")
ANCIENNETE_ALERTE = 2  # mois : au-delà, une action ouverte est signalée


def _rang(annee, mois):
    return annee * 12 + mois - 1


def dernier_mois_valide(db):
    """Mois le plus récent ayant au moins un rapport mensuel validé (sinon le mois traité par défaut)."""
    r = db.execute(select(Rapport.annee, Rapport.mois).where(Rapport.periodicite == "mensuel", Rapport.statut == VALIDE)
                   .order_by(Rapport.annee.desc(), Rapport.mois.desc()).limit(1)).first()
    return (r.annee, r.mois) if r else mois_courant()


def _valides(db, clients, annee, mois, nb_mois):
    """Dernière version validée de chaque (client, mois) de la fenêtre, sans les données volumineuses."""
    fin = _rang(annee, mois)
    lignes = db.execute(select(Rapport.id, Rapport.client_id, Rapport.annee, Rapport.mois, Rapport.version,
                               Rapport.indicateurs, Rapport.contenu["niveau_risque"].astext.label("niveau"),
                               Rapport.contenu["actions"].label("actions"), Rapport.contenu["suivi"].label("suivi"),
                               Rapport.donnees["menaces"]["categories"].label("categories"), Rapport.valide_le)
                        .where(Rapport.periodicite == "mensuel", Rapport.statut == VALIDE,
                               Rapport.client_id.in_([c.id for c in clients]),
                               Rapport.annee * 12 + Rapport.mois - 1 > fin - nb_mois,
                               Rapport.annee * 12 + Rapport.mois - 1 <= fin)
                        .order_by(Rapport.version)).all()
    return {(l.client_id, l.annee, l.mois): l for l in lignes}  # la dernière version l'emporte


def _somme(valeurs):
    connues = [v for v in valeurs if v is not None]
    return sum(connues) if connues else None


def _groupe_responsable(responsable, client):
    """ESAY, le client, ou partagée (« ESAY + HUDSON »)."""
    texte = (responsable or "").upper()
    prestataire = config.PRESTATAIRE["nom"].upper() in texte
    chez_client = client.nom.upper() in texte or "CLIENT" in texte
    if prestataire and chez_client:
        return "Partagée"
    return config.PRESTATAIRE["nom"] if prestataire else "Client"


def _actions(valides, clients, fenetre):
    """Actions du dernier mois : taux de réalisation, ouvertes par responsable, ancienneté des actions reportées.
    L'origine d'une action est le premier mois (dans la fenêtre) où elle apparaît dans un rapport validé."""
    annee, mois = fenetre[-1]
    bilan = {"nouvelles": 0, "suivies": Counter(), "par_responsable": Counter(), "anciennes": [], "ouvertes": 0}
    for c in clients:
        origines = {}
        for a, m in fenetre:
            l = valides.get((c.id, a, m))
            if l is None:
                continue
            for x in (l.suivi or []) + (l.actions or []):
                origines.setdefault(x["action"].strip().lower(), (a, m))
        l = valides.get((c.id, annee, mois))
        if l is None:
            continue
        bilan["nouvelles"] += len(l.actions or [])
        for x in l.suivi or []:
            bilan["suivies"][x.get("statut", "À faire")] += 1
        for x, reportee in [(x, True) for x in (l.suivi or [])] + [(x, False) for x in (l.actions or [])]:
            if x.get("statut", "À faire") not in OUVERTES:
                continue
            bilan["ouvertes"] += 1
            bilan["par_responsable"][_groupe_responsable(x.get("responsable"), c)] += 1
            oa, om = origines.get(x["action"].strip().lower(), (annee, mois))
            age = _rang(annee, mois) - _rang(oa, om)
            if reportee and age >= ANCIENNETE_ALERTE:
                bilan["anciennes"].append({"client": c, "action": x["action"], "responsable": x.get("responsable") or "—",
                                           "priorite": x.get("priorite", "—"), "statut": x.get("statut", "À faire"),
                                           "depuis": fmt_mois(oa, om), "age": age, "rapport_id": l.id})
    bilan["anciennes"].sort(key=lambda x: (-x["age"], {"Urgente": 0, "Haute": 1}.get(x["priorite"], 2), x["client"].nom))
    suivies = sum(bilan["suivies"].values())
    bilan["taux"] = round(100 * bilan["suivies"].get("Réalisée", 0) / suivies) if suivies else None
    return bilan


def _menaces_par_mois(valides, fenetre):
    """Détections par catégorie et par mois ; les 4 catégories principales de la période, une courbe chacune
    (échelles séparées : une catégorie dominante n'écrase pas les autres)."""
    par_mois = []
    total = Counter()
    for a, m in fenetre:
        cpt = Counter()
        presents = [l for (cid, aa, mm), l in valides.items() if (aa, mm) == (a, m)]
        for l in presents:
            cpt.update(l.categories or {})
        total.update(cpt)
        par_mois.append({"libelle": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}", "presents": bool(presents), "categories": cpt})
    principales = [cat for cat, _ in total.most_common(4)]
    series = [{"cle": cat, "libelle": cat} for cat in principales]
    points = [{"libelle": p["libelle"],
               "indicateurs": {cat: (p["categories"].get(cat, 0) if p["presents"] else None) for cat in principales}}
              for p in par_mois]
    return {"series": series, "points": points, "autres": sorted(set(total) - set(principales)),
            "mois_avec_donnees": sum(1 for p in par_mois if p["presents"])}


def _delais_du_mois(valides, clients, annee, mois):
    """Date de validation de chaque rapport du mois et écart avec l'engagement interne."""
    fin = bornes_mois(annee, mois)[1]
    lignes = []
    for c in clients:
        l = valides.get((c.id, annee, mois))
        if l and l.valide_le:
            jours = (l.valide_le.date() - fin).days
            lignes.append({"client": c, "rapport_id": l.id, "version": l.version, "valide_le": l.valide_le, "jours": jours,
                           "retard": jours > config.ENGAGEMENT_DELAI_JOURS})
        else:
            ecoules = (date.today() - fin).days
            lignes.append({"client": c, "rapport_id": None, "valide_le": None, "jours": ecoules if ecoules > 0 else None,
                           "retard": ecoules > config.ENGAGEMENT_DELAI_JOURS})
    return sorted(lignes, key=lambda x: (x["valide_le"] is not None, -(x["jours"] or 0)))


def statistiques(db, annee, mois, nb_mois=12, client_id=None, profil=None):
    tous = db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all()
    clients = [c for c in tous if (not client_id or c.id == client_id) and (not profil or c.profil == PROFILS.get(profil))]
    fenetre = [mois_decale(annee, mois, -k) for k in range(nb_mois - 1, -1, -1)]
    valides = _valides(db, clients, annee, mois, nb_mois)
    colonnes = [{"annee": a, "mois": m, "court": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}", "long": fmt_mois(a, m)} for a, m in fenetre]

    # Carte de chaleur clients × mois
    chaleur = [{"client": c, "cases": [valides.get((c.id, a, m)) for a, m in fenetre]} for c in clients]

    # Tendances du portefeuille (somme des clients validés chaque mois)
    tendances = []
    for a, m in fenetre:
        du_mois = [l for (cid, aa, mm), l in valides.items() if (aa, mm) == (a, m)]
        tendances.append({"libelle": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}", "nb": len(du_mois),
                          "indicateurs": {cle: _somme(l.indicateurs.get(cle) for l in du_mois) if du_mois else None
                                          for cle, _ in INDICATEURS_SUIVIS + [("incidents_mdr", ""), ("appareils_administres", "")]}})

    courant, precedent = tendances[-1], tendances[-2] if nb_mois > 1 else None

    def kpi(cle):
        v = courant["indicateurs"].get(cle)
        p = precedent["indicateurs"].get(cle) if precedent else None
        return {"valeur": v, "delta": (round(v - p, 1) if v is not None and p is not None else None)}

    indicateurs = {cle: kpi(cle) for cle in ("appareils_administres", "appareils_critiques", "vulnerabilites_critiques",
                                            "detections", "incidents_mdr")}

    # Rapports complets du mois sélectionné (données détaillées)
    ids_mois = [l.id for (cid, a, m), l in valides.items() if (a, m) == (annee, mois)]
    rapports_mois = db.scalars(select(Rapport).where(Rapport.id.in_(ids_mois))).all() if ids_mois else []
    par_client = {r.client_id: r for r in rapports_mois}

    classement, couverture, applis, categories = [], [], defaultdict(lambda: {"clients": set(), "total": 0, "critiques": 0}), Counter()
    for c in clients:
        r = par_client.get(c.id)
        if r is None:
            continue
        i, d = r.indicateurs or {}, r.donnees
        classement.append({"client": c, "rapport": r, "niveau": r.contenu.get("niveau_risque"),
                           "critiques": i.get("appareils_critiques"), "parc": i.get("appareils_administres"),
                           "vulns": i.get("vulnerabilites_critiques"), "detections": i.get("detections"),
                           "incidents": i.get("incidents_mdr")})
        if d.get("mdr") and d.get("protection"):
            couverture.append({"client": c, "mdr": d["mdr"]["max"], "parc": d["protection"]["total"],
                               "hors": max(d["protection"]["total"] - d["mdr"]["max"], 0)})
        for nom, info in (d.get("vulnerabilites") or {}).get("applications", []):
            applis[nom]["clients"].add(c.nom)
            applis[nom]["total"] += info["total"]
            applis[nom]["critiques"] += info["critiques"]
        categories.update((d.get("menaces") or {}).get("categories", {}))
    classement.sort(key=lambda x: (ORDRE_RISQUE.get(x["niveau"], 9), -(x["critiques"] or 0), -(x["vulns"] or 0)))
    maxi = {k: max([x[k] or 0 for x in classement] or [0]) or 1 for k in ("critiques", "vulns", "detections")}
    couverture.sort(key=lambda x: x["mdr"] / x["parc"] if x["parc"] else 1)
    communes = sorted(({"nom": n, **v, "clients": sorted(v["clients"])} for n, v in applis.items()),
                      key=lambda x: (-len(x["clients"]), -x["critiques"], -x["total"]))
    actions = _actions(valides, clients, fenetre)

    # Délai de production : jours entre la fin du mois et la validation
    delais = []
    for a, m in fenetre:
        fin = bornes_mois(a, m)[1]
        jours = [(l.valide_le.date() - fin).days for (cid, aa, mm), l in valides.items() if (aa, mm) == (a, m) and l.valide_le]
        delais.append({"libelle": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}",
                       "indicateurs": {"delai": round(sum(jours) / len(jours), 1) if jours else None}})

    # Fin de support (dernier export de protection de chaque client)
    systemes = defaultdict(lambda: {"clients": set(), "appareils": 0, "serveurs": 0})
    for c in clients:
        e = parc.dernier_export_protection(db, c.id)
        if not e:
            continue
        for a in e.donnees.get("appareils", []):
            nom = mparc.systeme_court(a["os"])
            systemes[nom]["clients"].add(c.nom)
            systemes[nom]["appareils"] += 1
            systemes[nom]["serveurs"] += 1 if a.get("serveur") else 0
    aujourd_hui = date.today()
    fin_support = []
    for nom, v in systemes.items():
        fin = mparc.fin_de_support(nom)
        statut, libelle = mparc.statut_support(fin, aujourd_hui)
        if statut in ("expire", "urgent", "a-planifier"):
            fin_support.append({"os": nom, **v, "clients": sorted(v["clients"]), "fin": fin, "statut": statut, "libelle": libelle})
    fin_support.sort(key=lambda x: x["fin"])

    requete_alertes = select(Alerte).where(Alerte.traitee.is_(False))
    if len(clients) < len(tous):  # vue filtrée : alertes des clients retenus seulement
        requete_alertes = requete_alertes.where(Alerte.client_id.in_([c.id for c in clients]))
    alertes = db.scalars(requete_alertes.order_by(Alerte.cree_le.desc()).limit(6)).all()
    contrats = [(k, e) for k, e in parc.contrats_avec_etat(db, clients, config.SEUIL_SOUS_UTILISATION)
                if e["echeance"][0] in ("expire", "proche", "a-prevoir") or e["statut"] in ("depassement", "sous-utilise")]

    return {"annee": annee, "mois": mois, "libelle": fmt_mois(annee, mois), "clients": clients, "tous": tous,
            "filtre": {"client": client_id, "profil": profil}, "filtree": len(clients) < len(tous), "colonnes": colonnes,
            "menaces_evolution": _menaces_par_mois(valides, fenetre), "delais_mois": _delais_du_mois(valides, clients, annee, mois),
            "engagement": config.ENGAGEMENT_DELAI_JOURS, "anciennete_alerte": ANCIENNETE_ALERTE,
            "chaleur": chaleur, "tendances": tendances, "indicateurs": indicateurs, "nb_valides": len(rapports_mois),
            "classement": classement, "maxi": maxi, "couverture": couverture, "communes": communes[:10],
            "categories": categories.most_common(8), "total_categories": sum(categories.values()),
            "actions": actions, "delais": delais, "fin_support": fin_support, "alertes": alertes, "contrats": contrats,
            "historique_disponible": sum(1 for t in tendances if t["nb"])}

"""Textes par défaut du rapport, déduits des données.

Ils constituent le « contenu » modifiable dans la plateforme avant génération :
les chiffres et tableaux viennent toujours des données, les textes de ce contenu.
Mise en forme légère : **gras**, paragraphes séparés par une ligne vide.
"""
from datetime import date

from .outils import fmt_date, fmt_nb, fmt_pct, pluriel

STATUTS_ACTION = ("À faire", "En cours", "Réalisée", "Abandonnée")


def _virgule(x):
    return str(round(x, 1)).replace(".", ",")


def synthese(d, prestataire):
    mdr, p, m, v = d["mdr"], d["protection"], d["menaces"], d["vulnerabilites"]
    if mdr and (p or m or v):
        outils = "la plateforme Kaspersky Managed Detection and Response (MDR) et la console Kaspersky Security Center (KSC)"
    elif mdr:
        outils = "la plateforme Kaspersky Managed Detection and Response (MDR)"
    else:
        outils = "la console Kaspersky Security Center (KSC)"
    texte = (f"Au cours de la période du **{fmt_date(date.fromisoformat(d['debut']))} au "
             f"{fmt_date(date.fromisoformat(d['fin_incluse']))}**, {prestataire} a assuré la supervision de sécurité "
             f"du système d'information de **{d['client']}** à travers {outils}. ")
    if mdr:
        if mdr["max"]:
            texte += (f"En moyenne, **{_virgule(mdr['moyenne_ouvres'] or mdr['moyenne'])} postes** ont transmis leur "
                      "télémétrie au service MDR chaque jour ouvré. ")
        else:
            texte += "Aucun poste n'a transmis de télémétrie au service MDR sur la période. "
        n = len(mdr["incidents"])
        texte += ("Aucun incident de sécurité n'a été confirmé par les analystes MDR." if n == 0
                  else "1 incident de sécurité a été traité par les analystes MDR." if n == 1
                  else f"{n} incidents de sécurité ont été traités par les analystes MDR.")
    else:
        morceaux = []
        if p:
            morceaux.append(f"**{p['total']} appareils** administrés")
        if m:
            morceaux.append(f"**{fmt_nb(m['detections'])} détections** de menaces")
        if v:
            morceaux.append(f"**{v['total']} vulnérabilités** recensées")
        if morceaux:
            texte += "L'analyse porte sur " + ", ".join(morceaux) + "."
    return texte


def commentaire_mdr(d):
    mdr, p = d["mdr"], d["protection"]
    if not mdr or not mdr["max"]:
        return ""
    texte = (f"Sur le mois, **{_virgule(mdr['moyenne_ouvres'])} postes** en moyenne ont transmis leur télémétrie "
             f"chaque jour ouvré (maximum {mdr['max']}).")
    if p and p["total"]:
        from .analyse import couverture_mdr
        texte += f" Rapporté aux {p['total']} appareils administrés, le taux de couverture maximal est de {fmt_pct(mdr['max'], p['total'])}."
        c = couverture_mdr(mdr, p)
        if c["statut"] == "Normal":
            texte += " La quasi-totalité du parc est supervisée."
        elif c["statut"] == "À surveiller":
            texte += (f" **{c['hors_mdr']} {pluriel(c['hors_mdr'], 'appareil')}** ne transmettent pas leur télémétrie : "
                      "à vérifier (appareils éteints, retirés ou agent MDR absent).")
        else:
            texte += (f" **{c['hors_mdr']} appareils sur {c['administres']} échappent à la supervision MDR** : aucune "
                      "détection ni réponse managée n'est assurée sur ces appareils. Il faut vérifier le déploiement de l'agent "
                      "MDR, le nombre de licences et retirer de la console les appareils qui n'existent plus.")
    return texte


def commentaire_protection(d):
    p = d["protection"]
    if not p:
        return ""
    systemes = ", ".join(f"{n} sous {o}" for o, n in list(p["systemes"].items())[:4])
    genere = fmt_date(date.fromisoformat(p["genere_le"])) if p["genere_le"] else "—"
    return (f"Le parc administré compte **{p['total']} appareils** ({systemes}). Au moment de l'export ({genere}), "
            f"**{p['critique']} appareils ({fmt_pct(p['critique'], p['total'])})** sont en état critique, "
            f"{p['avertissement']} en avertissement et {p['ok']} en état normal.")


def commentaire_menaces(d):
    m = d["menaces"]
    if not m:
        return ""
    periode = (f"du {fmt_date(date.fromisoformat(m['couvert_debut']))} au "
               f"{fmt_date(date.fromisoformat(m['couvert_fin']))}")
    if not m["detections"]:
        return f"Aucune menace n'a été détectée sur le parc sur la période analysée ({periode})."
    n = len(m["non_neutralisees"])
    if not n:
        suite = ("Toutes ont été **bloquées ou supprimées automatiquement** par Kaspersky Endpoint Security ; "
                 "aucune infection active n'a été constatée.")
    else:
        details = ", ".join(f"{x['objet']} sur {x['appareil']}" for x in m["non_neutralisees"][:3])
        suite = (f"**{fmt_nb(m['neutralisees'])} ont été bloquées ou supprimées automatiquement.** Pour {n} "
                 f"{pluriel(n, 'détection')} ({details}), l'antivirus n'a remonté aucune action : une vérification "
                 "est prévue au plan d'action.")
    u = m["utilisateurs_touches"]
    return (f"Sur la période analysée ({periode}), **{fmt_nb(m['detections'])} détections** correspondant à "
            f"**{m['menaces_distinctes']} menaces distinctes** ont été enregistrées sur **{m['appareils_touches']} "
            f"appareils** ({u} {pluriel(u, 'utilisateur')}). {suite}")


def commentaire_vulnerabilites(d):
    v = d["vulnerabilites"]
    if not v:
        return ""
    return (f"L'analyse a identifié **{v['total']} vulnérabilités** distinctes dans les logiciels installés, dont "
            f"**{v['critiques']} critiques** et {v['elevees']} de gravité élevée. Non corrigées, ces failles peuvent être "
            "exploitées pour exécuter du code malveillant, élever des privilèges ou accéder aux données.")


def conclusion(d, prestataire):
    risque = d["risque"]["niveau"]
    m, p, mdr = d["menaces"], d["protection"], d["mdr"]
    phrases = []
    if m and m["detections"]:
        if not m["non_neutralisees"]:
            phrases.append(f"Les mécanismes de protection ont joué leur rôle : les {fmt_nb(m['detections'])} détections "
                           "du mois ont toutes été neutralisées automatiquement.")
        else:
            phrases.append(f"Les mécanismes de protection ont joué leur rôle : {fmt_nb(m['neutralisees'])} des "
                           f"{fmt_nb(m['detections'])} détections du mois ont été neutralisées automatiquement, "
                           "les autres faisant l'objet d'une vérification.")
    if mdr and not mdr["incidents"] and mdr["max"]:
        phrases.append("Aucun incident de sécurité n'a été confirmé par le service MDR.")
    if risque in ("Critique", "Élevé"):
        cause = ""
        if p and p["anomalies"].get("ksn"):
            cause = (" en particulier le rétablissement de l'accès aux serveurs KSN et la remise en conformité "
                     "des appareils déconnectés ou non administrés,")
        phrases.append(f"Néanmoins, le niveau de risque global reste **{risque.lower()}** et appelle des actions "
                       f"correctives rapides,{cause} conformément au plan d'action ci-dessus.")
    elif risque == "Modéré":
        phrases.append("Quelques points d'amélioration subsistent ; leur traitement permettra de renforcer "
                       "durablement le niveau de sécurité.")
    else:
        phrases.append("Le niveau de sécurité est satisfaisant ; la supervision se poursuit.")
    if d["exports_manquants"]:
        phrases.append("Ce rapport sera complété dès réception des exports Kaspersky Security Center manquants.")
    return (" ".join(phrases) + "\n\n"
            f"{prestataire} reste pleinement mobilisée aux côtés de {d['client']} pour mettre en œuvre ces actions "
            "et garantir un niveau de sécurité optimal et durable du système d'information.")


def contenu_par_defaut(d, prestataire="ESAY", suivi=None):
    """suivi : actions encore ouvertes du mois précédent (statut à mettre à jour à la relecture)."""
    return {
        "suivi": suivi or [],
        "niveau_risque": d["risque"]["niveau"],
        "motifs_risque": list(d["risque"]["motifs"]),
        "synthese": synthese(d, prestataire),
        "commentaires": {
            "mdr": commentaire_mdr(d),
            "protection": commentaire_protection(d),
            "menaces": commentaire_menaces(d),
            "vulnerabilites": commentaire_vulnerabilites(d),
        },
        "suggestion_mdr": d.get("suggestion_mdr") or "",
        "actions": [{**a, "statut": "À faire"} for a in d["actions"]],
        "conclusion": conclusion(d, prestataire),
    }

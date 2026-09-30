"""Bilans trimestriels et semestriels : consolidation des rapports mensuels validés d'une période.

Un bilan ne relit aucun fichier : il repart des données et des textes figés dans les rapports
mensuels validés (dernière version de chaque mois). Les mois sans rapport validé sont signalés.
"""
from collections import Counter
from datetime import date, timedelta

from .outils import MOIS_FR, bornes_mois, fmt_date, fmt_mois, fmt_nb, pluriel

DUREES = {"trimestriel": 3, "semestriel": 6}
NOMS = {"trimestriel": "trimestre", "semestriel": "semestre"}
ORDRE_RISQUE = {"Faible": 0, "Modéré": 1, "Élevé": 2, "Critique": 3}
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


# --------------------------------------------------------------------------- #
# Périodes
# --------------------------------------------------------------------------- #
def nb_periodes(periodicite):
    return 12 // DUREES[periodicite]


def numero_periode(periodicite, mois):
    return (mois - 1) // DUREES[periodicite] + 1


def mois_de_periode(periodicite, annee, numero):
    n = DUREES[periodicite]
    return [(annee, m) for m in range((numero - 1) * n + 1, numero * n + 1)]


def bornes_periode(periodicite, annee, numero):
    mois = mois_de_periode(periodicite, annee, numero)
    return bornes_mois(*mois[0])[0], bornes_mois(*mois[-1])[1]  # fin exclue


def libelle_court(periodicite, annee, numero):
    return f"{'T' if periodicite == 'trimestriel' else 'S'}{numero} {annee}"


def libelle_long(periodicite, annee, numero):
    rang = "1er" if numero == 1 else f"{numero}e"
    return f"{rang} {NOMS[periodicite]} {annee}"


def periode_courante(periodicite, aujourd_hui=None):
    """Dernière période terminée (ou en cours à partir de son dernier mois)."""
    j = aujourd_hui or date.today()
    numero = numero_periode(periodicite, j.month)
    dernier_mois = mois_de_periode(periodicite, j.year, numero)[-1][1]
    if j.month == dernier_mois and j.day >= 25:
        return j.year, numero
    return (j.year - 1, nb_periodes(periodicite)) if numero == 1 else (j.year, numero - 1)


# --------------------------------------------------------------------------- #
# Consolidation
# --------------------------------------------------------------------------- #
def _niveau_max(niveaux):
    connus = [n for n in niveaux if n in ORDRE_RISQUE]
    return max(connus, key=ORDRE_RISQUE.get) if connus else None


def _somme(valeurs):
    connues = [v for v in valeurs if v is not None]
    return sum(connues) if connues else None


def _moyenne(valeurs):
    connues = [v for v in valeurs if v is not None]
    return round(sum(connues) / len(connues), 1) if connues else None


def _premier_dernier(valeurs):
    connues = [v for v in valeurs if v is not None]
    return (connues[0], connues[-1]) if connues else (None, None)


def _bilan_actions(mensuels):
    """Actions recommandées sur la période et leur dernier avancement connu (suivi des mois suivants)."""
    actions = {}
    for r in mensuels:
        libelle_mois = fmt_mois(r["annee"], r["mois"])
        for a in r["contenu"].get("suivi", []):
            cle = a["action"].strip().lower()
            if cle in actions:
                actions[cle].update(statut=a.get("statut", "À faire"), commentaire=a.get("commentaire", ""))
        for a in r["contenu"].get("actions", []):
            cle = a["action"].strip().lower()
            if cle not in actions:
                actions[cle] = {"action": a["action"], "priorite": a.get("priorite", "Normale"),
                                "responsable": a.get("responsable", ""), "origine": libelle_mois,
                                "statut": a.get("statut", "À faire"), "commentaire": ""}
    ordre = {"Urgente": 0, "Haute": 1, "Normale": 2}
    liste = sorted(actions.values(), key=lambda a: (a["statut"] in ("Réalisée", "Abandonnée"), ordre.get(a["priorite"], 3)))
    return liste, dict(Counter(a["statut"] for a in liste))


def consolider_bilan(client, periodicite, annee, numero, mensuels):
    """client : {"nom", "mdr": bool} · mensuels : rapports mensuels validés de la période, sous forme de dict
    {"id", "annee", "mois", "version", "valide_le", "contenu", "donnees", "indicateurs"} (un par mois au plus)."""
    debut, fin = bornes_periode(periodicite, annee, numero)
    par_mois = {(r["annee"], r["mois"]): r for r in mensuels}
    mois, manquants = [], []
    for a, m in mois_de_periode(periodicite, annee, numero):
        r = par_mois.get((a, m))
        mois.append({"annee": a, "mois": m, "libelle": fmt_mois(a, m), "court": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}",
                     "present": r is not None, "rapport_id": r["id"] if r else None, "version": r["version"] if r else None,
                     "valide_le": r["valide_le"] if r else None, "niveau": r["contenu"].get("niveau_risque") if r else None,
                     "indicateurs": r["indicateurs"] if r else {}})
        if r is None:
            manquants.append(fmt_mois(a, m))
    presents = [r for r in sorted(mensuels, key=lambda r: (r["annee"], r["mois"]))]
    ind = lambda cle: [x["indicateurs"].get(cle) for x in mois if x["present"]]

    incidents = {}
    categories = Counter()
    for r in presents:
        d = r["donnees"]
        for i in (d.get("mdr") or {}).get("incidents", []):
            incidents[i["numero"]] = i
        categories.update((d.get("menaces") or {}).get("categories", {}))
    dernier = presents[-1]["donnees"] if presents else {}
    vulns = dernier.get("vulnerabilites") or {}
    actions, compte_actions = _bilan_actions(presents)
    crit_debut, crit_fin = _premier_dernier(ind("appareils_critiques"))
    vc_debut, vc_fin = _premier_dernier(ind("vulnerabilites_critiques"))

    totaux = {
        "mois_couverts": len(presents), "mois_attendus": len(mois),
        "detections": _somme(ind("detections")),
        "incidents_mdr": len(incidents) if client.get("mdr") else None,
        "postes_mdr_moyenne": _moyenne(ind("postes_mdr_moyenne")),
        "appareils_administres": _premier_dernier(ind("appareils_administres"))[1],
        "appareils_critiques_debut": crit_debut, "appareils_critiques_fin": crit_fin,
        "vulnerabilites_critiques_debut": vc_debut, "vulnerabilites_critiques_fin": vc_fin,
        "actions": len(actions), "actions_realisees": compte_actions.get("Réalisée", 0),
    }
    niveaux = [x["niveau"] for x in mois if x["present"]]
    avertissements = []
    if manquants:
        avertissements.append(f"{len(manquants)} {pluriel(len(manquants), 'mois')} sans rapport mensuel validé "
                              f"({', '.join(manquants)}) : {'il est exclu' if len(manquants) == 1 else 'ils sont exclus'} du bilan.")
    return {
        "type": "bilan", "client": client["nom"], "avec_mdr": bool(client.get("mdr")), "periodicite": periodicite,
        "annee": annee, "numero": numero, "libelle": libelle_court(periodicite, annee, numero),
        "libelle_long": libelle_long(periodicite, annee, numero), "nom_periode": NOMS[periodicite],
        "debut": debut.isoformat(), "fin": fin.isoformat(), "fin_incluse": (fin - timedelta(days=1)).isoformat(),
        "mois": mois, "manquants": manquants, "totaux": totaux,
        "niveau_suggere": niveaux[-1] if niveaux else None, "niveau_max": _niveau_max(niveaux),
        "motifs_suggeres": presents[-1]["contenu"].get("motifs_risque", []) if presents else [],
        "incidents": list(incidents.values()),
        "categories_menaces": dict(categories.most_common()),
        "applications": [(nom, {"total": i["total"], "critiques": i["critiques"]}) for nom, i in (vulns.get("applications") or [])[:8]],
        "actions": actions, "compte_actions": compte_actions,
        "avertissements": avertissements,
    }


def indicateurs_bilan(d):
    return {k: v for k, v in d["totaux"].items() if isinstance(v, (int, float))}


# --------------------------------------------------------------------------- #
# Textes par défaut (modifiables à la relecture)
# --------------------------------------------------------------------------- #
def _evol(debut, fin, libelle):
    if debut is None or fin is None:
        return None
    if fin == debut:
        return f"le nombre de {libelle} est resté stable ({fin})"
    sens = "a baissé" if fin < debut else "a augmenté"
    return f"le nombre de {libelle} {sens} de **{debut} à {fin}**"


def contenu_bilan_defaut(d, prestataire="ESAY"):
    t = d["totaux"]
    periode = f"du **{fmt_date(date.fromisoformat(d['debut']))} au {fmt_date(date.fromisoformat(d['fin_incluse']))}**"
    synthese = (f"Ce bilan couvre le {d['libelle_long']}, {periode}. Il consolide les "
                f"{t['mois_couverts']} {pluriel(t['mois_couverts'], 'rapport')} {pluriel(t['mois_couverts'], 'mensuel')} "
                f"de sécurité validés pour **{d['client']}**. ")
    if d["avec_mdr"] and t["postes_mdr_moyenne"] is not None:
        n = t["incidents_mdr"]
        synthese += (f"Le service MDR a supervisé en moyenne **{str(t['postes_mdr_moyenne']).replace('.', ',')} postes** ; "
                     + ("aucun incident de sécurité n'a été confirmé sur la période. " if not n
                        else f"**{n} {pluriel(n, 'incident')}** de sécurité {'a été traité' if n == 1 else 'ont été traités'} par les analystes. "))
    if t["detections"] is not None:
        synthese += f"Au total, **{fmt_nb(t['detections'])} détections** de menaces ont été enregistrées."

    evolutions = [e for e in (_evol(t["appareils_critiques_debut"], t["appareils_critiques_fin"], "appareils en état critique"),
                              _evol(t["vulnerabilites_critiques_debut"], t["vulnerabilites_critiques_fin"], "vulnérabilités critiques"))
                  if e]
    commentaire = ("Entre le premier et le dernier mois de la période, " + " et ".join(evolutions) + "."
                   if evolutions else "Les données disponibles ne permettent pas encore de dégager une tendance.")

    ouvertes = [a for a in d["actions"] if a["statut"] in ("À faire", "En cours")]
    perspectives = (f"Sur les {t['actions']} {pluriel(t['actions'], 'action')} {pluriel(t['actions'], 'recommandée')} au cours du "
                    f"{d['nom_periode']}, {t['actions_realisees']} {'a été réalisée' if t['actions_realisees'] == 1 else 'ont été réalisées'}. "
                    if t["actions"] else "")
    if ouvertes:
        perspectives += "Pour la période suivante, les priorités sont :\n\n" + "\n".join(
            f"**{a['action']}** ({a['priorite'].lower()}, {a['responsable']})" for a in ouvertes[:5])
    else:
        perspectives += "Aucune action corrective n'est en attente : la supervision se poursuit sur le même périmètre."

    conclusion = (f"{prestataire} poursuivra la supervision de sécurité de {d['client']} au cours du {d['nom_periode']} suivant "
                  "et rendra compte chaque mois de l'avancement des actions engagées.")
    return {"niveau_risque": d["niveau_suggere"] or "Modéré", "motifs_risque": list(d["motifs_suggeres"]),
            "synthese": synthese.strip(), "commentaire_evolution": commentaire,
            "perspectives": perspectives.strip(), "conclusion": conclusion}


__all__ = ["DUREES", "MOIS_FR", "consolider_bilan", "contenu_bilan_defaut", "indicateurs_bilan", "bornes_periode",
           "libelle_court", "libelle_long", "mois_de_periode", "nb_periodes", "numero_periode", "periode_courante"]

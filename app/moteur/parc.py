"""Suivi du parc appareil par appareil, à partir des exports « État de la protection » successifs.

Chaque export mensuel donne la liste des appareils signalés par KSC (état, anomalies, système, groupe).
En les mettant bout à bout, on repère les appareils qui reviennent en anomalie mois après mois,
et on planifie les systèmes d'exploitation qui arrivent en fin de support.
"""
from collections import Counter, defaultdict
from datetime import date

from .outils import MOIS_FR

# Fin du support étendu Microsoft (sécurité). Windows 11 dépend de la version : non suivi ici.
CALENDRIER_SUPPORT = [
    ("Windows XP", date(2014, 4, 8)), ("Windows Vista", date(2017, 4, 11)), ("Windows 7", date(2020, 1, 14)),
    ("Windows 8.1", date(2023, 1, 10)), ("Windows 8", date(2016, 1, 12)), ("Windows 10", date(2025, 10, 14)),
    ("Windows Server 2003", date(2015, 7, 14)), ("Windows Server 2008", date(2020, 1, 14)),
    ("Windows Server 2012", date(2023, 10, 10)), ("Windows Server 2016", date(2027, 1, 12)),
    ("Windows Server 2019", date(2029, 1, 9)), ("Windows Server 2022", date(2031, 10, 14)),
    ("Windows Server 2025", date(2034, 10, 10)),
]
HORIZONS = [(0, "expire", "Support terminé"), (180, "urgent", "Fin sous 6 mois"),
            (540, "a-planifier", "Fin sous 18 mois"), (None, "ok", "Supporté")]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def systeme_court(os_):
    return (os_ or "").replace("Microsoft ", "").strip() or "Inconnu"


def fin_de_support(os_):
    nom = systeme_court(os_)
    for prefixe, fin in CALENDRIER_SUPPORT:  # les préfixes les plus précis sont listés avant (8.1 avant 8)
        if nom.startswith(prefixe):
            return fin
    return None


def statut_support(fin, reference):
    if fin is None:
        return "inconnu", "Non suivi"
    jours = (fin - reference).days
    for seuil, cle, libelle in HORIZONS:
        if seuil is None or jours <= seuil:
            return cle, libelle
    return "ok", "Supporté"


def planning_fin_de_support(appareils, reference):
    """Systèmes du dernier export avec leur date de fin de support, du plus urgent au moins urgent."""
    par_os = defaultdict(list)
    for a in appareils:
        par_os[systeme_court(a["os"])].append(a)
    lignes = []
    for nom, liste in par_os.items():
        fin = fin_de_support(nom)
        cle, libelle = statut_support(fin, reference)
        lignes.append({"os": nom, "appareils": len(liste), "serveurs": sum(1 for a in liste if a.get("serveur")),
                       "noms": sorted(a["appareil"] for a in liste), "fin_support": fin,
                       "jours": (fin - reference).days if fin else None, "statut": cle, "libelle": libelle})
    ordre = {"expire": 0, "urgent": 1, "a-planifier": 2, "ok": 3, "inconnu": 4}
    return sorted(lignes, key=lambda l: (ordre[l["statut"]], l["jours"] if l["jours"] is not None else 10 ** 6, l["os"]))


def historique_appareils(mois):
    """mois : [(annee, mois, donnees_protection | None)] du plus ancien au plus récent.
    Renvoie les appareils avec leur état chaque mois et leur série d'anomalies en cours."""
    colonnes = [{"annee": a, "mois": m, "libelle": f"{MOIS_COURTS[m - 1]} {str(a)[2:]}",
                 "long": f"{MOIS_FR[m - 1]} {a}", "export": p is not None} for a, m, p in mois]
    appareils = {}
    for i, (_, _, p) in enumerate(mois):
        if p is None:
            continue
        for a in p["appareils"]:
            fiche = appareils.setdefault(a["appareil"], {"appareil": a["appareil"], "etats": [None] * len(mois)})
            fiche["etats"][i] = a["etat"]
            fiche.update(os=systeme_court(a["os"]), groupe=a.get("groupe") or "—", serveur=bool(a.get("serveur")),
                         anomalies=a.get("anomalies", []), raison=a.get("raison", ""), etat=a["etat"], dernier_mois=i)
    avec_export = [i for i, c in enumerate(colonnes) if c["export"]]
    dernier = avec_export[-1] if avec_export else None
    for f in appareils.values():
        signales = [i for i in avec_export if f["etats"][i]]
        f["mois_signales"] = len(signales)
        # Série en cours : mois consécutifs (parmi ceux qui ont un export) jusqu'au dernier export
        serie = 0
        for i in reversed(avec_export):
            if not f["etats"][i]:
                break
            serie += 1
        f["serie"] = serie
        f["present"] = dernier is not None and f["etats"][dernier] is not None
        f["recurrent"] = f["present"] and serie >= 2
        f["critique_continu"] = f["present"] and all(f["etats"][i] == "Critique" for i in avec_export[-serie:]) if serie else False
    liste = sorted(appareils.values(), key=lambda f: (not f["present"], -f["serie"], f["etat"] != "Critique",
                                                        not f["serveur"], f["appareil"]))
    return {"colonnes": colonnes, "appareils": liste, "mois_avec_export": len(avec_export),
            "recurrents": [f for f in liste if f["recurrent"]],
            "resolus": [f for f in liste if not f["present"] and f["mois_signales"]]}


def serveurs_critiques_consecutifs(precedent, courant):
    """Serveurs en état critique dans deux exports successifs (noms communs)."""
    if not precedent or not courant:
        return []
    avant = {a["appareil"] for a in precedent["appareils"] if a.get("serveur") and a["etat"] == "Critique"}
    return sorted(a["appareil"] for a in courant["appareils"]
                  if a.get("serveur") and a["etat"] == "Critique" and a["appareil"] in avant)


def repartition_anomalies(appareils):
    return Counter(x for a in appareils for x in a.get("anomalies", []))

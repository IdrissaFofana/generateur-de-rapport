"""Lecture des exports Kaspersky Security Center fournis par le client :
état de la protection, menaces, vulnérabilités.

L'extraction des tableaux est lente sur les gros PDF : le résultat est mis en
cache (dossier .cache) et réutilisé tant que le fichier n'a pas changé.
"""
import glob
import hashlib
import json
import os
import re
from datetime import datetime

import fitz

from .outils import date_ksc, dates_ksc, nettoyer

DOSSIER_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
VERSION_CACHE = 3

TYPES = {
    "protection": "Rapport sur l'état de la protection",
    "menaces": "Rapport sur les menaces",
    "vulnerabilites": "Rapport sur les vulnérabilités",
}
ETATS = ("Critique", "Avertissement", "OK")
GRAVITES = ("Critique", "Élevé", "Moyen", "Faible", "Avertissement")


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #
def _tables(doc):
    for page in doc:
        for table in page.find_tables().tables:
            yield [[nettoyer(c) for c in ligne] for ligne in table.extract()]


def _recapitulatif(texte, libelle):
    m = re.search(re.escape(libelle) + r"\s*:\s*(\d+)", texte)
    return int(m.group(1)) if m else None


def _complet(texte):
    """« En savoir plus (1000 de 2968) » -> (1000, 2968)"""
    m = re.search(r"En savoir plus \((\d+) de (\d+)\)", texte)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


# --------------------------------------------------------------------------- #
# État de la protection
# --------------------------------------------------------------------------- #
def _anomalies(raison, etat_app):
    """Transforme les raisons KSC en anomalies normalisées."""
    r = raison.lower()
    a = []
    if "plus administré" in r:
        a.append("non_administre")
    if "pas connecté au serveur" in r:
        a.append("deconnecte")
    if "recherche d'applications malveillantes" in r:
        a.append("analyse_ancienne")
    if "bases sont dépassées" in r or "bases obsolètes" in r:
        a.append("bases_depassees")
    if "n'est pas installée" in r or "non installée" in r:
        a.append("non_installe")
    if "désactivée" in r or "n'est pas en cours" in r or "protection en temps réel" in r:
        a.append("protection_desactivee")
    if "redémarrage" in r:
        a.append("redemarrage")
    if "licence" in r:
        a.append("licence")
    e = (etat_app or "").lower()
    if "ksn" in e:
        a.append("ksn")
    elif "désactiv" in e:
        a.append("protection_desactivee")
    elif "redémarrage" in e:
        a.append("redemarrage")
    elif "licence" in e:
        a.append("licence")
    elif e not in ("", "n/a") and "application" in r:
        a.append("autre")
    return sorted(set(a))


def _lire_protection(doc, texte):
    recap, appareils = [], []
    entete = None
    for lignes in _tables(doc):
        for cells in lignes:
            if cells and cells[0] == "État" and len(cells) > 10:
                entete = cells
                continue
            if len(cells) == 4 and cells[0] in ETATS and cells[2].isdigit():
                recap.append({"etat": cells[0], "raison": cells[1],
                              "appareils": int(cells[2]), "groupes": int(cells[3])})
                continue
            if entete is None or len(cells) < len(entete):
                continue
            decal = len(cells) - len(entete)  # colonne parasite en début de page
            c = dict(zip(entete, cells[decal:]))
            if c.get("État") not in ETATS:
                continue
            raison = c.get("Raison", "")
            etat_app = c.get("État de l'appareil défini par l'application", "")
            appareils.append({
                "etat": c["État"],
                "groupe": c.get("Groupe", ""),
                "appareil": c.get("Appareil", ""),
                "derniere_connexion": c.get("Dernière connexion au Serveur d'administration", ""),
                "raison": raison,
                "etat_application": etat_app,
                "ip": c.get("Adresse IP", ""),
                "os": c.get("Système d'exploitation", ""),
                "date_bases": c.get("Date de publication de la base antivirus", ""),
                "derniere_analyse": c.get("Dernière analyse complète", ""),
                "anomalies": _anomalies(raison, etat_app),
                "serveur": "server" in c.get("Système d'exploitation", "").lower(),
            })
    return {
        "nb_appareils": _recapitulatif(texte, "Nombre d'appareils"),
        "recapitulatif": recap,
        "appareils": appareils,
    }


# --------------------------------------------------------------------------- #
# Menaces
# --------------------------------------------------------------------------- #
def categorie_menace(objet, type_objet):
    o, t = objet.lower(), type_objet.lower()
    if "phishing" in t:
        return "Phishing"
    if "adware" in o:
        return "Adware"
    if "trojan" in o or "troie" in t:
        return "Cheval de Troie"
    if "backdoor" in o or "dérobée" in t:
        return "Backdoor"
    if "worm" in o or t == "ver":
        return "Ver"
    if "exploit" in o:
        return "Exploit"
    if "risktool" in o or "riskware" in o:
        return "Outil à risque"
    if "dangerousobject" in o:
        return "Objet dangereux (cloud)"
    if "virus" in t:
        return "Virus"
    if "malveillant" in t or "url" in t:
        return "Lien malveillant"
    if "autre application" in t:
        return "Application indésirable"
    return type_objet.capitalize() or "Autre"


def _lire_menaces(doc, texte):
    synthese, detections = [], []
    entete = None
    for lignes in _tables(doc):
        for cells in lignes:
            if "Objet détecté" in cells and "Action" in cells and len(cells) > 10:
                entete = cells
                continue
            if len(cells) == 8 and cells[2].isdigit() and cells[0] != "Objet détecté":
                dates = dates_ksc(cells[6] + cells[7])
                synthese.append({
                    "objet": cells[0], "type": cells[1],
                    "detections": int(cells[2]), "fichiers": int(cells[3]),
                    "appareils": int(cells[4]), "groupes": int(cells[5]),
                    "premiere": dates[0].isoformat() if dates else None,
                    "derniere": dates[-1].isoformat() if dates else None,
                    "categorie": categorie_menace(cells[0], cells[1]),
                })
                continue
            # Ligne de détail (les pages suivantes ajoutent une colonne parasite en tête)
            if entete is None or len(cells) < len(entete):
                continue
            c = dict(zip(entete, cells[len(cells) - len(entete):]))
            detecte = date_ksc(c.get("Détecté à", ""))
            if not detecte or not c.get("Appareil"):
                continue
            action = c.get("Action", "")
            evenement = re.search(r"Type d'événement : (.+?) Nom :", action)
            resultat = re.search(r"Description du résultat : (\S+)", action)
            detections.append({
                "groupe": c.get("Groupe", ""), "appareil": c["Appareil"], "objet": c.get("Objet détecté", ""),
                "detecte": detecte.isoformat(),
                "chemin": c.get("Chemin du fichier", ""), "type": c.get("Type de l'objet", ""),
                "evenement": evenement.group(1).strip() if evenement else "",
                "resultat": resultat.group(1) if resultat else "",
                "utilisateur": c.get("Compte utilisateur", ""),
                "categorie": categorie_menace(c.get("Objet détecté", ""), c.get("Type de l'objet", "")),
            })
    m = re.search(r"Période : du (.+?) jusqu'au (.+?\d{4})", texte)
    affiches, total = _complet(texte)
    return {
        "periode_debut": date_ksc(m.group(1)).date().isoformat() if m else None,
        "periode_fin": date_ksc(m.group(2)).date().isoformat() if m else None,
        "nb_menaces": _recapitulatif(texte, "Menaces détectées"),
        "nb_fichiers": _recapitulatif(texte, "Différents fichiers"),
        "nb_appareils_infectes": _recapitulatif(texte, "Appareils infectés"),
        "nb_groupes_infectes": _recapitulatif(texte, "Groupes infectés"),
        "detail_affiche": affiches, "detail_total": total,
        "synthese": synthese,
        "detections": detections,
    }


# --------------------------------------------------------------------------- #
# Vulnérabilités
# --------------------------------------------------------------------------- #
def _lire_vulnerabilites(doc, texte):
    synthese, detail = [], []
    for lignes in _tables(doc):
        for cells in lignes:
            k = next((i for i, c in enumerate(cells) if re.fullmatch(r"KLA\d+", c)), None)
            if k is None or k == 0 or cells[k - 1] not in GRAVITES:
                continue
            if len(cells) <= 8:
                if cells[k + 3].isdigit():
                    synthese.append({"gravite": cells[k - 1], "kla": cells[k],
                                     "editeur": cells[k + 1], "application": cells[k + 2],
                                     "appareils": int(cells[k + 3]),
                                     "groupes": int(cells[k + 4]) if cells[k + 4].isdigit() else None})
                continue
            # Colonnes stables par rapport à la colonne KLA (une colonne vide parasite peut précéder)
            if k + 10 >= len(cells):
                continue
            detail.append({
                "gravite": cells[k - 1], "kla": cells[k],
                "application": cells[k + 4], "version": cells[k + 6],
                "correctif": cells[k + 8], "groupe": cells[k + 9], "appareil": cells[k + 10],
            })
    affiches, total = _complet(texte)
    return {"synthese": synthese, "detail": detail,
            "detail_affiche": affiches, "detail_total": total}


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #
def type_export(chemin):
    nom = os.path.basename(chemin).lower()
    if "protection" in nom:
        return "protection"
    if "menace" in nom:
        return "menaces"
    if "vuln" in nom:
        return "vulnerabilites"
    return None


def _cle_cache(chemin):
    st = os.stat(chemin)
    brut = f"{VERSION_CACHE}|{os.path.abspath(chemin)}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()


def detecter_type(chemin):
    """Type d'export d'après le titre du PDF (None si ce n'est pas un export KSC reconnu)."""
    with fitz.open(chemin) as doc:
        debut = doc[0].get_text()[:500] if doc.page_count else ""
    return next((typ for typ, titre in TYPES.items() if titre in debut), None)


def lire_export(chemin, nom_fichier=None, cache=True):
    """Lit un export KSC. nom_fichier : nom d'origine à mémoriser (utile si le fichier a été renommé au stockage)."""
    fichier_cache = None
    if cache:
        os.makedirs(DOSSIER_CACHE, exist_ok=True)
        fichier_cache = os.path.join(DOSSIER_CACHE, _cle_cache(chemin) + ".json")
        if os.path.exists(fichier_cache):
            with open(fichier_cache, encoding="utf-8") as f:
                return json.load(f)

    typ = detecter_type(chemin)
    if typ is None:
        raise ValueError("Ce fichier n'est pas un export Kaspersky Security Center reconnu "
                         "(état de la protection, menaces ou vulnérabilités).")
    doc = fitz.open(chemin)
    texte = "\n".join(p.get_text() for p in doc)
    genere = date_ksc(texte[:300])
    lecteurs = {"protection": _lire_protection, "menaces": _lire_menaces,
                "vulnerabilites": _lire_vulnerabilites}
    donnees = lecteurs[typ](doc, texte)
    donnees.update({"type": typ, "fichier": nom_fichier or os.path.basename(chemin),
                    "genere_le": genere.isoformat() if genere else None})
    if fichier_cache:
        with open(fichier_cache, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
    return donnees


def exports_client(dossier):
    """Retourne le plus récent export de chaque type présent dans le dossier du client."""
    trouves = {}
    for chemin in glob.glob(os.path.join(dossier, "*.pdf")):
        typ = type_export(chemin)
        if typ is None or not os.path.basename(chemin).lower().startswith("rapport sur"):
            continue
        # Date dans le nom « (23-09-2026 14-06-46) », sinon date de modification
        m = re.search(r"\((\d{2})-(\d{2})-(\d{4}) (\d{2})-(\d{2})", chemin)
        horodatage = (datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                               int(m.group(4)), int(m.group(5))) if m
                      else datetime.fromtimestamp(os.path.getmtime(chemin)))
        if typ not in trouves or horodatage > trouves[typ][0]:
            trouves[typ] = (horodatage, chemin)
    return {typ: chemin for typ, (_, chemin) in trouves.items()}

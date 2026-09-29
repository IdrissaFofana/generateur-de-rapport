"""Lecture des rapports hebdomadaires Kaspersky MDR (multi-tenant)."""
import glob
import os
import re

import fitz

from .outils import date_mdr, nettoyer

_RE_TENANT = re.compile(r"^Statistics for (?:tenant (.+)|(root tenant))$")
_RE_JOUR = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_TITRE_POSTES = "Unique assets that sent telemetry in 30 days"


def _postes_par_tenant(doc):
    """{tenant: {date: nb_postes}} depuis les pages « Unique assets statistics »."""
    resultat = {}
    for page in doc:
        lignes = [l.strip() for l in page.get_text().split("\n")]
        tenant = None
        for i, l in enumerate(lignes):
            m = _RE_TENANT.match(l)
            if m:
                tenant = (m.group(1) or m.group(2)).strip()
                resultat.setdefault(tenant, {})
                debut = i
                break
        if tenant is None:
            continue
        # Le calendrier est entre le 1er et le 2e titre « Unique assets... »
        titres = [i for i, l in enumerate(lignes) if l == _TITRE_POSTES and i > debut]
        fin = titres[1] if len(titres) > 1 else len(lignes)
        zone = lignes[titres[0] + 1:fin] if titres else []
        for j in range(len(zone) - 1):
            if _RE_JOUR.match(zone[j]) and zone[j + 1].isdigit():
                resultat[tenant][date_mdr(zone[j]).date()] = int(zone[j + 1])
    return resultat


def _incidents(doc):
    """Liste des incidents de la section « Current incidents »."""
    incidents = []
    for page in doc:
        if not page.get_text().lstrip().startswith("Current incidents"):
            continue
        for table in page.find_tables().tables:
            for ligne in table.extract():
                cells = [nettoyer(c) for c in ligne]
                if len(cells) < 7 or cells[0] in ("", "Number"):
                    continue
                incidents.append({
                    "numero": cells[0], "nom": cells[1], "tenant": cells[2],
                    "cree": cells[3], "priorite": cells[4],
                    "statut": cells[5], "resolution": cells[6],
                })
    return incidents


def lire_hebdo(chemin):
    doc = fitz.open(chemin)
    texte = doc[0].get_text()
    m = re.search(r"(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})\s*-\s*(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", texte)
    if not m:
        raise ValueError(f"Période introuvable dans {chemin}")
    return {
        "fichier": os.path.basename(chemin),
        "debut": date_mdr(m.group(1)).date(),
        "fin": date_mdr(m.group(2)).date(),  # exclue
        "postes": _postes_par_tenant(doc),
        "incidents": _incidents(doc),
    }


def lire_tous_hebdos(dossier):
    rapports = []
    for chemin in sorted(glob.glob(os.path.join(dossier, "*.pdf"))):
        try:
            rapports.append(lire_hebdo(chemin))
        except Exception as e:  # un PDF étranger dans le dossier ne doit pas tout bloquer
            print(f"  ! Hebdo ignoré ({os.path.basename(chemin)}) : {e}")
    return sorted(rapports, key=lambda r: r["debut"])


def vers_json(h):
    """Hebdo lu -> dict JSON (pour stockage en base)."""
    return {**h, "debut": h["debut"].isoformat(), "fin": h["fin"].isoformat(),
            "postes": {t: {j.isoformat(): n for j, n in s.items()} for t, s in h["postes"].items()}}


def depuis_json(j):
    from datetime import date
    return {**j, "debut": date.fromisoformat(j["debut"]), "fin": date.fromisoformat(j["fin"]),
            "postes": {t: {date.fromisoformat(k): n for k, n in s.items()} for t, s in j["postes"].items()}}

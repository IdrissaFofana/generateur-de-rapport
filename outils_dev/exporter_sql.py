"""Export de la base locale vers un fichier SQL à rejouer sur le serveur, plus l'archive des fichiers déposés.

    python -m outils_dev.exporter_sql [dossier_sortie]        (depuis le dossier « plateforme »)

Produit :
  - donnees_locales.sql : vide les tables du serveur puis y insère les données locales (une seule transaction) ;
  - fichiers_stockage.tar.gz : PDF déposés et rapports générés, à extraire dans STOCKAGE_DIR sur le serveur.
Les chemins Windows (« hebdos\\x.pdf ») sont convertis au format Linux (« hebdos/x.pdf »).
"""
import json
import os
import sys
import tarfile
from datetime import date, datetime

from sqlalchemy import select

from app.config import STOCKAGE_DIR
from app.db import Base, moteur
from app import modeles  # noqa: F401  (enregistre les modèles)

# Ordre d'insertion respectant les clés étrangères
TABLES = ["utilisateurs", "clients", "hebdos", "exports_ksc", "rapports", "journal", "contrats", "alertes", "envois", "bibliotheque", "interventions", "assistances_planifiees", "formations",
          "certifications", "activites_internes", "rapports_service"]
CHEMINS = {"hebdos": ["chemin"], "exports_ksc": ["chemin"], "rapports": ["pdf"], "interventions": ["pdf", "fichier_source"], "certifications": ["fichier"], "rapports_service": ["pdf"]}


def litteral(valeur, jsonb=False):
    if valeur is None:
        return "NULL"
    if jsonb:
        return "'" + json.dumps(valeur, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    if isinstance(valeur, bool):
        return "TRUE" if valeur else "FALSE"
    if isinstance(valeur, (int, float)):
        return repr(valeur)
    if isinstance(valeur, (datetime, date)):
        return "'" + valeur.isoformat(sep=" ") + "'" if isinstance(valeur, datetime) else "'" + valeur.isoformat() + "'"
    return "'" + str(valeur).replace("'", "''") + "'"


def main(sortie):
    os.makedirs(sortie, exist_ok=True)
    lignes = [
        "-- Données de la plateforme « Rapports de sécurité » exportées depuis le poste local",
        f"-- Généré le {datetime.now():%d/%m/%Y %H:%M}",
        "-- ATTENTION : remplace tout le contenu actuel des tables sur le serveur.",
        "-- Exécution : psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -f donnees_locales.sql",
        "",
        "SET client_encoding = 'UTF8';",
        "BEGIN;",
        "",
        "TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE;",
    ]
    comptes = {}
    with moteur.connect() as cx:
        for nom in TABLES:
            table = Base.metadata.tables[nom]
            colonnes = list(table.columns)
            rangs = cx.execute(select(table).order_by(table.c.id)).mappings().all()
            comptes[nom] = len(rangs)
            lignes += ["", f"-- {nom} ({len(rangs)})"]
            entete = f"INSERT INTO {nom} (" + ", ".join(c.name for c in colonnes) + ") VALUES"
            for r in rangs:
                valeurs = []
                for c in colonnes:
                    v = r[c.name]
                    if c.name in CHEMINS.get(nom, []) and v:
                        v = v.replace("\\", "/")
                    valeurs.append(litteral(v, jsonb=c.type.__class__.__name__ == "JSONB"))
                lignes.append(entete + " (" + ", ".join(valeurs) + ");")
            # Les identifiants suivants reprennent après le plus grand id importé
            lignes.append(f"SELECT setval(pg_get_serial_sequence('{nom}', 'id'), "
                          f"COALESCE((SELECT MAX(id) FROM {nom}), 0) + 1, false);")
    lignes += ["", "COMMIT;", ""]
    fichier_sql = os.path.join(sortie, "donnees_locales.sql")
    with open(fichier_sql, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lignes))

    archive = os.path.join(sortie, "fichiers_stockage.tar.gz")
    nb = 0
    with tarfile.open(archive, "w:gz") as tar:
        for racine, _, fichiers in os.walk(STOCKAGE_DIR):
            for nom in fichiers:
                chemin = os.path.join(racine, nom)
                relatif = os.path.relpath(chemin, STOCKAGE_DIR).replace("\\", "/")
                if relatif.startswith("_") or "/_" in relatif:
                    continue
                tar.add(chemin, arcname=relatif)
                nb += 1
    print("Tables :", ", ".join(f"{t} {n}" for t, n in comptes.items()))
    print(f"SQL     : {fichier_sql}")
    print(f"Fichiers: {archive} ({nb} fichiers)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "export_serveur")

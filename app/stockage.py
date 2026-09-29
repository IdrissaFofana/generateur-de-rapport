"""Stockage des fichiers déposés et des rapports générés.

Les fichiers sont rangés sous leur empreinte SHA-256 (jamais sous le nom fourni par l'utilisateur).
"""
import hashlib
import os

from fastapi import UploadFile

from .config import STOCKAGE_DIR, TAILLE_MAX_DEPOT


class DepotInvalide(ValueError):
    pass


async def lire_pdf(fichier: UploadFile):
    """Contenu du fichier déposé après contrôles (PDF, taille)."""
    if not (fichier.filename or "").lower().endswith(".pdf"):
        raise DepotInvalide(f"« {fichier.filename} » n'est pas un fichier PDF.")
    contenu = await fichier.read(TAILLE_MAX_DEPOT + 1)
    if len(contenu) > TAILLE_MAX_DEPOT:
        raise DepotInvalide(f"« {fichier.filename} » dépasse la taille maximale autorisée.")
    if not contenu.startswith(b"%PDF"):
        raise DepotInvalide(f"« {fichier.filename} » n'est pas un PDF valide.")
    return contenu


def empreinte(contenu):
    return hashlib.sha256(contenu).hexdigest()


def enregistrer(contenu, *sous_dossiers):
    h = empreinte(contenu)
    dossier = os.path.join(STOCKAGE_DIR, *sous_dossiers)
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, h + ".pdf")
    if not os.path.exists(chemin):
        with open(chemin, "wb") as f:
            f.write(contenu)
    return os.path.relpath(chemin, STOCKAGE_DIR), h


def absolu(chemin_relatif):
    chemin = os.path.normpath(os.path.join(STOCKAGE_DIR, chemin_relatif))
    if not chemin.startswith(os.path.normpath(STOCKAGE_DIR)):
        raise ValueError("Chemin de stockage invalide.")
    return chemin


def supprimer(chemin_relatif):
    try:
        os.remove(absolu(chemin_relatif))
    except FileNotFoundError:
        pass

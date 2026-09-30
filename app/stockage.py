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


# Formats acceptés : extension → (signature des premiers octets, type MIME)
FORMATS = {
    ".pdf": (b"%PDF", "application/pdf"),
    ".docx": (bytes([0x50, 0x4B, 0x03, 0x04]), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".png": (bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]), "image/png"),
    ".jpg": (bytes([0xFF, 0xD8, 0xFF]), "image/jpeg"),
    ".jpeg": (bytes([0xFF, 0xD8, 0xFF]), "image/jpeg"),
}


async def lire_fichier(fichier: UploadFile, extensions, taille_max=TAILLE_MAX_DEPOT):
    """Contenu d'un fichier déposé, contrôlé par extension ET par signature (un .pdf renommé en .png est refusé).
    Renvoie (contenu, extension normalisée)."""
    nom = (fichier.filename or "").lower()
    extension = next((e for e in extensions if nom.endswith(e)), None)
    if extension is None:
        raise DepotInvalide(f"« {fichier.filename} » : format non accepté ({', '.join(extensions)}).")
    contenu = await fichier.read(taille_max + 1)
    if len(contenu) > taille_max:
        raise DepotInvalide(f"« {fichier.filename} » dépasse la taille maximale autorisée.")
    if not contenu.startswith(FORMATS[extension][0]):
        raise DepotInvalide(f"« {fichier.filename} » : le contenu ne correspond pas à son extension.")
    return contenu, ".jpg" if extension == ".jpeg" else extension


def type_mime(chemin):
    return next((m for e, (_, m) in FORMATS.items() if chemin.lower().endswith(e)), "application/octet-stream")


def empreinte(contenu):
    return hashlib.sha256(contenu).hexdigest()


def enregistrer(contenu, *sous_dossiers, extension=".pdf"):
    h = empreinte(contenu)
    dossier = os.path.join(STOCKAGE_DIR, *sous_dossiers)
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, h + extension)
    if not os.path.exists(chemin):
        with open(chemin, "wb") as f:
            f.write(contenu)
    return os.path.relpath(chemin, STOCKAGE_DIR).replace(os.sep, "/"), h  # « / » quel que soit le système


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

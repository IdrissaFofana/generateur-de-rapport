"""Configuration lue depuis l'environnement (fichier .env à la racine de la plateforme)."""
import os
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

RACINE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
load_dotenv(os.path.join(RACINE, ".env"))


def _url_sqlalchemy(url):
    """Accepte le format Prisma (postgresql://…?schema=public) et le convertit pour SQLAlchemy/psycopg."""
    morceaux = urlsplit(url)
    schema = "postgresql+psycopg" if morceaux.scheme in ("postgresql", "postgres") else morceaux.scheme
    requete = "&".join(p for p in morceaux.query.split("&") if p and not p.startswith("schema="))
    return urlunsplit((schema, morceaux.netloc, morceaux.path, requete, ""))


DATABASE_URL = _url_sqlalchemy(os.environ["DATABASE_URL"])
SECRET_KEY = os.environ["SECRET_KEY"]
PORT = int(os.environ.get("PORT", "8010"))
STOCKAGE_DIR = os.path.normpath(os.path.join(RACINE, os.environ.get("STOCKAGE_DIR", "./donnees")))
# Cookie de session « Secure » : à activer quand la plateforme est servie en HTTPS
COOKIE_SECURISE = os.environ.get("COOKIE_SECURISE", "0") == "1"
TAILLE_MAX_DEPOT = int(os.environ.get("TAILLE_MAX_DEPOT_MO", "50")) * 1024 * 1024

PRESTATAIRE = {
    "nom": os.environ.get("PRESTATAIRE_NOM", "ESAY"),
    "nom_complet": os.environ.get("PRESTATAIRE_NOM_COMPLET", "ESAY Corporation"),
    "signataire": os.environ.get("PRESTATAIRE_SIGNATAIRE", "Équipe technique ESAY"),
}

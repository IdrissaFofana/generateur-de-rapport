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

# Adresse de la plateforme, pour les liens des e-mails et messages Teams
URL_PLATEFORME = os.environ.get("URL_PLATEFORME", "http://127.0.0.1:8010").rstrip("/")


def _liste(nom):
    return [x.strip() for x in os.environ.get(nom, "").replace(";", ",").split(",") if x.strip()]


# Notifications (toutes facultatives : sans configuration, les alertes restent visibles dans la plateforme)
SMTP = {
    "hote": os.environ.get("SMTP_HOTE", ""),
    "port": int(os.environ.get("SMTP_PORT", "587")),
    "securite": os.environ.get("SMTP_SECURITE", "starttls").lower(),  # starttls | ssl | aucune
    "utilisateur": os.environ.get("SMTP_UTILISATEUR", ""),
    "mot_de_passe": os.environ.get("SMTP_MOT_DE_PASSE", ""),
    "expediteur": os.environ.get("SMTP_EXPEDITEUR", ""),
}
ALERTES_EMAILS = _liste("ALERTES_EMAILS")        # destinataires des alertes, au fil de l'eau
RESUME_EMAILS = _liste("RESUME_EMAILS")          # destinataires du résumé hebdomadaire (direction)
TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK", "")  # URL d'un workflow Teams « requête webhook reçue »
# Seuils des alertes
SEUIL_HAUSSE_DETECTIONS = int(os.environ.get("SEUIL_HAUSSE_DETECTIONS_PCT", "50"))
SEUIL_SOUS_UTILISATION = int(os.environ.get("SEUIL_SOUS_UTILISATION_PCT", "70"))
# Engagement interne : rapport mensuel validé au plus tard N jours après la fin du mois
ENGAGEMENT_DELAI_JOURS = int(os.environ.get("ENGAGEMENT_DELAI_JOURS", "10"))

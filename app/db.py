"""Connexion PostgreSQL (SQLAlchemy 2) et migrations du schéma (Alembic)."""
import os

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, RACINE

moteur = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
Session = sessionmaker(bind=moteur, expire_on_commit=False)

REVISION_INITIALE = "0001"  # schéma des bases créées avant l'introduction des migrations


class Base(DeclarativeBase):
    pass


def session_db():
    """Dépendance FastAPI : une session par requête."""
    with Session() as s:
        yield s


def migrer():
    """Met la base au niveau des modèles (appelé au démarrage et par « gerer.py init »).

    Une base créée avant les migrations (tables présentes, pas de table alembic_version)
    est d'abord marquée au niveau du schéma initial : ses données sont conservées."""
    from alembic import command
    from alembic.config import Config

    config = Config(os.path.join(RACINE, "alembic.ini"))
    with moteur.begin() as connexion:
        config.attributes["connexion"] = connexion
        tables = inspect(connexion).get_table_names()
        if "utilisateurs" in tables and "alembic_version" not in tables:
            command.stamp(config, REVISION_INITIALE)
        command.upgrade(config, "head")


creer_tables = migrer  # ancien nom, conservé pour les scripts existants

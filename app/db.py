"""Connexion PostgreSQL (SQLAlchemy 2)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

moteur = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
Session = sessionmaker(bind=moteur, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def session_db():
    """Dépendance FastAPI : une session par requête."""
    with Session() as s:
        yield s


def creer_tables():
    from . import modeles  # noqa: F401  (enregistre les modèles)
    Base.metadata.create_all(moteur)

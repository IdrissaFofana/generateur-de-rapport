"""Environnement Alembic : même connexion et mêmes modèles que l'application."""
from alembic import context

from app import modeles  # noqa: F401  (enregistre les modèles)
from app.db import Base, moteur

config = context.config


def executer():
    connexion = config.attributes.get("connexion")
    if connexion is not None:  # appel depuis l'application (app.db.migrer)
        _migrer(connexion)
        return
    with moteur.connect() as connexion:
        _migrer(connexion)


def _migrer(connexion):
    context.configure(connection=connexion, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


executer()

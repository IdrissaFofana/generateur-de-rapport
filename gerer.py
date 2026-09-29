"""Commandes d'administration de la plateforme.

    python gerer.py init                                   crée les tables
    python gerer.py creer-admin <email> "<Nom>"            crée un administrateur (mot de passe provisoire affiché)
    python gerer.py importer-clients <config.json>         importe les clients du générateur en ligne de commande
"""
import json
import sys

from sqlalchemy import select

from app.db import Session, creer_tables
from app.modeles import Client, Utilisateur, journaliser
from app.securite import hacher
from app.web.admin import mot_de_passe_provisoire


def init():
    creer_tables()
    print("Tables créées (ou déjà présentes).")


def creer_admin(email, nom):
    creer_tables()
    email = email.strip().lower()
    with Session() as db:
        if db.scalar(select(Utilisateur).where(Utilisateur.email == email)):
            sys.exit(f"Un compte existe déjà pour {email}.")
        mdp = mot_de_passe_provisoire()
        db.add(Utilisateur(email=email, nom=nom, role="admin", mot_de_passe=hacher(mdp), doit_changer_mdp=True))
        journaliser(db, None, "création administrateur (ligne de commande)", email)
        db.commit()
    print(f"Administrateur créé : {email}\nMot de passe provisoire : {mdp}\n"
          "Il devra être changé à la première connexion.")


def importer_clients(chemin):
    creer_tables()
    with open(chemin, encoding="utf-8") as f:
        config = json.load(f)
    with Session() as db:
        for c in config["clients"]:
            if db.scalar(select(Client).where(Client.nom == c["nom"])):
                print(f"  = {c['nom']} (déjà présent)")
                continue
            db.add(Client(nom=c["nom"], avec_mdr=True, avec_ksc=True, tenants_mdr=c.get("tenants_mdr", []),
                          notes=c.get("note", "")))
            print(f"  + {c['nom']}")
        journaliser(db, None, "import des clients (ligne de commande)", chemin)
        db.commit()


if __name__ == "__main__":
    commandes = {"init": init, "creer-admin": creer_admin, "importer-clients": importer_clients}
    if len(sys.argv) < 2 or sys.argv[1] not in commandes:
        sys.exit(__doc__)
    commandes[sys.argv[1]](*sys.argv[2:])

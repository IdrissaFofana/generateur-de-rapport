"""Tableau de bord."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import services
from ..db import session_db
from ..modeles import Client
from ..securite import exiger
from .commun import mois_courant, page

routes = APIRouter()


def _contexte(db, annee, mois):
    clients = db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all()
    hebdos = services.hebdos_du_mois(db, annee, mois)
    etats = [services.etat_client(db, c, annee, mois, hebdos) for c in clients]
    return {"etats": etats, "annee": annee, "mois": mois, "en_cours": any(e["en_cours"] for e in etats)}


@routes.get("/")
def tableau(request: Request, annee: int | None = None, mois: int | None = None,
            u=Depends(exiger("lecteur")), db: SessionDB = Depends(session_db)):
    if not (annee and mois and 1 <= mois <= 12):
        annee, mois = mois_courant()
    return page(request, "tableau.html", u, **_contexte(db, annee, mois))


@routes.get("/tableau/liste")
def tableau_liste(request: Request, annee: int, mois: int, u=Depends(exiger("lecteur")),
                  db: SessionDB = Depends(session_db)):
    return page(request, "_tableau_liste.html", u, **_contexte(db, annee, mois))

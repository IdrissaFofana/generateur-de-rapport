"""Connexion, déconnexion et changement de mot de passe."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from ..db import session_db
from ..modeles import Utilisateur, journaliser
from ..securite import hacher, mot_de_passe_valide, verifier, verifier_csrf
from .commun import flash, page, rediriger

routes = APIRouter()


@routes.get("/connexion")
def connexion_form(request: Request):
    return page(request, "connexion.html")


@routes.post("/connexion", dependencies=[Depends(verifier_csrf)])
def connexion(request: Request, email: str = Form(...), mot_de_passe: str = Form(...),
              db: SessionDB = Depends(session_db)):
    u = db.scalar(select(Utilisateur).where(Utilisateur.email == email.strip().lower()))
    if u is None or not u.actif or not verifier(mot_de_passe, u.mot_de_passe):
        return page(request, "connexion.html", erreur="Adresse e-mail ou mot de passe incorrect.", email=email)
    request.session.clear()
    request.session["uid"] = u.id
    u.derniere_connexion = datetime.now()
    journaliser(db, u, "connexion")
    db.commit()
    return rediriger("/mon-compte" if u.doit_changer_mdp else "/")


@routes.get("/deconnexion")
def deconnexion(request: Request):
    request.session.clear()
    return rediriger("/connexion")


@routes.get("/mon-compte")
def mon_compte_form(request: Request, db: SessionDB = Depends(session_db)):
    u = db.get(Utilisateur, request.session.get("uid") or 0)
    if u is None:
        return rediriger("/connexion")
    return page(request, "mon_compte.html", u)


@routes.post("/mon-compte", dependencies=[Depends(verifier_csrf)])
def mon_compte(request: Request, actuel: str = Form(...), nouveau: str = Form(...), confirmation: str = Form(...),
               db: SessionDB = Depends(session_db)):
    u = db.get(Utilisateur, request.session.get("uid") or 0)
    if u is None:
        return rediriger("/connexion")
    erreur = None
    if not verifier(actuel, u.mot_de_passe):
        erreur = "Le mot de passe actuel est incorrect."
    elif nouveau != confirmation:
        erreur = "La confirmation ne correspond pas au nouveau mot de passe."
    elif nouveau == actuel:
        erreur = "Le nouveau mot de passe doit être différent de l'actuel."
    else:
        erreur = mot_de_passe_valide(nouveau)
    if erreur:
        return page(request, "mon_compte.html", u, erreur=erreur)
    u.mot_de_passe = hacher(nouveau)
    u.doit_changer_mdp = False
    journaliser(db, u, "changement de mot de passe")
    db.commit()
    flash(request, "Mot de passe modifié.")
    return rediriger("/")

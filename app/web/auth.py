"""Connexion (mot de passe puis code à usage unique si la double authentification est active), déconnexion,
compte personnel : mot de passe et double authentification."""
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import totp
from ..supervision import evenement_securite
from ..db import session_db
from ..modeles import Utilisateur, journaliser
from ..securite import (adresse_ip, compte_verrouille, enregistrer_echec, hacher, limiteur_ip, mot_de_passe_valide,
                        ouvrir_session, utilisateur_session, verifier, verifier_csrf)
from .commun import flash, page, rediriger

routes = APIRouter()
# Message unique : ne révèle ni l'existence du compte, ni son verrouillage
ECHEC = "Connexion impossible : identifiants incorrects, ou trop de tentatives (réessayez dans quelques minutes)."
DELAI_CODE = 300  # secondes pour saisir le code après le mot de passe
# Empreinte « leurre » calculée une fois : un compte inconnu coûte une vérification, comme un compte réel
LEURRE = hacher(secrets.token_urlsafe(16))


def accueil(u):
    """Page d'arrivée selon le rôle : la production pour ceux qui la font, la vue d'ensemble pour les autres."""
    return "/production" if u.role in ("operateur", "validateur") else "/"


def _connecter(request, db, u):
    u.echecs_connexion, u.bloque_jusqua, u.derniere_connexion = 0, None, datetime.now()
    limiteur_ip.reinitialiser(adresse_ip(request))
    ouvrir_session(request, u)
    evenement_securite("connexion", adresse_ip(request), u.email, "2fa" if u.totp_actif else "mot de passe")
    journaliser(db, u, "connexion", f"depuis {adresse_ip(request)}" + (" (double authentification)" if u.totp_actif else ""))
    db.commit()
    return rediriger("/mon-compte" if u.doit_changer_mdp else accueil(u))


def _echec(request, db, u, email, etape):
    ip = adresse_ip(request)
    limiteur_ip.echec(ip)
    verrouille = enregistrer_echec(u) if u is not None else False
    evenement_securite("echec_connexion", ip, email or "inconnu", etape)
    if verrouille:
        evenement_securite("compte_verrouille", ip, email)
    journaliser(db, u, "échec de connexion", f"{etape} · {email} · depuis {ip}", acteur=email or "inconnu")
    if verrouille:
        journaliser(db, u, "compte verrouillé", f"{email} après échecs répétés · depuis {ip}", acteur=email)
    db.commit()


# --------------------------------------------------------------------------- #
# Connexion en une ou deux étapes
# --------------------------------------------------------------------------- #
@routes.get("/connexion")
def connexion_form(request: Request):
    return page(request, "connexion.html")


@routes.post("/connexion", dependencies=[Depends(verifier_csrf)])
def connexion(request: Request, email: str = Form(...), mot_de_passe: str = Form(...),
              db: SessionDB = Depends(session_db)):
    email = email.strip().lower()
    if limiteur_ip.bloque(adresse_ip(request)):
        evenement_securite("ip_bloquee", adresse_ip(request), email or "inconnu", "trop d'échecs")
        journaliser(db, None, "connexion refusée", f"trop d'échecs depuis {adresse_ip(request)}", acteur=email or "inconnu")
        db.commit()
        return page(request, "connexion.html", erreur=ECHEC, email=email)
    u = db.scalar(select(Utilisateur).where(Utilisateur.email == email))
    # Le mot de passe est vérifié même pour un compte verrouillé ou inconnu : temps de réponse homogène
    valide = verifier(mot_de_passe, u.mot_de_passe if u else LEURRE)
    if u is None or not u.actif or compte_verrouille(u) or not valide:
        _echec(request, db, u, email, "mot de passe")
        return page(request, "connexion.html", erreur=ECHEC, email=email)
    if u.totp_actif:
        request.session.clear()
        request.session["uid_2fa"], request.session["t_2fa"] = u.id, time.time()
        return rediriger("/connexion/code")
    return _connecter(request, db, u)


@routes.get("/connexion/code")
def code_form(request: Request):
    if not request.session.get("uid_2fa"):
        return rediriger("/connexion")
    return page(request, "connexion_code.html")


@routes.post("/connexion/code", dependencies=[Depends(verifier_csrf)])
def code(request: Request, code: str = Form(...), db: SessionDB = Depends(session_db)):
    uid, debut = request.session.get("uid_2fa"), request.session.get("t_2fa", 0)
    u = db.get(Utilisateur, uid) if uid else None
    if u is None or time.time() - debut > DELAI_CODE:
        request.session.clear()
        flash(request, "Délai dépassé : reconnectez-vous.", "erreur")
        return rediriger("/connexion")
    if limiteur_ip.bloque(adresse_ip(request)) or compte_verrouille(u) or not u.actif:
        request.session.clear()
        return page(request, "connexion.html", erreur=ECHEC, email=u.email)
    pas = totp.verifier(u.totp_secret, code, u.totp_dernier_pas)
    if pas is None:
        _echec(request, db, u, u.email, "code de double authentification")
        return page(request, "connexion_code.html", erreur="Code incorrect ou déjà utilisé.")
    u.totp_dernier_pas = pas
    return _connecter(request, db, u)


@routes.get("/deconnexion")
def deconnexion_lien(request: Request):
    """Un simple lien ne déconnecte pas (protection contre la déconnexion forcée depuis un autre site)."""
    return rediriger("/mon-compte")


@routes.post("/deconnexion", dependencies=[Depends(verifier_csrf)])
def deconnexion(request: Request):
    request.session.clear()
    return rediriger("/connexion")


# --------------------------------------------------------------------------- #
# Mon compte : mot de passe et double authentification
# --------------------------------------------------------------------------- #
def _compte(request, db):
    return utilisateur_session(request, db)


@routes.get("/mon-compte")
def mon_compte_form(request: Request, db: SessionDB = Depends(session_db)):
    u = _compte(request, db)
    if u is None:
        return rediriger("/connexion")
    return _page_compte(request, u)


def _page_compte(request, u, **extra):
    """Mon compte ; si une activation de la double authentification est en cours, QR code et clé à saisir."""
    secret = request.session.get("totp_en_attente")
    qr = totp.qr_svg(totp.uri(secret, u.email)) if secret and not u.totp_actif else None
    cle = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)) if qr else None
    return page(request, "mon_compte.html", u, exige_2fa=_exige_2fa(u), qr=qr, cle=cle, **extra)


def _exige_2fa(u):
    from ..config import EXIGER_2FA_ROLES
    return u.role in EXIGER_2FA_ROLES


@routes.post("/mon-compte", dependencies=[Depends(verifier_csrf)])
def mon_compte(request: Request, actuel: str = Form(...), nouveau: str = Form(...), confirmation: str = Form(...),
               db: SessionDB = Depends(session_db)):
    u = _compte(request, db)
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
        return _page_compte(request, u, erreur=erreur)
    u.mot_de_passe = hacher(nouveau)
    u.doit_changer_mdp = False
    u.version_session += 1  # les autres sessions ouvertes sont fermées
    journaliser(db, u, "changement de mot de passe", "autres sessions fermées")
    db.commit()
    ouvrir_session(request, u)
    flash(request, "Mot de passe modifié. Vos autres sessions ont été fermées.")
    return rediriger("/mon-compte" if _exige_2fa(u) and not u.totp_actif else accueil(u))


@routes.post("/mon-compte/2fa/preparer", dependencies=[Depends(verifier_csrf)])
def preparer_2fa(request: Request, db: SessionDB = Depends(session_db)):
    """Nouveau secret gardé en session tant que l'utilisateur n'a pas prouvé qu'il l'a bien enregistré."""
    u = _compte(request, db)
    if u is None:
        return rediriger("/connexion")
    request.session["totp_en_attente"] = totp.generer_secret()
    return rediriger("/mon-compte#double-authentification")


@routes.post("/mon-compte/2fa/activer", dependencies=[Depends(verifier_csrf)])
def activer_2fa(request: Request, code: str = Form(...), db: SessionDB = Depends(session_db)):
    u = _compte(request, db)
    secret = request.session.get("totp_en_attente")
    if u is None or not secret:
        return rediriger("/mon-compte")
    pas = totp.verifier(secret, code)
    if pas is None:
        flash(request, "Code incorrect : vérifiez l'heure du téléphone et saisissez le code affiché.", "erreur")
        return rediriger("/mon-compte#double-authentification")
    u.totp_secret, u.totp_actif, u.totp_dernier_pas = secret, True, pas
    u.version_session += 1
    journaliser(db, u, "double authentification activée", "autres sessions fermées")
    db.commit()
    request.session.pop("totp_en_attente", None)
    ouvrir_session(request, u)
    flash(request, "Double authentification activée : un code vous sera demandé à chaque connexion.")
    return rediriger("/mon-compte")


@routes.post("/mon-compte/2fa/desactiver", dependencies=[Depends(verifier_csrf)])
def desactiver_2fa(request: Request, mot_de_passe: str = Form(...), code: str = Form(...),
                   db: SessionDB = Depends(session_db)):
    u = _compte(request, db)
    if u is None:
        return rediriger("/connexion")
    if _exige_2fa(u):
        flash(request, "La double authentification est obligatoire pour votre rôle.", "erreur")
        return rediriger("/mon-compte")
    pas = totp.verifier(u.totp_secret, code, u.totp_dernier_pas)
    if not verifier(mot_de_passe, u.mot_de_passe) or pas is None:
        flash(request, "Mot de passe ou code incorrect.", "erreur")
        return rediriger("/mon-compte#double-authentification")
    u.totp_secret, u.totp_actif, u.totp_dernier_pas = None, False, None
    u.version_session += 1
    journaliser(db, u, "double authentification désactivée")
    db.commit()
    ouvrir_session(request, u)
    flash(request, "Double authentification désactivée.", "info")
    return rediriger("/mon-compte")

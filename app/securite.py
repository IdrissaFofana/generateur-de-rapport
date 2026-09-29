"""Mots de passe, session, contrôle des rôles et protection CSRF."""
import base64
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as SessionDB

from .db import session_db
from .modeles import Utilisateur

_N, _R, _P = 2 ** 14, 8, 1  # paramètres scrypt


def hacher(mot_de_passe):
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${base64.b64encode(sel).decode()}${base64.b64encode(h).decode()}"


def verifier(mot_de_passe, stocke):
    try:
        _, sel, h = stocke.split("$")
        calcule = hashlib.scrypt(mot_de_passe.encode(), salt=base64.b64decode(sel), n=_N, r=_R, p=_P, dklen=32)
        return hmac.compare_digest(calcule, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def mot_de_passe_valide(mdp):
    """None si valide, sinon le message d'erreur."""
    if len(mdp) < 10:
        return "Le mot de passe doit contenir au moins 10 caractères."
    if mdp.isalpha() or mdp.isdigit():
        return "Le mot de passe doit mélanger lettres et chiffres (ou symboles)."
    return None


# --------------------------------------------------------------------------- #
# Session et utilisateur courant
# --------------------------------------------------------------------------- #
class NonConnecte(Exception):
    """Levée quand une page protégée est demandée sans session : redirection vers la connexion."""


def utilisateur_courant(request: Request, db: SessionDB = Depends(session_db)) -> Utilisateur:
    uid = request.session.get("uid")
    u = db.get(Utilisateur, uid) if uid else None
    if u is None or not u.actif:
        request.session.clear()
        raise NonConnecte()
    if u.doit_changer_mdp and request.url.path not in ("/mon-compte", "/deconnexion"):
        raise NonConnecte("changer_mdp")
    return u


def exiger(role_minimum):
    """Dépendance : l'utilisateur doit avoir au moins ce rôle."""
    def controle(u: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
        if not u.peut(role_minimum):
            raise HTTPException(403, "Vous n'avez pas les droits nécessaires pour cette action.")
        return u
    return controle


# --------------------------------------------------------------------------- #
# CSRF : un jeton par session, vérifié sur chaque formulaire POST
# --------------------------------------------------------------------------- #
def jeton_csrf(request: Request):
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


async def verifier_csrf(request: Request):
    if request.method != "POST":
        return
    formulaire = await request.form()
    envoye = formulaire.get("csrf") or request.headers.get("X-CSRF-Token")
    if not envoye or not hmac.compare_digest(str(envoye), request.session.get("csrf", "")):
        raise HTTPException(400, "Formulaire expiré : rechargez la page et recommencez.")

"""Mots de passe, session, contrôle des rôles et protection CSRF."""
import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as SessionDB

from . import config
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


# Pages accessibles tant que le compte doit encore être régularisé (mot de passe provisoire, 2FA obligatoire)
PAGES_REGULARISATION = ("/mon-compte", "/mon-compte/2fa/preparer", "/mon-compte/2fa/activer", "/deconnexion")


def ouvrir_session(request: Request, u: Utilisateur):
    """Session authentifiée : l'identifiant et la version de session (changée = session invalidée)."""
    request.session.clear()
    request.session["uid"], request.session["vs"] = u.id, u.version_session


def utilisateur_session(request: Request, db) -> Utilisateur | None:
    """Utilisateur de la session si elle est toujours valide (compte actif, version de session inchangée)."""
    uid = request.session.get("uid")
    if not uid:
        return None  # visiteur non connecté : on conserve la session (connexion en attente de code, jeton CSRF)
    u = db.get(Utilisateur, uid)
    if u is None or not u.actif or request.session.get("vs") != u.version_session:
        request.session.clear()  # session périmée (compte désactivé, mot de passe changé…)
        return None
    return u


def utilisateur_courant(request: Request, db: SessionDB = Depends(session_db)) -> Utilisateur:
    u = utilisateur_session(request, db)
    if u is None:
        raise NonConnecte()
    if request.url.path not in PAGES_REGULARISATION:
        if u.doit_changer_mdp:
            raise NonConnecte("changer_mdp")
        if u.role in config.EXIGER_2FA_ROLES and not u.totp_actif:
            raise NonConnecte("activer_2fa")
    return u


# --------------------------------------------------------------------------- #
# Protection contre la force brute
# --------------------------------------------------------------------------- #
class LimiteurTentatives:
    """Fenêtre glissante d'échecs par clé (ici l'adresse IP). En mémoire : l'application tourne avec un seul
    processus web ; le verrouillage par compte, lui, est stocké en base."""

    def __init__(self, maximum, fenetre_secondes, horloge=time.monotonic):
        self.maximum, self.fenetre, self.horloge = maximum, fenetre_secondes, horloge
        self.echecs = defaultdict(deque)

    def _purger(self, cle):
        file, limite = self.echecs[cle], self.horloge() - self.fenetre
        while file and file[0] < limite:
            file.popleft()
        return file

    def bloque(self, cle):
        return len(self._purger(cle)) >= self.maximum

    def echec(self, cle):
        self._purger(cle).append(self.horloge())

    def reinitialiser(self, cle):
        self.echecs.pop(cle, None)


limiteur_ip = LimiteurTentatives(config.LIMITE_ECHECS_IP, config.FENETRE_ECHECS_IP_MINUTES * 60)


def compte_verrouille(u: Utilisateur, maintenant=None):
    return bool(u.bloque_jusqua and u.bloque_jusqua > (maintenant or datetime.now()))


def enregistrer_echec(u: Utilisateur, maintenant=None):
    """Échec d'authentification sur un compte existant : verrouillage temporaire au-delà du seuil."""
    maintenant = maintenant or datetime.now()
    u.echecs_connexion = (u.echecs_connexion or 0) + 1
    if u.echecs_connexion >= config.VERROUILLAGE_ECHECS:
        u.bloque_jusqua = maintenant + timedelta(minutes=config.VERROUILLAGE_MINUTES)
        u.echecs_connexion = 0
        return True  # vient d'être verrouillé
    return False


def adresse_ip(request: Request):
    return request.client.host if request.client else "inconnue"


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

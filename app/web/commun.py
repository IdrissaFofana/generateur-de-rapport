"""Outils communs aux pages : gabarits, messages flash, redirections."""
import os
from datetime import date

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..modeles import ROLES, TYPES_EXPORT
from ..moteur.outils import MOIS_FR, fmt_mois
from ..securite import jeton_csrf

gabarits = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))
gabarits.env.globals.update(ROLES=ROLES, TYPES_EXPORT=TYPES_EXPORT, MOIS_FR=MOIS_FR, fmt_mois=fmt_mois)


def _fdatetime(d):
    return d.strftime("%d/%m/%Y %H:%M") if d else "—"


def _fdate(d):
    return d.strftime("%d/%m/%Y") if d else "—"


gabarits.env.filters.update(fdatetime=_fdatetime, fdate=_fdate)


def flash(request: Request, message, genre="succes"):
    request.session.setdefault("flash", []).append({"message": message, "genre": genre})


def page(request: Request, nom, utilisateur=None, **contexte):
    messages = request.session.pop("flash", [])
    return gabarits.TemplateResponse(request, nom, {
        "utilisateur": utilisateur, "csrf": jeton_csrf(request), "messages": messages, **contexte})


def rediriger(url):
    return RedirectResponse(url, status_code=303)


def mois_courant():
    """Mois traité par défaut : le mois en cours à partir du 25, sinon le précédent."""
    auj = date.today()
    if auj.day >= 25:
        return auj.year, auj.month
    return (auj.year - 1, 12) if auj.month == 1 else (auj.year, auj.month - 1)

"""Outils communs aux pages : gabarits, messages flash, redirections."""
import os

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import func, select

from ..db import Session
from ..modeles import ROLES, TYPES_EXPORT, Alerte
from ..services import INDICATEURS_SUIVIS, MOIS_COURTS
from ..moteur.outils import MOIS_FR, fmt_mois, mois_courant  # noqa: F401  (réexporté)
from ..securite import jeton_csrf

gabarits = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))
gabarits.env.globals.update(ROLES=ROLES, TYPES_EXPORT=TYPES_EXPORT, MOIS_FR=MOIS_FR, fmt_mois=fmt_mois,
                            INDICATEURS_SUIVIS=INDICATEURS_SUIVIS, MOIS_COURTS=MOIS_COURTS)


def _fdatetime(d):
    return d.strftime("%d/%m/%Y %H:%M") if d else "—"


def _fdate(d):
    return d.strftime("%d/%m/%Y") if d else "—"


gabarits.env.filters.update(fdatetime=_fdatetime, fdate=_fdate)


def flash(request: Request, message, genre="succes"):
    request.session.setdefault("flash", []).append({"message": message, "genre": genre})


def _alertes_ouvertes():
    with Session() as db:
        return db.scalar(select(func.count()).select_from(Alerte).where(Alerte.traitee.is_(False)))


def page(request: Request, nom, utilisateur=None, **contexte):
    messages = request.session.pop("flash", [])
    # Pages complètes seulement (pas les fragments htmx rafraîchis toutes les quelques secondes)
    ouvertes = _alertes_ouvertes() if utilisateur and not nom.startswith("_") else 0
    return gabarits.TemplateResponse(request, nom, {
        "utilisateur": utilisateur, "csrf": jeton_csrf(request), "messages": messages,
        "alertes_ouvertes": ouvertes, **contexte})


def rediriger(url):
    return RedirectResponse(url, status_code=303)

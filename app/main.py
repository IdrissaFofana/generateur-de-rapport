"""Application web « Rapports de sécurité ESAY ».

Lancement (développement) :  python -m app.main
Production : uvicorn app.main:app --host 127.0.0.1 --port $PORT  (derrière Nginx)
"""
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .analyses import arreter as arreter_analyses
from .analyses import reprendre_analyses
from .config import COOKIE_SECURISE, PORT, SECRET_KEY, STOCKAGE_DIR
from . import alertes, supervision
from .db import Session, migrer
from .securite import NonConnecte
from .web import admin, auth, bilans, depots, interventions, pilotage, rapports, service, tableau
from .web.commun import page, rediriger


def _alertes_au_demarrage():
    try:
        with Session() as db:
            alertes.evaluer_et_notifier(db, en_arriere_plan=False)
    except Exception:  # noqa: BLE001  (base indisponible, etc. : réessayé par la tâche quotidienne)
        logging.getLogger("rapports.alertes").exception("Évaluation des alertes au démarrage")


@asynccontextmanager
async def cycle_de_vie(_app):
    os.makedirs(STOCKAGE_DIR, exist_ok=True)
    migrer()
    reprendre_analyses()
    threading.Thread(target=_alertes_au_demarrage, daemon=True).start()
    yield
    arreter_analyses()


app = FastAPI(title="Rapports de sécurité ESAY", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=cycle_de_vie)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="rapports_esay",
                   max_age=12 * 3600, same_site="lax", https_only=COOKIE_SECURISE)
app.add_middleware(supervision.MiddlewareMetriques)
supervision.configurer_journalisation()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

for module in (auth, pilotage, tableau, depots, rapports, bilans, interventions, service, admin):
    app.include_router(module.routes)


@app.get("/metrics", include_in_schema=False)
def metriques(request: Request):
    """Métriques Prometheus, réservées au collecteur (jeton). Sans jeton configuré : la route n'existe pas (404)."""
    from fastapi.responses import PlainTextResponse
    from .config import METRIQUES_JETON
    if not METRIQUES_JETON:
        raise HTTPException(404)
    if not supervision.jeton_valide(request.headers.get("authorization")):
        raise HTTPException(401)
    with Session() as db:
        return PlainTextResponse(supervision.exposition(db), media_type="text/plain; version=0.0.4")


@app.exception_handler(NonConnecte)
def non_connecte(request: Request, exc: NonConnecte):
    # Compte à régulariser (mot de passe provisoire, double authentification obligatoire) : page « Mon compte »
    return rediriger("/mon-compte" if exc.args and exc.args[0] in ("changer_mdp", "activer_2fa") else "/connexion")


@app.exception_handler(HTTPException)
def erreur_http(request: Request, exc: HTTPException):
    titres = {403: "Accès refusé", 404: "Page introuvable"}
    reponse = page(request, "erreur.html", None, titre=titres.get(exc.status_code, "Erreur"), message=exc.detail)
    reponse.status_code = exc.status_code
    return reponse


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=True)

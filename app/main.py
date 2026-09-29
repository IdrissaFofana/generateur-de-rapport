"""Application web « Rapports de sécurité ESAY ».

Lancement (développement) :  python -m app.main
Production : uvicorn app.main:app --host 127.0.0.1 --port $PORT  (derrière Nginx)
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .analyses import arreter as arreter_analyses
from .analyses import reprendre_analyses
from .config import COOKIE_SECURISE, PORT, SECRET_KEY, STOCKAGE_DIR
from .db import creer_tables
from .securite import NonConnecte
from .web import admin, auth, depots, rapports, tableau
from .web.commun import page, rediriger


@asynccontextmanager
async def cycle_de_vie(_app):
    os.makedirs(STOCKAGE_DIR, exist_ok=True)
    creer_tables()
    reprendre_analyses()
    yield
    arreter_analyses()


app = FastAPI(title="Rapports de sécurité ESAY", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=cycle_de_vie)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="rapports_esay",
                   max_age=12 * 3600, same_site="lax", https_only=COOKIE_SECURISE)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

for module in (auth, tableau, depots, rapports, admin):
    app.include_router(module.routes)


@app.exception_handler(NonConnecte)
def non_connecte(request: Request, exc: NonConnecte):
    return rediriger("/mon-compte" if exc.args and exc.args[0] == "changer_mdp" else "/connexion")


@app.exception_handler(HTTPException)
def erreur_http(request: Request, exc: HTTPException):
    titres = {403: "Accès refusé", 404: "Page introuvable"}
    reponse = page(request, "erreur.html", None, titre=titres.get(exc.status_code, "Erreur"), message=exc.detail)
    reponse.status_code = exc.status_code
    return reponse


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=True)

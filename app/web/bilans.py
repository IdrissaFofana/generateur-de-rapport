"""Bilans trimestriels et semestriels : suivi par client et création à partir des mensuels validés."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import services
from ..db import session_db
from ..modeles import BROUILLON, Client, journaliser
from ..moteur import bilan as mbilan
from ..securite import exiger, verifier_csrf
from .commun import flash, page, rediriger

routes = APIRouter()
lecteur, operateur = exiger("lecteur"), exiger("operateur")


def _periode(periodicite, annee, numero):
    if periodicite not in mbilan.DUREES:
        raise HTTPException(400, "Type de bilan inconnu.")
    if annee is None or numero is None:
        return mbilan.periode_courante(periodicite)
    if not (2000 <= annee <= 2100 and 1 <= numero <= mbilan.nb_periodes(periodicite)):
        raise HTTPException(400, "Période invalide.")
    return annee, numero


def _lignes(db, periodicite, annee, numero):
    debut, _ = mbilan.bornes_periode(periodicite, annee, numero)
    attendus = len(mbilan.mois_de_periode(periodicite, annee, numero))
    lignes = []
    for c in db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)):
        valides = sorted(m["mois"] for m in services.mensuels_de_periode(db, c.id, periodicite, annee, numero))
        rapport = services.dernier_rapport(db, c.id, annee, debut.month, periodicite=periodicite)
        lignes.append({"client": c, "valides": valides, "attendus": attendus, "rapport": rapport,
                       "complet": len(valides) == attendus})
    return lignes


@routes.get("/bilans")
def bilans(request: Request, periodicite: str = "trimestriel", annee: int | None = None, numero: int | None = None,
           u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    annee, numero = _periode(periodicite, annee, numero)
    pa, pn = (annee - 1, mbilan.nb_periodes(periodicite)) if numero == 1 else (annee, numero - 1)
    sa, sn = (annee + 1, 1) if numero == mbilan.nb_periodes(periodicite) else (annee, numero + 1)
    return page(request, "bilans.html", u, periodicite=periodicite, annee=annee, numero=numero,
                libelle=mbilan.libelle_court(periodicite, annee, numero),
                libelle_long=mbilan.libelle_long(periodicite, annee, numero),
                mois=mbilan.mois_de_periode(periodicite, annee, numero), lignes=_lignes(db, periodicite, annee, numero),
                precedente=(pa, pn), suivante=(sa, sn), nb_periodes=mbilan.nb_periodes(periodicite))


def _creer(db, client, periodicite, annee, numero, u):
    debut, _ = mbilan.bornes_periode(periodicite, annee, numero)
    dernier = services.dernier_rapport(db, client.id, annee, debut.month, periodicite=periodicite)
    if dernier and dernier.statut == BROUILLON:
        return dernier, False
    r = services.creer_bilan(db, client, periodicite, annee, numero, u)
    journaliser(db, u, "création bilan", f"{client.nom} {mbilan.libelle_court(periodicite, annee, numero)} v{r.version}")
    return r, True


@routes.post("/bilans/creer", dependencies=[Depends(verifier_csrf)])
def creer(request: Request, client_id: int = Form(...), periodicite: str = Form(...), annee: int = Form(...),
          numero: int = Form(...), u=Depends(operateur), db: SessionDB = Depends(session_db)):
    annee, numero = _periode(periodicite, annee, numero)
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(404)
    if not services.mensuels_de_periode(db, client.id, periodicite, annee, numero):
        flash(request, f"Aucun rapport mensuel validé pour {client.nom} sur cette période : bilan impossible.", "erreur")
        return rediriger(f"/bilans?periodicite={periodicite}&annee={annee}&numero={numero}")
    r, nouveau = _creer(db, client, periodicite, annee, numero, u)
    db.commit()
    flash(request, f"Bilan {services.libelle_rapport(r)} v{r.version} créé en brouillon." if nouveau
                   else f"Un brouillon (v{r.version}) existe déjà pour cette période.", "succes" if nouveau else "info")
    return rediriger(f"/rapports/{r.id}")


@routes.post("/bilans/creer-tous", dependencies=[Depends(verifier_csrf)])
def creer_tous(request: Request, periodicite: str = Form(...), annee: int = Form(...), numero: int = Form(...),
               u=Depends(operateur), db: SessionDB = Depends(session_db)):
    """Crée le bilan de chaque client dont tous les mois de la période sont validés et qui n'a pas encore de bilan."""
    annee, numero = _periode(periodicite, annee, numero)
    crees = []
    for l in _lignes(db, periodicite, annee, numero):
        if l["complet"] and not l["rapport"]:
            _creer(db, l["client"], periodicite, annee, numero, u)
            crees.append(l["client"].nom)
    db.commit()
    flash(request, f"{len(crees)} bilan(s) créé(s) : {', '.join(crees)}." if crees
                   else "Aucun client complet sans bilan : rien à créer.", "succes" if crees else "info")
    return rediriger(f"/bilans?periodicite={periodicite}&annee={annee}&numero={numero}")

"""Tableau de bord et actions groupées sur les clients du mois."""
import io
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import services
from ..db import session_db
from ..modeles import BROUILLON, VALIDE, Client, journaliser
from ..moteur.outils import fmt_mois
from ..securite import exiger, verifier_csrf
from ..stockage import absolu
from .commun import flash, mois_courant, page, rediriger

routes = APIRouter()


def _etats(db, annee, mois):
    clients = db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all()
    hebdos = services.hebdos_du_mois(db, annee, mois)
    return [services.etat_client(db, c, annee, mois, hebdos) for c in clients]


def _contexte(db, annee, mois):
    etats = _etats(db, annee, mois)
    return {"etats": etats, "annee": annee, "mois": mois, "en_cours": any(e["en_cours"] for e in etats)}


def _verifier_mois(annee, mois):
    if not (2000 <= annee <= 2100 and 1 <= mois <= 12):
        raise HTTPException(400, "Période invalide.")


@routes.get("/production")
def tableau(request: Request, annee: int | None = None, mois: int | None = None,
            u=Depends(exiger("lecteur")), db: SessionDB = Depends(session_db)):
    if not (annee and mois and 1 <= mois <= 12):
        annee, mois = mois_courant()
    return page(request, "tableau.html", u, **_contexte(db, annee, mois))


@routes.get("/tableau/liste")
def tableau_liste(request: Request, annee: int, mois: int, u=Depends(exiger("lecteur")),
                  db: SessionDB = Depends(session_db)):
    return page(request, "_tableau_liste.html", u, **_contexte(db, annee, mois))


@routes.post("/tableau/brouillons", dependencies=[Depends(verifier_csrf)])
def creer_brouillons(request: Request, annee: int = Form(...), mois: int = Form(...), partiels: bool = Form(False),
                     u=Depends(exiger("operateur")), db: SessionDB = Depends(session_db)):
    """Crée le brouillon de chaque client « Prêt » (et « Partiel » si demandé) qui n'a pas encore de rapport."""
    _verifier_mois(annee, mois)
    retenus = ("Prêt", "Partiel") if partiels else ("Prêt",)
    crees = []
    for e in _etats(db, annee, mois):
        if e["etat"] in retenus and not e["rapport"]:
            r = services.creer_brouillon(db, e["client"], annee, mois, u)
            journaliser(db, u, "création brouillon", f"{e['client'].nom} {mois:02d}/{annee} v{r.version} (groupée)")
            crees.append(e["client"].nom)
    db.commit()
    if crees:
        flash(request, f"{len(crees)} brouillon(s) créé(s) : {', '.join(crees)}.")
    else:
        flash(request, "Aucun client éligible : aucun brouillon créé.", "info")
    return rediriger(f"/production?annee={annee}&mois={mois}")


@routes.post("/tableau/actualiser", dependencies=[Depends(verifier_csrf)])
def actualiser_brouillons(request: Request, annee: int = Form(...), mois: int = Form(...),
                          u=Depends(exiger("operateur")), db: SessionDB = Depends(session_db)):
    """Recalcule les chiffres de tous les brouillons du mois (textes conservés)."""
    _verifier_mois(annee, mois)
    noms = []
    for e in _etats(db, annee, mois):
        r = e["rapport"]
        if r and r.statut == BROUILLON:
            services.actualiser_brouillon(db, r)
            journaliser(db, u, "actualisation brouillon", f"{r.client.nom} {mois:02d}/{annee} v{r.version} (groupée)")
            noms.append(r.client.nom)
    db.commit()
    flash(request, f"Chiffres recalculés pour {len(noms)} brouillon(s) : {', '.join(noms)}." if noms
                   else "Aucun brouillon à actualiser pour ce mois.", "succes" if noms else "info")
    return rediriger(f"/production?annee={annee}&mois={mois}")


@routes.post("/tableau/mettre-a-jour", dependencies=[Depends(verifier_csrf)])
def mettre_a_jour_valides(request: Request, annee: int = Form(...), mois: int = Form(...),
                          u=Depends(exiger("validateur")), db: SessionDB = Depends(session_db)):
    """Pour chaque client dont le rapport du mois est validé : nouvelle version en brouillon, entièrement régénérée."""
    from .rapports import mettre_a_jour_rapport
    _verifier_mois(annee, mois)
    noms = []
    for e in _etats(db, annee, mois):
        r = e["rapport"]
        if r and r.statut == VALIDE:
            mettre_a_jour_rapport(db, r, u)
            noms.append(r.client.nom)
    db.commit()
    flash(request, f"{len(noms)} rapport(s) mis à jour en nouvelle version brouillon : {', '.join(noms)}. "
                   "Relisez-les puis validez-les." if noms else "Aucun rapport validé à mettre à jour pour ce mois.",
          "succes" if noms else "info")
    return rediriger(f"/production?annee={annee}&mois={mois}")


@routes.get("/tableau/pdf-valides.zip")
def pdf_valides(annee: int, mois: int, u=Depends(exiger("lecteur")), db: SessionDB = Depends(session_db)):
    """Archive ZIP des PDF validés du mois (dernière version validée de chaque client)."""
    _verifier_mois(annee, mois)
    tampon = io.BytesIO()
    nb = 0
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
        for e in _etats(db, annee, mois):
            r = services.dernier_rapport(db, e["client"].id, annee, mois, VALIDE)
            if r and r.pdf:
                zf.write(absolu(r.pdf), services.nom_fichier_rapport(r))
                nb += 1
    if not nb:
        raise HTTPException(404, "Aucun rapport validé pour ce mois.")
    journaliser(db, u, "téléchargement groupé", f"{nb} PDF validé(s) {mois:02d}/{annee}")
    db.commit()
    nom = f"Rapports mensuels sécurité - {fmt_mois(annee, mois)}.zip"
    return Response(tampon.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"})

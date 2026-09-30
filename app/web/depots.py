"""Dépôt des rapports hebdomadaires MDR et des exports KSC, fiche client-mois."""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import analyses, services
from ..rendu import courbes
from ..db import session_db
from ..modeles import Client, ExportKsc, Hebdo, Rapport, journaliser
from ..moteur.outils import bornes_mois
from ..securite import exiger, verifier_csrf
from ..stockage import DepotInvalide, absolu, enregistrer, lire_pdf, supprimer
from .commun import flash, mois_courant, page, rediriger

routes = APIRouter()
lecteur, operateur = exiger("lecteur"), exiger("operateur")


def _mois_valide(annee, mois):
    if not (2020 <= annee <= 2100 and 1 <= mois <= 12):
        raise HTTPException(404)


def _client(db, cid):
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(404)
    return client


# --------------------------------------------------------------------------- #
# Rapports hebdomadaires MDR
# --------------------------------------------------------------------------- #
def _contexte_hebdos(db, annee, mois):
    hebdos = db.scalars(select(Hebdo).order_by(Hebdo.debut.desc().nulls_first(), Hebdo.depose_le.desc())).all()
    clients = db.scalars(select(Client).where(Client.actif.is_(True), Client.avec_mdr.is_(True))
                         .order_by(Client.nom)).all()
    donnees_mois = services.hebdos_du_mois(db, annee, mois)
    couvertures = [(c, services.couverture_mdr(c, annee, mois, donnees_mois)) for c in clients]
    debuts = [h.debut for h in hebdos if h.debut]
    doublons = {d for d in debuts if debuts.count(d) > 1}
    return {"hebdos": hebdos, "couvertures": couvertures, "annee": annee, "mois": mois, "doublons": doublons,
            "en_cours": any(h.statut in ("en_attente", "en_cours") for h in hebdos)}


@routes.get("/hebdos")
def hebdos(request: Request, annee: int | None = None, mois: int | None = None,
           u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    if not (annee and mois):
        annee, mois = mois_courant()
    _mois_valide(annee, mois)
    return page(request, "hebdos.html", u, **_contexte_hebdos(db, annee, mois))


@routes.get("/hebdos/liste")
def hebdos_liste(request: Request, annee: int, mois: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    """Fragment rafraîchi automatiquement pendant les analyses."""
    return page(request, "_hebdos_liste.html", u, **_contexte_hebdos(db, annee, mois))


@routes.post("/hebdos", dependencies=[Depends(verifier_csrf)])
async def deposer_hebdos(request: Request, fichiers: list[UploadFile] = File(...), annee: int = 0, mois: int = 0,
                         u=Depends(operateur), db: SessionDB = Depends(session_db)):
    nouveaux = []
    for f in fichiers:
        if not f.filename:
            continue
        try:
            contenu = await lire_pdf(f)
        except DepotInvalide as e:
            flash(request, str(e), "erreur")
            continue
        chemin, h = enregistrer(contenu, "hebdos")
        existant = db.scalar(select(Hebdo).where(Hebdo.empreinte == h))
        if existant:
            flash(request, f"« {f.filename} » a déjà été déposé (le {existant.depose_le:%d/%m/%Y}).", "info")
            continue
        hebdo = Hebdo(fichier=f.filename, chemin=chemin, empreinte=h, depose_par_id=u.id)
        db.add(hebdo)
        db.flush()
        nouveaux.append(hebdo.id)
        journaliser(db, u, "dépôt hebdo MDR", f.filename)
    db.commit()
    for hid in nouveaux:
        analyses.planifier_hebdo(hid)
    if nouveaux:
        flash(request, f"{len(nouveaux)} fichier(s) déposé(s) : analyse en cours.")
    return rediriger(f"/hebdos?annee={annee}&mois={mois}" if annee else "/hebdos")


@routes.post("/hebdos/{hid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_hebdo(request: Request, hid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    h = db.get(Hebdo, hid)
    if h is None:
        raise HTTPException(404)
    if h.statut == "en_cours":
        flash(request, "Analyse en cours : réessayez dans un instant.", "erreur")
        return rediriger("/hebdos")
    supprimer(h.chemin)
    db.delete(h)
    journaliser(db, u, "suppression hebdo MDR", h.fichier)
    db.commit()
    flash(request, f"« {h.fichier} » supprimé.")
    return rediriger("/hebdos")


# --------------------------------------------------------------------------- #
# Fiche client pour un mois : exports KSC et aperçu
# --------------------------------------------------------------------------- #
def _contexte_client(db, client, annee, mois):
    exports = services.exports_du_mois(db, client.id, annee, mois)
    hebdos = services.hebdos_du_mois(db, annee, mois) if client.avec_mdr else []
    rapports = db.scalars(select(Rapport).where(Rapport.client_id == client.id, Rapport.periodicite == "mensuel",
                                                Rapport.annee == annee, Rapport.mois == mois)
                          .order_by(Rapport.version.desc())).all()
    debut, fin = bornes_mois(annee, mois)
    return {"client": client, "annee": annee, "mois": mois, "exports": exports,
            "retenus": services.exports_retenus(exports), "mdr": services.couverture_mdr(client, annee, mois, hebdos),
            "rapports": rapports, "debut": debut, "fin": fin,
            "en_cours": any(e.statut in ("en_attente", "en_cours") for e in exports)}


def _contexte_evolution(db, client, annee, mois):
    """Courbes des 12 derniers mois validés, jusqu'au mois affiché inclus."""
    points = services.historique(db, client.id, annee, mois, nb_mois=12)
    suivis = [(cle, titre) for cle, titre in services.INDICATEURS_SUIVIS
              if any(p["indicateurs"].get(cle) is not None for p in points)]
    return {"historique": points,
            "courbes": [{"titre": titre, "svg": courbes.mini_courbe(points, cle), "variation": courbes.variation(points, cle)}
                        for cle, titre in suivis]}


@routes.get("/clients/{cid}/aller")
def aller(cid: int, annee: int, mois: int, u=Depends(lecteur)):
    _mois_valide(annee, mois)
    return rediriger(f"/clients/{cid}/{annee}/{mois}")


@routes.get("/clients/{cid}/{annee}/{mois}")
def fiche_mois(request: Request, cid: int, annee: int, mois: int, u=Depends(lecteur),
               db: SessionDB = Depends(session_db)):
    _mois_valide(annee, mois)
    client = _client(db, cid)
    return page(request, "client_mois.html", u, **_contexte_client(db, client, annee, mois),
                **_contexte_evolution(db, client, annee, mois))


@routes.get("/clients/{cid}/{annee}/{mois}/exports")
def fiche_exports(request: Request, cid: int, annee: int, mois: int, u=Depends(lecteur),
                  db: SessionDB = Depends(session_db)):
    return page(request, "_exports_liste.html", u, **_contexte_client(db, _client(db, cid), annee, mois))


@routes.get("/clients/{cid}/{annee}/{mois}/apercu")
def apercu(request: Request, cid: int, annee: int, mois: int, u=Depends(lecteur),
           db: SessionDB = Depends(session_db)):
    """Chiffres extraits et niveau de risque calculé, avant génération."""
    client = _client(db, cid)
    d = services.consolider_client(db, client, annee, mois)
    return page(request, "_apercu.html", u, d=d, client=client)


@routes.post("/clients/{cid}/{annee}/{mois}/exports", dependencies=[Depends(verifier_csrf)])
async def deposer_exports(request: Request, cid: int, annee: int, mois: int, fichiers: list[UploadFile] = File(...),
                          u=Depends(operateur), db: SessionDB = Depends(session_db)):
    _mois_valide(annee, mois)
    client = _client(db, cid)
    nouveaux = []
    for f in fichiers:
        if not f.filename:
            continue
        try:
            contenu = await lire_pdf(f)
        except DepotInvalide as e:
            flash(request, str(e), "erreur")
            continue
        chemin, h = enregistrer(contenu, "ksc", str(client.id), f"{annee}-{mois:02d}")
        if db.scalar(select(ExportKsc).where(ExportKsc.client_id == client.id, ExportKsc.annee == annee,
                                             ExportKsc.mois == mois, ExportKsc.empreinte == h)):
            flash(request, f"« {f.filename} » a déjà été déposé pour ce mois.", "info")
            continue
        export = ExportKsc(client_id=client.id, annee=annee, mois=mois, fichier=f.filename, chemin=chemin,
                           empreinte=h, depose_par_id=u.id)
        db.add(export)
        db.flush()
        nouveaux.append(export.id)
        journaliser(db, u, "dépôt export KSC", f"{client.nom} {mois:02d}/{annee} : {f.filename}")
    db.commit()
    for eid in nouveaux:
        analyses.planifier_export(eid)
    if nouveaux:
        flash(request, f"{len(nouveaux)} export(s) déposé(s) : analyse en cours (quelques minutes pour les gros fichiers).")
    return rediriger(f"/clients/{cid}/{annee}/{mois}")


@routes.post("/exports/{eid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_export(request: Request, eid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    e = db.get(ExportKsc, eid)
    if e is None:
        raise HTTPException(404)
    retour = f"/clients/{e.client_id}/{e.annee}/{e.mois}"
    if e.statut == "en_cours":
        flash(request, "Analyse en cours : réessayez dans un instant.", "erreur")
        return rediriger(retour)
    autres = db.scalar(select(ExportKsc).where(ExportKsc.chemin == e.chemin, ExportKsc.id != e.id))
    if not autres:
        supprimer(e.chemin)
    db.delete(e)
    # L'export précédent du même type redevient celui en vigueur
    if e.type and not e.remplace:
        precedent = db.scalar(select(ExportKsc).where(
            ExportKsc.client_id == e.client_id, ExportKsc.annee == e.annee, ExportKsc.mois == e.mois,
            ExportKsc.type == e.type, ExportKsc.id != e.id, ExportKsc.statut == "ok")
            .order_by(ExportKsc.depose_le.desc()))
        if precedent:
            precedent.remplace = False
    journaliser(db, u, "suppression export KSC", e.fichier)
    db.commit()
    flash(request, f"« {e.fichier} » supprimé.")
    return rediriger(retour)


# --------------------------------------------------------------------------- #
# Téléchargement des fichiers d'origine
# --------------------------------------------------------------------------- #
@routes.get("/fichiers/hebdo/{hid}")
def fichier_hebdo(hid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    h = db.get(Hebdo, hid)
    if h is None:
        raise HTTPException(404)
    return FileResponse(absolu(h.chemin), media_type="application/pdf", filename=h.fichier)


@routes.get("/fichiers/export/{eid}")
def fichier_export(eid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    e = db.get(ExportKsc, eid)
    if e is None:
        raise HTTPException(404)
    return FileResponse(absolu(e.chemin), media_type="application/pdf", filename=e.fichier)

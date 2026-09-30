"""Pilotage : vue d'ensemble du portefeuille, parc d'un client, contrats et licences, alertes."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessionDB

from .. import alertes as malertes
from .. import config, parc, vue_ensemble
from ..db import session_db
from ..modeles import NIVEAUX_ALERTE, PRODUITS, Alerte, Client, Contrat, journaliser
from ..moteur.outils import mois_courant
from ..services import MOIS_COURTS
from ..rendu import courbes
from ..securite import exiger, verifier_csrf
from .commun import flash, page, rediriger

routes = APIRouter()
lecteur, operateur, admin = exiger("lecteur"), exiger("operateur"), exiger("admin")


def _mois(annee, mois, defaut):
    if annee and mois and 1 <= mois <= 12 and 2000 <= annee <= 2100:
        return annee, mois
    return defaut


# --------------------------------------------------------------------------- #
# Vue d'ensemble
# --------------------------------------------------------------------------- #
@routes.get("/")
def vue(request: Request, annee: int | None = None, mois: int | None = None, client: str = "", profil: str = "",
        u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    annee, mois = _mois(annee, mois, vue_ensemble.dernier_mois_valide(db))
    client_id = int(client) if client.isdigit() else None
    profil = profil if profil in vue_ensemble.PROFILS else None
    s = vue_ensemble.statistiques(db, annee, mois, client_id=client_id, profil=profil)
    me = s["menaces_evolution"]
    courbes_portefeuille = [
        {"titre": titre, "svg": courbes.mini_courbe(s["tendances"], cle), "variation": courbes.variation(s["tendances"], cle)}
        for cle, titre in [("appareils_critiques", "Appareils en état critique"), ("vulnerabilites_critiques", "Vulnérabilités critiques"),
                           ("detections", "Menaces détectées"), ("incidents_mdr", "Incidents MDR")]]
    filtres = "&".join(f"{k}={v}" for k, v in (("client", client_id), ("profil", profil)) if v)
    return page(request, "vue_ensemble.html", u, s=s, courbes_portefeuille=courbes_portefeuille,
                courbe_delais=courbes.mini_courbe(s["delais"], "delai"), CLASSES=vue_ensemble.CLASSES_RISQUE,
                courbes_menaces=[{"titre": x["libelle"], "svg": courbes.mini_courbe(me["points"], x["cle"]),
                                  "variation": courbes.variation(me["points"], x["cle"])} for x in me["series"]],
                PROFILS=vue_ensemble.PROFILS,
                filtres=filtres, MOIS_COURTS=MOIS_COURTS)


# --------------------------------------------------------------------------- #
# Parc d'un client
# --------------------------------------------------------------------------- #
@routes.get("/clients/{cid}/parc")
def parc_client(request: Request, cid: int, annee: int | None = None, mois: int | None = None,
                u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(404)
    annee, mois = _mois(annee, mois, mois_courant())
    return page(request, "parc.html", u, client=client, annee=annee, mois=mois, **parc.parc_client(db, client, annee, mois))


# --------------------------------------------------------------------------- #
# Contrats et licences
# --------------------------------------------------------------------------- #
@routes.get("/contrats")
def contrats(request: Request, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    clients = db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all()
    lignes = parc.contrats_avec_etat(db, clients, config.SEUIL_SOUS_UTILISATION)
    sans_contrat = [c for c in clients if not any(k.client_id == c.id for k, _ in lignes)]
    return page(request, "contrats.html", u, lignes=lignes, sans_contrat=sans_contrat, PRODUITS=PRODUITS,
                seuil=config.SEUIL_SOUS_UTILISATION)


def _date(texte):
    try:
        return date.fromisoformat(texte) if texte else None
    except ValueError:
        raise HTTPException(400, "Date invalide.")


@routes.post("/admin/clients/{cid}/contrats", dependencies=[Depends(verifier_csrf)])
@routes.post("/admin/contrats/{kid}", dependencies=[Depends(verifier_csrf)])
def enregistrer_contrat(request: Request, cid: int | None = None, kid: int | None = None, produit: str = Form(...),
                        reference: str = Form(""), licences: int = Form(0), debut: str = Form(""), echeance: str = Form(""),
                        notes: str = Form(""), actif: bool = Form(False), u=Depends(admin), db: SessionDB = Depends(session_db)):
    contrat = db.get(Contrat, kid) if kid else Contrat(client_id=cid)
    if contrat is None or (cid and db.get(Client, cid) is None):
        raise HTTPException(404)
    if produit not in PRODUITS or licences < 0:
        raise HTTPException(400, "Produit ou nombre de licences invalide.")
    contrat.produit, contrat.reference, contrat.licences = produit, reference.strip(), licences
    contrat.debut, contrat.echeance, contrat.notes = _date(debut), _date(echeance), notes.strip()
    contrat.actif = actif if kid else True
    if not kid:
        db.add(contrat)
    db.flush()
    journaliser(db, u, "modification contrat" if kid else "création contrat",
                f"{contrat.client.nom} {produit} {licences} licences, échéance {contrat.echeance or '—'}")
    db.commit()
    malertes.evaluer_et_notifier(db)
    flash(request, f"Contrat {produit} de {contrat.client.nom} enregistré.")
    return rediriger(f"/admin/clients/{contrat.client_id}#contrats")


@routes.post("/admin/contrats/{kid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_contrat(request: Request, kid: int, u=Depends(admin), db: SessionDB = Depends(session_db)):
    contrat = db.get(Contrat, kid)
    if contrat is None:
        raise HTTPException(404)
    cid, nom = contrat.client_id, contrat.client.nom
    journaliser(db, u, "suppression contrat", f"{nom} {contrat.produit} {contrat.reference}")
    db.delete(contrat)
    db.commit()
    flash(request, f"Contrat de {nom} supprimé.")
    return rediriger(f"/admin/clients/{cid}#contrats")


# --------------------------------------------------------------------------- #
# Alertes
# --------------------------------------------------------------------------- #
@routes.get("/alertes")
def liste_alertes(request: Request, etat: str = "ouvertes", type: str = "", client: int | None = None,
                  u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    requete = select(Alerte)
    if etat == "ouvertes":
        requete = requete.where(Alerte.traitee.is_(False))
    elif etat == "traitees":
        requete = requete.where(Alerte.traitee.is_(True))
    if type in malertes.TYPES:
        requete = requete.where(Alerte.type == type)
    if client:
        requete = requete.where(Alerte.client_id == client)
    lignes = db.scalars(requete.order_by(Alerte.traitee, Alerte.cree_le.desc()).limit(300)).all()
    return page(request, "alertes.html", u, lignes=lignes, etat=etat, type_=type, client_id=client,
                clients=db.scalars(select(Client).order_by(Client.nom)).all(), TYPES=malertes.TYPES, NIVEAUX=NIVEAUX_ALERTE,
                email=malertes.email_configure(), teams=bool(config.TEAMS_WEBHOOK),
                destinataires=config.ALERTES_EMAILS, destinataires_resume=config.RESUME_EMAILS)


@routes.post("/alertes/traiter", dependencies=[Depends(verifier_csrf)])
async def traiter(request: Request, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    f = await request.form()
    ids = [int(x) for x in f.getlist("ids") if str(x).isdigit()]
    rouvrir = f.get("rouvrir") == "1"
    for a in db.scalars(select(Alerte).where(Alerte.id.in_(ids))):
        a.traitee, a.traitee_par_id, a.traitee_le = (False, None, None) if rouvrir else (True, u.id, datetime.now())
    journaliser(db, u, "alertes rouvertes" if rouvrir else "alertes traitées", f"{len(ids)} alerte(s)")
    db.commit()
    flash(request, f"{len(ids)} alerte(s) {'rouverte(s)' if rouvrir else 'marquée(s) comme traitée(s)'}.")
    return rediriger(f.get("retour") or "/alertes")


@routes.post("/alertes/evaluer", dependencies=[Depends(verifier_csrf)])
def evaluer(request: Request, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    nouvelles = malertes.evaluer_et_notifier(db)
    flash(request, f"{len(nouvelles)} nouvelle(s) alerte(s)." if nouvelles else "Aucune nouvelle alerte.",
          "succes" if nouvelles else "info")
    return rediriger("/alertes")


@routes.get("/alertes/resume", response_class=HTMLResponse)
def apercu_resume(u=Depends(admin), db: SessionDB = Depends(session_db)):
    return HTMLResponse(malertes.html_resume(malertes.contenu_resume(db)))


@routes.post("/alertes/resume", dependencies=[Depends(verifier_csrf)])
def envoyer_resume(request: Request, u=Depends(admin), db: SessionDB = Depends(session_db)):
    envoye, message = malertes.envoyer_resume(db, forcer=True)
    if envoye:
        journaliser(db, u, "résumé hebdomadaire envoyé", message)
        db.commit()
    flash(request, message, "succes" if envoye else "erreur")
    return rediriger("/alertes")


@routes.post("/alertes/test", dependencies=[Depends(verifier_csrf)])
def tester_notifications(request: Request, u=Depends(admin), db: SessionDB = Depends(session_db)):
    essai = Alerte(cle="essai", type="info", niveau="info", titre="Message d'essai de la plateforme",
                   detail=f"Envoyé par {u.nom} pour vérifier la configuration des notifications.", lien="/alertes")
    if not malertes.notifications_configurees():
        flash(request, "Aucun canal configuré : renseignez SMTP_* et ALERTES_EMAILS, ou TEAMS_WEBHOOK, dans le fichier .env.", "erreur")
    else:
        erreurs = malertes.notifier([essai])
        flash(request, "Échec : " + "; ".join(erreurs) if erreurs else "Message d'essai envoyé.", "erreur" if erreurs else "succes")
    return rediriger("/alertes")


def nb_alertes_ouvertes(db):
    return db.scalar(select(func.count()).select_from(Alerte).where(Alerte.traitee.is_(False)))

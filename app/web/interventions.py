"""Rapports d'intervention : saisie au retour, bibliothèque d'actions, validation, envoi au client, historique."""
import json
from datetime import date, datetime, time
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessionDB

from .. import alertes
from .. import interventions as mi
from ..db import session_db
from ..modeles import (BROUILLON, MODES_INTERVENTION, STATUTS_INTERVENTION, TYPES_INTERVENTION, VALIDE, Client,
                       ElementBibliotheque, ImportEnAttente, Intervention, Utilisateur, journaliser)
from ..securite import exiger, verifier_csrf
from ..stockage import DepotInvalide, absolu, lire_fichier, type_mime
from ..stockage import supprimer as supprimer_fichier
from .commun import flash, page, rediriger

routes = APIRouter()
lecteur, operateur, validateur = exiger("lecteur"), exiger("operateur"), exiger("validateur")


def _intervention(db, iid):
    i = db.get(Intervention, iid)
    if i is None:
        raise HTTPException(404)
    return i


def _date(texte, defaut=None):
    try:
        return date.fromisoformat(texte) if texte else defaut
    except ValueError:
        raise HTTPException(400, "Date invalide.")


def _heure(texte):
    try:
        return time.fromisoformat(texte) if texte else None
    except ValueError:
        raise HTTPException(400, "Heure invalide.")


def bibliotheque_json(db):
    """{type: {"action": [...], "recommandation": [...]}} des éléments actifs, pour le panneau du formulaire."""
    donnees = {t: {"action": [], "recommandation": []} for t in TYPES_INTERVENTION}
    for e in db.scalars(select(ElementBibliotheque).where(ElementBibliotheque.actif.is_(True))
                        .order_by(ElementBibliotheque.ordre, ElementBibliotheque.id)):
        cibles = TYPES_INTERVENTION if e.type_intervention == "tous" else [e.type_intervention]
        for t in cibles:
            if t in donnees:
                donnees[t][e.genre].append({"categorie": e.categorie or "Autres", "libelle": e.libelle})
    return donnees


# --------------------------------------------------------------------------- #
# Liste et création
# --------------------------------------------------------------------------- #
@routes.get("/interventions")
def liste(request: Request, client: str = "", type: str = "", statut: str = "",
          u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    requete = select(Intervention)
    if client.isdigit():
        requete = requete.where(Intervention.client_id == int(client))
    if type in TYPES_INTERVENTION:
        requete = requete.where(Intervention.type == type)
    if statut in ("brouillon", "valide", "envoye"):
        requete = (requete.where(Intervention.envoye_le.is_not(None)) if statut == "envoye"
                   else requete.where(Intervention.statut == statut, Intervention.envoye_le.is_(None)))
    if not u.peut("operateur"):
        requete = requete.where(Intervention.statut == VALIDE)
    lignes = db.scalars(requete.order_by(Intervention.date_debut.desc(), Intervention.id.desc()).limit(300)).all()
    return page(request, "interventions.html", u, lignes=lignes, TYPES=TYPES_INTERVENTION, filtre={"client": client, "type": type, "statut": statut},
                clients=db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all())


@routes.post("/interventions", dependencies=[Depends(verifier_csrf)])
def creer(request: Request, client_id: int = Form(...), type: str = Form(...), date_debut: str = Form(""),
          u=Depends(operateur), db: SessionDB = Depends(session_db)):
    client = db.get(Client, client_id)
    if client is None or type not in TYPES_INTERVENTION:
        raise HTTPException(400, "Client ou type d'intervention invalide.")
    i = mi.creer(db, client, type, u, _date(date_debut, date.today()))
    journaliser(db, u, "création intervention", f"{i.numero} ({i.libelle_type})")
    db.commit()
    flash(request, f"Rapport {i.numero} créé : complétez-le puis validez-le.")
    return rediriger(f"/interventions/{i.id}")


# --------------------------------------------------------------------------- #
# Import d'anciens rapports (déclaré avant /interventions/{iid})
# --------------------------------------------------------------------------- #
@routes.get("/interventions/importer")
def importer_form(request: Request, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a_verifier = db.scalars(select(Intervention).where(Intervention.a_verifier.is_(True)).order_by(Intervention.cree_le.desc())).all()
    importes = db.scalar(select(func.count()).select_from(Intervention).where(Intervention.source == "import", Intervention.a_verifier.is_(False)))
    attentes = db.scalars(select(ImportEnAttente).order_by(ImportEnAttente.cree_le.desc())).all()
    return page(request, "import_interventions.html", u, a_verifier=a_verifier, importes=importes,
                attentes=[a for a in attentes if a.motif == "client"], doublons=[a for a in attentes if a.motif == "doublon"],
                clients=db.scalars(select(Client).where(Client.actif.is_(True)).order_by(Client.nom)).all())


@routes.post("/interventions/importer", dependencies=[Depends(verifier_csrf)])
async def importer(request: Request, fichiers: list[UploadFile] = File(...), client_impose: str = Form(""),
                   u=Depends(operateur), db: SessionDB = Depends(session_db)):
    """Le client choisi à la main n'est appliqué qu'à un fichier seul : dans un lot, un document non reconnu est mis
    en attente plutôt que rattaché d'office à un client qui n'est peut-être pas le sien."""
    impose = int(client_impose) if client_impose.isdigit() and len(fichiers) == 1 else None
    if client_impose.isdigit() and len(fichiers) > 1:
        flash(request, "Plusieurs fichiers : le client choisi a été ignoré, chaque document est reconnu séparément.", "info")
    reussis, attente, doublons, erreurs = [], [], [], []
    for f in fichiers:
        try:
            contenu, extension = await lire_fichier(f, (".pdf", ".docx"))
            i, detail = mi.importer(db, contenu, extension, f.filename or "rapport", u, impose)
            db.flush()
            if i is None and detail.motif == "doublon":
                journaliser(db, u, "import en attente : doublon probable",
                            f"« {f.filename} » ressemble à {detail.doublon.numero} ({round(detail.similarite * 100)} %)")
                doublons.append(f"{f.filename} ≈ {detail.doublon.numero}")
                continue
            if i is None:
                journaliser(db, u, "import en attente de client", f"« {f.filename} »" + (f" (client écrit : {detail.nom_detecte})" if detail.nom_detecte else ""))
                attente.append(f.filename + (f" — client « {detail.nom_detecte} »" if detail.nom_detecte else ""))
                continue
            journaliser(db, u, "import intervention", f"{i.numero} depuis « {f.filename} »")
            reussis.append(f"{i.numero}" + (f" (à compléter : {', '.join(detail)})" if detail else ""))
        except (DepotInvalide, ValueError) as e:
            erreurs.append(f"{f.filename} : {e}")
        except Exception as e:  # noqa: BLE001  (document illisible)
            erreurs.append(f"{f.filename} : lecture impossible ({e.__class__.__name__})")
    db.commit()
    if reussis:
        flash(request, f"{len(reussis)} rapport(s) importé(s), à vérifier : {'; '.join(reussis)}.")
    if attente:
        flash(request, f"{len(attente)} rapport(s) d'un client non enregistré, en attente : {'; '.join(attente)}. "
                       "Créez le client ou rattachez-les ci-dessous.", "info")
    if doublons:
        flash(request, f"{len(doublons)} rapport(s) ressemblent à une intervention déjà enregistrée : {'; '.join(doublons)}. "
                       "Importez-les quand même ou annulez ci-dessous.", "info")
    if erreurs:
        flash(request, "Non importé(s) : " + " · ".join(erreurs), "erreur")
    return rediriger("/interventions/importer")


def _attente(db, aid):
    a = db.get(ImportEnAttente, aid)
    if a is None:
        raise HTTPException(404)
    return a


@routes.post("/interventions/attente/{aid}/rattacher", dependencies=[Depends(verifier_csrf)])
def rattacher_attente(request: Request, aid: int, client_id: int = Form(...), memoriser: bool = Form(False),
                      u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a, client = _attente(db, aid), db.get(Client, client_id)
    if client is None:
        raise HTTPException(400, "Client inconnu.")
    nom_detecte, nom_fichier = a.nom_detecte, a.nom_fichier
    if memoriser and nom_detecte and nom_detecte.lower() != client.nom.lower() \
            and nom_detecte.lower() not in [n.lower() for n in client.autres_noms or []]:
        client.autres_noms = [*(client.autres_noms or []), nom_detecte]  # reconnu automatiquement la prochaine fois
        journaliser(db, u, "autre nom client", f"{client.nom} : « {nom_detecte} »")
    i, _ = mi.resoudre_attente(db, a, client, u)
    if i is None:
        journaliser(db, u, "import en attente : doublon probable", f"« {nom_fichier} » ressemble à {a.doublon.numero} ({client.nom})")
        db.commit()
        flash(request, f"« {nom_fichier} » ressemble à {a.doublon.numero} chez {client.nom} : importez-le quand même ou annulez.", "info")
        return rediriger("/interventions/importer")
    journaliser(db, u, "import intervention", f"{i.numero} depuis « {nom_fichier} » (rattaché à {client.nom})")
    autres, _ = mi.reessayer_attentes(db, u) if memoriser else ([], [])
    db.commit()
    flash(request, f"« {nom_fichier} » rattaché à {client.nom} : {i.numero}, à vérifier."
                   + (f" {len(autres)} autre(s) rapport(s) en attente reconnu(s) du même coup." if autres else ""))
    return rediriger("/interventions/importer")


@routes.post("/interventions/attente/{aid}/accepter", dependencies=[Depends(verifier_csrf)])
def accepter_doublon(request: Request, aid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    """Doublon probable : l'utilisateur confirme qu'il s'agit bien d'une autre intervention."""
    a = _attente(db, aid)
    if a.motif != "doublon" or a.client is None:
        raise HTTPException(400, "Ce document n'est pas signalé comme doublon probable.")
    nom_fichier, ressemblance = a.nom_fichier, a.doublon.numero if a.doublon else "—"
    i, _ = mi.resoudre_attente(db, a, a.client, u, forcer=True)
    journaliser(db, u, "import intervention", f"{i.numero} depuis « {nom_fichier} » (importé malgré la ressemblance avec {ressemblance})")
    db.commit()
    flash(request, f"« {nom_fichier} » importé quand même : {i.numero}, à vérifier.")
    return rediriger("/interventions/importer")


@routes.post("/interventions/attente/{aid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_attente(request: Request, aid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a = _attente(db, aid)
    fichier, nom = a.fichier, a.nom_fichier
    doublon = a.motif == "doublon"
    journaliser(db, u, "import annulé (doublon probable)" if doublon else "import en attente supprimé", nom)
    db.delete(a)
    db.commit()
    supprimer_fichier(fichier)
    flash(request, f"Import de « {nom} » annulé." if doublon else f"« {nom} » retiré.")
    return rediriger("/interventions/importer")


@routes.get("/interventions/attente/{aid}/original")
def original_attente(aid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a = _attente(db, aid)
    return FileResponse(absolu(a.fichier), media_type=type_mime(a.fichier), filename=a.nom_fichier)


@routes.post("/interventions/{iid}/confirmer-import", dependencies=[Depends(verifier_csrf)])
def confirmer_import(request: Request, iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.source != "import" or i.statut != BROUILLON:
        raise HTTPException(400, "Ce rapport n'est pas un import en attente de vérification.")
    mi.confirmer_import(db, i, u)
    journaliser(db, u, "confirmation import intervention", i.numero)
    db.commit()
    flash(request, f"Import {i.numero} vérifié : il compte désormais dans les statistiques et la base de connaissances.")
    return rediriger(f"/interventions/{iid}")


@routes.get("/interventions/{iid}/original")
def original(iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if not i.fichier_source:
        raise HTTPException(404)
    return FileResponse(absolu(i.fichier_source), media_type=type_mime(i.fichier_source), filename=i.nom_fichier_source or "rapport")


@routes.post("/interventions/{iid}/dupliquer", dependencies=[Depends(verifier_csrf)])
def dupliquer(request: Request, iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    base = _intervention(db, iid)
    i = mi.creer(db, base.client, base.type, u, date.today(), base=base)
    journaliser(db, u, "création intervention", f"{i.numero} (suite de {base.numero})")
    db.commit()
    flash(request, f"Rapport {i.numero} créé à partir de {base.numero} (dates et résultat à compléter).")
    return rediriger(f"/interventions/{i.id}")


# --------------------------------------------------------------------------- #
# Saisie
# --------------------------------------------------------------------------- #
@routes.get("/interventions/{iid}")
def fiche(request: Request, iid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.statut != VALIDE and not u.peut("operateur"):
        raise HTTPException(403, "Seuls les rapports validés sont accessibles avec le rôle Lecteur.")
    modifiable = i.statut == BROUILLON and u.peut("operateur")
    utilisateurs = db.scalars(select(Utilisateur.nom).where(Utilisateur.actif.is_(True)).order_by(Utilisateur.nom)).all()
    return page(request, "intervention.html", u, i=i, modifiable=modifiable, TYPES=TYPES_INTERVENTION,
                MODES=MODES_INTERVENTION, STATUTS=STATUTS_INTERVENTION, utilisateurs=utilisateurs,
                bibliotheque=json.dumps(bibliotheque_json(db), ensure_ascii=False) if modifiable else "{}",
                email=alertes.email_configure())


def _liste(f, nom):
    return [v.strip() for v in f.getlist(nom)]


def _ajouter_bibliotheque(db, u, type_, genre, textes, drapeaux):
    """Éléments saisis à la main et cochés « ajouter à la bibliothèque »."""
    connus = {e.libelle.strip().lower() for e in db.scalars(select(ElementBibliotheque).where(
        ElementBibliotheque.type_intervention == type_, ElementBibliotheque.genre == genre))}
    ajoutes = 0
    for texte, drapeau in zip(textes, drapeaux):
        if drapeau == "1" and texte and texte.lower() not in connus:
            db.add(ElementBibliotheque(genre=genre, type_intervention=type_, categorie="Ajouts de l'équipe",
                                       libelle=texte, ordre=1000, cree_par_id=u.id))
            connus.add(texte.lower())
            ajoutes += 1
    return ajoutes


@routes.post("/interventions/{iid}", dependencies=[Depends(verifier_csrf)])
async def enregistrer(request: Request, iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.statut != BROUILLON:
        raise HTTPException(400, "Ce rapport est validé : un validateur doit le rouvrir pour le modifier.")
    f = await request.form()
    if f.get("type") in TYPES_INTERVENTION:
        i.type = f.get("type")
    i.mode = f.get("mode") if f.get("mode") in MODES_INTERVENTION else i.mode
    i.interlocuteur = f.get("interlocuteur", "").strip()
    i.intervenants = [x.strip() for x in f.get("intervenants", "").splitlines() if x.strip()]
    i.date_debut = _date(f.get("date_debut"), i.date_debut)
    i.date_fin = max(_date(f.get("date_fin"), i.date_debut), i.date_debut)
    i.heure_debut, i.heure_fin = _heure(f.get("heure_debut")), _heure(f.get("heure_fin"))
    i.objet = f.get("objet", "").strip()
    i.contexte = {k: f.get(f"ctx_{k}", "").strip() for k in ("postes", "serveurs", "systemes", "version_ksc", "autres")}
    i.travaux = [{"module": m, "resultat": r if r in STATUTS_INTERVENTION else "OK", "actions": a}
                 for m, r, a in zip(_liste(f, "tr_module"), _liste(f, "tr_resultat"), _liste(f, "tr_actions")) if m or a]
    resultat, recos = _liste(f, "resultat"), _liste(f, "recommandation")
    i.resultat = [x for x in resultat if x]
    i.recommandations = [x for x in recos if x]
    i.statut_global = f.get("statut_global") if f.get("statut_global") in STATUTS_INTERVENTION else "OK"
    i.points_bloquants = [{"probleme": p, "impact": im, "action": ac, "responsable": re_, "echeance": ec or None, "plan_action": pl == "1"}
                          for p, im, ac, re_, ec, pl in zip(_liste(f, "pb_probleme"), _liste(f, "pb_impact"), _liste(f, "pb_action"),
                                                            _liste(f, "pb_responsable"), _liste(f, "pb_echeance"), _liste(f, "pb_plan")) if p]
    ajoutes = _ajouter_bibliotheque(db, u, i.type, "action", resultat, _liste(f, "resultat_biblio")) \
        + _ajouter_bibliotheque(db, u, i.type, "recommandation", recos, _liste(f, "recommandation_biblio"))
    journaliser(db, u, "modification intervention", i.numero)
    db.commit()
    flash(request, "Rapport enregistré." + (f" {ajoutes} élément(s) ajouté(s) à la bibliothèque." if ajoutes else ""))
    return rediriger(f"/interventions/{iid}")


# --------------------------------------------------------------------------- #
# Validation, PDF, envoi
# --------------------------------------------------------------------------- #
def _pdf(contenu, nom, telecharger=False):
    disposition = "attachment" if telecharger else "inline"
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(nom)}"})


@routes.get("/interventions/{iid}/apercu.pdf")
def apercu(iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    return _pdf(mi.lire_pdf(i) if i.statut == VALIDE and i.pdf else mi.generer_pdf(i), "apercu.pdf")


@routes.get("/interventions/{iid}/pdf")
def telecharger(iid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.statut == VALIDE and not i.pdf and i.fichier_source:  # import Word confirmé : le document d'origine fait foi
        return FileResponse(absolu(i.fichier_source), media_type=type_mime(i.fichier_source), filename=i.nom_fichier_source)
    if i.statut != VALIDE or not i.pdf:
        raise HTTPException(400, "Le PDF définitif n'existe qu'une fois le rapport validé.")
    nom = i.nom_fichier_source if i.source == "import" and i.pdf == i.fichier_source else mi.nom_fichier(i)
    return _pdf(mi.lire_pdf(i), nom, telecharger=True)


@routes.post("/interventions/{iid}/valider", dependencies=[Depends(verifier_csrf)])
def valider(request: Request, iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.statut != BROUILLON:
        raise HTTPException(400, "Ce rapport est déjà validé.")
    if not i.objet or not (i.resultat or i.travaux):
        flash(request, "Complétez au moins l'objet et le résultat de l'intervention avant de générer le rapport.", "erreur")
        return rediriger(f"/interventions/{iid}")
    mi.valider(db, i, u)
    journaliser(db, u, "validation intervention", i.numero)
    db.commit()
    flash(request, f"Rapport {i.numero} généré : vous pouvez l'envoyer au client.")
    return rediriger(f"/interventions/{iid}")


@routes.post("/interventions/{iid}/rouvrir", dependencies=[Depends(verifier_csrf)])
def rouvrir(request: Request, iid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    i.statut = BROUILLON  # le PDF archivé reste en place ; un nouveau sera généré à la prochaine validation
    journaliser(db, u, "réouverture intervention", i.numero)
    db.commit()
    flash(request, f"Rapport {i.numero} rouvert en modification.", "info")
    return rediriger(f"/interventions/{iid}")


@routes.post("/interventions/{iid}/envoyer", dependencies=[Depends(verifier_csrf)])
def envoyer(request: Request, iid: int, destinataires: str = Form(""), u=Depends(operateur),
            db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.statut != VALIDE:
        raise HTTPException(400, "Validez le rapport avant de l'envoyer.")
    adresses = [x.strip() for x in destinataires.replace(";", ",").split(",") if x.strip()]
    try:
        mi.envoyer(i, adresses)
    except Exception as e:  # noqa: BLE001  (serveur de messagerie injoignable, pas de destinataire…)
        flash(request, f"Envoi impossible : {e}", "erreur")
        return rediriger(f"/interventions/{iid}")
    journaliser(db, u, "envoi intervention", f"{i.numero} à {i.envoye_a}")
    db.commit()
    flash(request, f"Rapport {i.numero} envoyé à {i.envoye_a}.")
    return rediriger(f"/interventions/{iid}")


@routes.get("/interventions/{iid}/brouillon.eml")
def brouillon(iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    """Brouillon Outlook avec le PDF joint ; l'envoi est noté (le message part du poste de l'utilisateur)."""
    i = _intervention(db, iid)
    if i.statut != VALIDE:
        raise HTTPException(400, "Validez le rapport avant de préparer l'envoi.")
    contenu = mi.brouillon_eml(i)
    if not i.envoye_le:
        i.envoye_le, i.envoye_a = datetime.now(), "brouillon Outlook : " + (", ".join(i.client.emails_rapports or []) or "destinataires à saisir")
    journaliser(db, u, "brouillon d'envoi intervention", i.numero)
    db.commit()
    return Response(contenu, media_type="message/rfc822",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(i.numero + '.eml')}"})


@routes.post("/interventions/{iid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer(request: Request, iid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    i = _intervention(db, iid)
    if i.statut != BROUILLON or i.pdf:
        raise HTTPException(400, "Seul un brouillon jamais validé peut être supprimé.")
    journaliser(db, u, "suppression intervention", i.numero)
    importe, fichier = i.source == "import", i.fichier_source
    db.delete(i)
    db.commit()
    if fichier:
        supprimer_fichier(fichier)
    flash(request, f"Brouillon {i.numero} supprimé.")
    return rediriger("/interventions/importer" if importe else "/interventions")


# --------------------------------------------------------------------------- #
# Historique d'un client
# --------------------------------------------------------------------------- #
@routes.get("/clients/{cid}/interventions")
def historique_client(request: Request, cid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(404)
    requete = select(Intervention).where(Intervention.client_id == cid)
    if not u.peut("operateur"):
        requete = requete.where(Intervention.statut == VALIDE)
    lignes = db.scalars(requete.order_by(Intervention.date_debut.desc(), Intervention.id.desc())).all()
    return page(request, "client_interventions.html", u, client=client, lignes=lignes, TYPES=TYPES_INTERVENTION,
                MODES_LIB=MODES_INTERVENTION)


# --------------------------------------------------------------------------- #
# Bibliothèque d'actions et de recommandations
# --------------------------------------------------------------------------- #
@routes.get("/bibliotheque")
def bibliotheque(request: Request, type: str = "deploiement", genre: str = "action",
                 u=Depends(operateur), db: SessionDB = Depends(session_db)):
    type = type if type in TYPES_INTERVENTION or type == "tous" else "deploiement"
    genre = genre if genre in ("action", "recommandation") else "action"
    elements = db.scalars(select(ElementBibliotheque).where(ElementBibliotheque.type_intervention == type,
                                                            ElementBibliotheque.genre == genre)
                          .order_by(ElementBibliotheque.categorie, ElementBibliotheque.ordre, ElementBibliotheque.id)).all()
    return page(request, "bibliotheque.html", u, elements=elements, type_=type, genre=genre, TYPES=TYPES_INTERVENTION)


@routes.post("/bibliotheque", dependencies=[Depends(verifier_csrf)])
def ajouter_element(request: Request, type: str = Form(...), genre: str = Form(...), categorie: str = Form(""),
                    libelle: str = Form(...), u=Depends(operateur), db: SessionDB = Depends(session_db)):
    if (type not in TYPES_INTERVENTION and type != "tous") or genre not in ("action", "recommandation") or not libelle.strip():
        raise HTTPException(400, "Élément invalide.")
    db.add(ElementBibliotheque(type_intervention=type, genre=genre, categorie=categorie.strip() or "Ajouts de l'équipe",
                               libelle=libelle.strip(), ordre=1000, cree_par_id=u.id))
    journaliser(db, u, "ajout bibliothèque", f"{type} / {genre} : {libelle.strip()[:80]}")
    db.commit()
    flash(request, "Élément ajouté à la bibliothèque.")
    return rediriger(f"/bibliotheque?type={type}&genre={genre}")


@routes.post("/bibliotheque/{eid}", dependencies=[Depends(verifier_csrf)])
def modifier_element(request: Request, eid: int, categorie: str = Form(""), libelle: str = Form(...), actif: bool = Form(False),
                     u=Depends(validateur), db: SessionDB = Depends(session_db)):
    e = db.get(ElementBibliotheque, eid)
    if e is None or not libelle.strip():
        raise HTTPException(400, "Élément invalide.")
    e.categorie, e.libelle, e.actif = categorie.strip(), libelle.strip(), actif
    journaliser(db, u, "modification bibliothèque", libelle.strip()[:80])
    db.commit()
    flash(request, "Élément modifié.")
    return rediriger(f"/bibliotheque?type={e.type_intervention}&genre={e.genre}")


@routes.post("/bibliotheque/{eid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_element(request: Request, eid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    e = db.get(ElementBibliotheque, eid)
    if e is None:
        raise HTTPException(404)
    type_, genre = e.type_intervention, e.genre
    journaliser(db, u, "suppression bibliothèque", e.libelle[:80])
    db.delete(e)
    db.commit()
    flash(request, "Élément supprimé de la bibliothèque.")
    return rediriger(f"/bibliotheque?type={type_}&genre={genre}")

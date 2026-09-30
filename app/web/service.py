"""Service technique : assistances mensuelles, base de connaissances, techniciens (parcours, certifications),
activités internes et rapports d'activité du service."""
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import interventions as mi
from .. import rapport_service as rs
from .. import service_technique as st
from ..db import session_db
from ..modeles import (BROUILLON, PERIODICITES_SERVICE, STATUTS_FORMATION, TYPES_ACTIVITE, VALIDE, ActiviteInterne,
                       AssistancePlanifiee, Certification, Formation, Intervention, RapportService, Utilisateur, journaliser)
from ..moteur.outils import bornes_mois, fmt_mois, mois_decale
from ..securite import exiger, verifier_csrf
from ..stockage import DepotInvalide, absolu, enregistrer, lire_fichier, supprimer, type_mime
from .commun import flash, page, rediriger

routes = APIRouter()
lecteur, operateur, validateur, admin = exiger("lecteur"), exiger("operateur"), exiger("validateur"), exiger("admin")
TAILLE_MAX_JUSTIFICATIF = 10 * 1024 * 1024


def _date(texte, obligatoire=False):
    try:
        return date.fromisoformat(texte) if texte else None
    except ValueError:
        raise HTTPException(400, "Date invalide.")


def _mois(annee, mois):
    if annee and mois and 1 <= mois <= 12:
        return annee, mois
    j = date.today()
    return j.year, j.month


# --------------------------------------------------------------------------- #
# Assistances mensuelles
# --------------------------------------------------------------------------- #
PERIODES_CLASSEMENT = {"mois": "le mois", "trimestre": "le trimestre", "annee": "l'année"}


def _bornes_classement(periode, annee, mois):
    if periode == "annee":
        return date(annee, 1, 1), date(annee + 1, 1, 1)
    if periode == "trimestre":
        premier = (mois - 1) // 3 * 3 + 1
        return date(annee, premier, 1), bornes_mois(*mois_decale(annee, premier, 2))[1]
    return bornes_mois(annee, mois)


@routes.get("/assistances")
def assistances(request: Request, annee: int | None = None, mois: int | None = None, periode: str = "mois",
                u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    annee, mois = _mois(annee, mois)
    st.assurer_planning(db, annee, mois)
    db.commit()
    periode = periode if periode in PERIODES_CLASSEMENT else "mois"
    debut, fin = _bornes_classement(periode, annee, mois)
    techniciens = db.scalars(select(Utilisateur).where(Utilisateur.actif.is_(True), Utilisateur.role != "lecteur")
                             .order_by(Utilisateur.nom)).all()
    return page(request, "assistances.html", u, annee=annee, mois=mois, periode=periode, PERIODES=PERIODES_CLASSEMENT,
                p=st.planning(db, annee, mois), etat=st.etat, techniciens=techniciens,
                clients=st.classement_clients(db, debut, fin), techs=st.classement_techniciens(db, debut, fin),
                debut=debut, fin_incluse=fin - timedelta(days=1))


def _assistance(db, aid):
    a = db.get(AssistancePlanifiee, aid)
    if a is None:
        raise HTTPException(404)
    return a


def _retour(a):
    return rediriger(f"/assistances?annee={a.annee}&mois={a.mois}")


@routes.post("/assistances/{aid}", dependencies=[Depends(verifier_csrf)])
def planifier(request: Request, aid: int, date_prevue: str = Form(""), technicien_id: str = Form(""),
              u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a = _assistance(db, aid)
    if a.statut == "realisee":
        raise HTTPException(400, "Assistance déjà réalisée.")
    a.date_prevue = _date(date_prevue)
    a.technicien_id = int(technicien_id) if technicien_id.isdigit() else None
    a.statut = "planifiee" if a.date_prevue else "a_planifier"
    journaliser(db, u, "planification assistance", f"{a.client.nom} {a.mois:02d}/{a.annee} : {a.date_prevue or 'sans date'}")
    db.commit()
    flash(request, f"Assistance de {a.client.nom} planifiée." if a.date_prevue else f"Planification de {a.client.nom} effacée.")
    return _retour(a)


@routes.post("/assistances/{aid}/reporter", dependencies=[Depends(verifier_csrf)])
def reporter(request: Request, aid: int, justification: str = Form(...), u=Depends(validateur), db: SessionDB = Depends(session_db)):
    a = _assistance(db, aid)
    if not justification.strip():
        raise HTTPException(400, "Une justification est obligatoire.")
    a.statut, a.justification = "reportee", justification.strip()
    journaliser(db, u, "report assistance", f"{a.client.nom} {a.mois:02d}/{a.annee} : {a.justification}")
    db.commit()
    flash(request, f"Assistance de {a.client.nom} reportée (non comptée comme manquée).", "info")
    return _retour(a)


@routes.post("/assistances/{aid}/rouvrir", dependencies=[Depends(verifier_csrf)])
def rouvrir(request: Request, aid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    a = _assistance(db, aid)
    a.statut, a.justification = ("planifiee" if a.date_prevue else "a_planifier"), ""
    journaliser(db, u, "réouverture assistance", f"{a.client.nom} {a.mois:02d}/{a.annee}")
    db.commit()
    return _retour(a)


@routes.post("/assistances/{aid}/rediger", dependencies=[Depends(verifier_csrf)])
def rediger(request: Request, aid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    """Crée le rapport d'assistance du mois et le rattache à l'assistance planifiée."""
    a = _assistance(db, aid)
    if a.intervention_id:
        return rediriger(f"/interventions/{a.intervention_id}")
    debut, fin = bornes_mois(a.annee, a.mois)
    jour = a.date_prevue or date.today()
    if not (debut <= jour < fin):  # rapport daté dans le mois de l'assistance
        jour = debut
    i = mi.creer(db, a.client, "assistance", u, jour)
    if a.technicien and a.technicien.nom not in i.intervenants:
        i.intervenants = [a.technicien.nom] + [n for n in i.intervenants if n != a.technicien.nom]
    i.objet = f"Assistance mensuelle de {fmt_mois(a.annee, a.mois).lower()}."
    a.intervention_id = i.id
    if a.statut == "a_planifier":
        a.statut, a.date_prevue = "planifiee", jour
    journaliser(db, u, "création intervention", f"{i.numero} (assistance mensuelle {a.mois:02d}/{a.annee})")
    db.commit()
    flash(request, f"Rapport {i.numero} créé pour l'assistance de {fmt_mois(a.annee, a.mois).lower()} : il comptera dès sa validation.")
    return rediriger(f"/interventions/{i.id}")


# --------------------------------------------------------------------------- #
# Base de connaissances
# --------------------------------------------------------------------------- #
@routes.get("/connaissances")
def connaissances(request: Request, q: str = "", u=Depends(operateur), db: SessionDB = Depends(session_db)):
    return page(request, "connaissances.html", u, q=q, resultats=st.rechercher(db, q) if q.strip() else None,
                recurrents=st.problemes_recurrents(db))


# --------------------------------------------------------------------------- #
# Techniciens : parcours et certifications
# --------------------------------------------------------------------------- #
def _peut_modifier(u, uid):
    return u.id == uid or u.peut("admin")


@routes.get("/techniciens")
def techniciens(request: Request, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    annee = date.today().year
    lignes = st.classement_techniciens(db, date(annee, 1, 1), date(annee + 1, 1, 1))
    certifs = {}
    for c in db.scalars(select(Certification)):
        certifs.setdefault(c.utilisateur_id, []).append(c)
    return page(request, "techniciens.html", u, lignes=lignes, certifs=certifs, annee=annee, etat_certif=st.etat_certification)


@routes.get("/techniciens/{uid}")
def technicien(request: Request, uid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    t = db.get(Utilisateur, uid)
    if t is None:
        raise HTTPException(404)
    if u.id != uid and not u.peut("operateur"):
        raise HTTPException(403, "Vous ne pouvez consulter que votre propre fiche.")
    annee = date.today().year
    stats = next((l for l in st.classement_techniciens(db, date(annee, 1, 1), date(annee + 1, 1, 1)) if l["utilisateur"].id == uid), None)
    interventions = [i for i in db.scalars(select(Intervention).where(Intervention.statut == VALIDE)
                                            .order_by(Intervention.date_debut.desc()).limit(400)) if st.participe(t, i)][:15]
    return page(request, "technicien.html", u, t=t, modifiable=_peut_modifier(u, uid), stats=stats, annee=annee,
                formations=db.scalars(select(Formation).where(Formation.utilisateur_id == uid).order_by(Formation.debut.desc())).all(),
                certifications=db.scalars(select(Certification).where(Certification.utilisateur_id == uid)
                                          .order_by(Certification.obtenue_le.desc())).all(),
                interventions=interventions, etat_certif=st.etat_certification, STATUTS=STATUTS_FORMATION)


@routes.post("/techniciens/{uid}/formations", dependencies=[Depends(verifier_csrf)])
@routes.post("/formations/{fid}", dependencies=[Depends(verifier_csrf)])
def enregistrer_formation(request: Request, uid: int | None = None, fid: int | None = None, intitule: str = Form(...),
                          organisme: str = Form(""), debut: str = Form(""), fin: str = Form(""), statut: str = Form("Terminée"),
                          heures: str = Form(""), notes: str = Form(""), u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    f = db.get(Formation, fid) if fid else Formation(utilisateur_id=uid)
    if f is None or not _peut_modifier(u, f.utilisateur_id):
        raise HTTPException(403 if f else 404, "Modification réservée au technicien et aux administrateurs.")
    f.intitule, f.organisme, f.notes = intitule.strip(), organisme.strip(), notes.strip()
    f.debut, f.fin = _date(debut), _date(fin)
    f.statut = statut if statut in STATUTS_FORMATION else "Terminée"
    f.heures = int(heures) if heures.strip().isdigit() else None
    if not fid:
        db.add(f)
    db.flush()
    journaliser(db, u, "formation enregistrée", f"{db.get(Utilisateur, f.utilisateur_id).email} : {f.intitule}")
    db.commit()
    flash(request, "Formation enregistrée.")
    return rediriger(f"/techniciens/{f.utilisateur_id}#parcours")


@routes.post("/formations/{fid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_formation(request: Request, fid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    f = db.get(Formation, fid)
    if f is None or not _peut_modifier(u, f.utilisateur_id):
        raise HTTPException(403, "Modification réservée au technicien et aux administrateurs.")
    uid = f.utilisateur_id
    journaliser(db, u, "formation supprimée", f.intitule)
    db.delete(f)
    db.commit()
    return rediriger(f"/techniciens/{uid}#parcours")


@routes.post("/techniciens/{uid}/certifications", dependencies=[Depends(verifier_csrf)])
async def ajouter_certification(request: Request, uid: int, intitule: str = Form(...), editeur: str = Form("Kaspersky"),
                                numero: str = Form(""), obtenue_le: str = Form(...), expire_le: str = Form(""),
                                justificatif: UploadFile | None = File(None), u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    if db.get(Utilisateur, uid) is None:
        raise HTTPException(404)
    if not _peut_modifier(u, uid):
        raise HTTPException(403, "Modification réservée au technicien et aux administrateurs.")
    c = Certification(utilisateur_id=uid, intitule=intitule.strip(), editeur=editeur.strip() or "Autre", numero=numero.strip(),
                      obtenue_le=_date(obtenue_le), expire_le=_date(expire_le))
    if c.obtenue_le is None:
        raise HTTPException(400, "La date d'obtention est obligatoire.")
    if justificatif is not None and justificatif.filename:
        try:
            contenu, extension = await lire_fichier(justificatif, (".pdf", ".png", ".jpg", ".jpeg"), TAILLE_MAX_JUSTIFICATIF)
        except DepotInvalide as e:
            flash(request, str(e), "erreur")
            return rediriger(f"/techniciens/{uid}#certifications")
        c.fichier, _ = enregistrer(contenu, "certifications", str(uid), extension=extension)
        c.nom_fichier = justificatif.filename[:300]
    db.add(c)
    journaliser(db, u, "certification ajoutée", f"{db.get(Utilisateur, uid).email} : {c.intitule} ({c.editeur})")
    db.commit()
    flash(request, f"Certification « {c.intitule} » ajoutée.")
    return rediriger(f"/techniciens/{uid}#certifications")


@routes.post("/certifications/{cid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_certification(request: Request, cid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    c = db.get(Certification, cid)
    if c is None or not _peut_modifier(u, c.utilisateur_id):
        raise HTTPException(403, "Modification réservée au technicien et aux administrateurs.")
    uid = c.utilisateur_id
    if c.fichier and not db.scalar(select(Certification.id).where(Certification.fichier == c.fichier, Certification.id != c.id)):
        supprimer(c.fichier)
    journaliser(db, u, "certification supprimée", c.intitule)
    db.delete(c)
    db.commit()
    return rediriger(f"/techniciens/{uid}#certifications")


@routes.get("/certifications/{cid}/fichier")
def justificatif(cid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    c = db.get(Certification, cid)
    if c is None or not c.fichier:
        raise HTTPException(404)
    if u.id != c.utilisateur_id and not u.peut("validateur"):
        raise HTTPException(403, "Justificatif réservé au technicien, aux validateurs et aux administrateurs.")
    return FileResponse(absolu(c.fichier), media_type=type_mime(c.fichier), filename=c.nom_fichier or "justificatif")


# --------------------------------------------------------------------------- #
# Activités internes
# --------------------------------------------------------------------------- #
@routes.get("/activites")
def activites(request: Request, annee: int | None = None, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    annee = annee or date.today().year
    lignes = db.scalars(select(ActiviteInterne).where(ActiviteInterne.date >= date(annee, 1, 1), ActiviteInterne.date < date(annee + 1, 1, 1))
                        .order_by(ActiviteInterne.date.desc())).all()
    noms = db.scalars(select(Utilisateur.nom).where(Utilisateur.actif.is_(True)).order_by(Utilisateur.nom)).all()
    return page(request, "activites.html", u, lignes=lignes, annee=annee, TYPES=TYPES_ACTIVITE, noms=noms)


@routes.post("/activites", dependencies=[Depends(verifier_csrf)])
@routes.post("/activites/{aid}", dependencies=[Depends(verifier_csrf)])
def enregistrer_activite(request: Request, aid: int | None = None, date_: str = Form(..., alias="date"), type: str = Form("projet"),
                         titre: str = Form(...), description: str = Form(""), participants: str = Form(""), duree: str = Form(""),
                         u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a = db.get(ActiviteInterne, aid) if aid else ActiviteInterne(cree_par_id=u.id)
    if a is None:
        raise HTTPException(404)
    if aid and a.cree_par_id != u.id and not u.peut("validateur"):
        raise HTTPException(403, "Modification réservée à l'auteur et aux validateurs.")
    a.date, a.titre, a.description = _date(date_) or date.today(), titre.strip(), description.strip()
    a.type = type if type in TYPES_ACTIVITE else "autre"
    a.participants = [p.strip() for p in participants.replace(";", ",").split(",") if p.strip()]
    try:
        a.duree_heures = float(duree.replace(",", ".")) if duree.strip() else None
    except ValueError:
        raise HTTPException(400, "Durée invalide.")
    if not aid:
        db.add(a)
    journaliser(db, u, "activité interne", f"{a.date} : {a.titre}")
    db.commit()
    flash(request, "Activité enregistrée.")
    return rediriger(f"/activites?annee={a.date.year}")


@routes.post("/activites/{aid}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_activite(request: Request, aid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    a = db.get(ActiviteInterne, aid)
    if a is None:
        raise HTTPException(404)
    if a.cree_par_id != u.id and not u.peut("validateur"):
        raise HTTPException(403, "Suppression réservée à l'auteur et aux validateurs.")
    journaliser(db, u, "activité interne supprimée", a.titre)
    db.delete(a)
    db.commit()
    return rediriger(f"/activites?annee={a.date.year}")


# --------------------------------------------------------------------------- #
# Rapports d'activité du service
# --------------------------------------------------------------------------- #
@routes.get("/service")
def rapports_service(request: Request, periodicite: str = "trimestriel", annee: int | None = None, numero: int | None = None,
                     u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    periodicite = periodicite if periodicite in PERIODICITES_SERVICE else "trimestriel"
    defaut = rs.periode_par_defaut(periodicite)
    annee = annee or defaut[0]
    numero = numero if numero and 1 <= numero <= rs.nb_periodes(periodicite) else defaut[1]
    requete = select(RapportService).order_by(RapportService.debut.desc(), RapportService.version.desc())
    if not u.peut("operateur"):
        requete = requete.where(RapportService.statut == VALIDE)
    return page(request, "service.html", u, periodicite=periodicite, annee=annee, numero=numero,
                nb_periodes=rs.nb_periodes(periodicite), libelle=rs.libelle(periodicite, annee, numero),
                existant=rs.dernier(db, periodicite, annee, numero), rapports=db.scalars(requete.limit(60)).all(),
                libelle_court=rs.libelle_court, PERIODICITES=PERIODICITES_SERVICE)


@routes.post("/service", dependencies=[Depends(verifier_csrf)])
def creer_rapport_service(request: Request, periodicite: str = Form(...), annee: int = Form(...), numero: int = Form(...),
                          u=Depends(validateur), db: SessionDB = Depends(session_db)):
    if periodicite not in PERIODICITES_SERVICE or not 1 <= numero <= rs.nb_periodes(periodicite):
        raise HTTPException(400, "Période invalide.")
    existant = rs.dernier(db, periodicite, annee, numero)
    if existant and existant.statut == BROUILLON:
        return rediriger(f"/service/{existant.id}")
    r = rs.creer(db, periodicite, annee, numero, u)
    journaliser(db, u, "création rapport du service", f"{rs.libelle_court(periodicite, annee, numero)} v{r.version}")
    db.commit()
    flash(request, f"Rapport d'activité {rs.libelle(periodicite, annee, numero)} créé en brouillon.")
    return rediriger(f"/service/{r.id}")


def _rapport(db, rid, u):
    r = db.get(RapportService, rid)
    if r is None:
        raise HTTPException(404)
    if r.statut != VALIDE and not u.peut("operateur"):
        raise HTTPException(403, "Seuls les rapports validés sont accessibles avec le rôle Lecteur.")
    return r


@routes.get("/service/{rid}")
def relecture_service(request: Request, rid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    return page(request, "relecture_service.html", u, r=r, d=r.donnees, c=r.contenu,
                modifiable=r.statut == BROUILLON and u.peut("validateur"), libelle=rs.libelle(r.periodicite, r.annee, r.numero))


@routes.post("/service/{rid}/contenu", dependencies=[Depends(verifier_csrf)])
async def enregistrer_service(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != BROUILLON:
        raise HTTPException(400, "Rapport validé : créez une nouvelle version.")
    f = await request.form()
    lignes = lambda nom: [x.strip() for x in f.get(nom, "").splitlines() if x.strip()]
    r.contenu = {**r.contenu, "synthese": f.get("synthese", "").strip(), "faits_marquants": lignes("faits_marquants"),
                 "perspectives": lignes("perspectives"), "conclusion": f.get("conclusion", "").strip()}
    journaliser(db, u, "modification rapport du service", rs.libelle_court(r.periodicite, r.annee, r.numero))
    db.commit()
    flash(request, "Textes enregistrés.")
    return rediriger(f"/service/{rid}")


@routes.post("/service/{rid}/actualiser", dependencies=[Depends(verifier_csrf)])
async def actualiser_service(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != BROUILLON:
        raise HTTPException(400, "Seul un brouillon peut être actualisé.")
    rs.actualiser(db, r, (await request.form()).get("reinitialiser") == "1")
    journaliser(db, u, "actualisation rapport du service", rs.libelle_court(r.periodicite, r.annee, r.numero))
    db.commit()
    flash(request, "Chiffres recalculés.")
    return rediriger(f"/service/{rid}")


@routes.post("/service/{rid}/valider", dependencies=[Depends(verifier_csrf)])
def valider_service(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != BROUILLON:
        raise HTTPException(400, "Déjà validé.")
    rs.valider(db, r, u)
    journaliser(db, u, "validation rapport du service", rs.libelle_court(r.periodicite, r.annee, r.numero))
    db.commit()
    flash(request, "Rapport d'activité validé : le PDF est archivé.")
    return rediriger(f"/service/{rid}")


@routes.post("/service/{rid}/nouvelle-version", dependencies=[Depends(verifier_csrf)])
def nouvelle_version_service(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    dernier = rs.dernier(db, r.periodicite, r.annee, r.numero)
    if dernier.statut == BROUILLON:
        return rediriger(f"/service/{dernier.id}")
    n = rs.creer(db, r.periodicite, r.annee, r.numero, u, base=r)
    journaliser(db, u, "nouvelle version rapport du service", f"{rs.libelle_court(r.periodicite, r.annee, r.numero)} v{n.version}")
    db.commit()
    return rediriger(f"/service/{n.id}")


def _pdf(contenu, nom, telecharger=False):
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f"{'attachment' if telecharger else 'inline'}; filename*=UTF-8''{quote(nom)}"})


@routes.get("/service/{rid}/apercu.pdf")
def apercu_service(rid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut == VALIDE and r.pdf:
        return FileResponse(absolu(r.pdf), media_type="application/pdf")
    return _pdf(rs.generer_pdf(r), "apercu.pdf")


@routes.get("/service/{rid}/pdf")
def telecharger_service(rid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != VALIDE or not r.pdf:
        raise HTTPException(400, "Le PDF définitif n'existe qu'une fois le rapport validé.")
    return FileResponse(absolu(r.pdf), media_type="application/pdf", filename=rs.nom_fichier(r))


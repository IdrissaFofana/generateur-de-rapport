"""Rapports : création des brouillons, relecture, aperçu, validation, téléchargement."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionDB

from .. import alertes, services
from ..config import PRESTATAIRE
from ..db import session_db
from ..modeles import BROUILLON, VALIDE, Client, Rapport, journaliser
from ..moteur import bilan as mbilan
from ..moteur.redaction import STATUTS_ACTION
from ..rendu.word import docx_rapport
from ..securite import exiger, verifier_csrf
from ..stockage import absolu
from .commun import flash, page, rediriger

routes = APIRouter()
lecteur, operateur, validateur = exiger("lecteur"), exiger("operateur"), exiger("validateur")
PRIORITES = ("Urgente", "Haute", "Normale")
NIVEAUX_RISQUE = ("Critique", "Élevé", "Modéré", "Faible")


def _rapport(db, rid, u):
    r = db.get(Rapport, rid)
    if r is None:
        raise HTTPException(404)
    if r.statut != VALIDE and not u.peut("operateur"):
        raise HTTPException(403, "Seuls les rapports validés sont accessibles avec le rôle Lecteur.")
    return r


def _ref(r):
    """« HUDSON 09/2026 v2 » pour un mensuel, « HUDSON T3 2026 v1 » pour un bilan (journal)."""
    periode = f"{r.mois:02d}/{r.annee}" if r.periodicite == "mensuel" else services.libelle_rapport(r)
    return f"{r.client.nom} {periode} v{r.version}"


def _pdf(contenu, nom, telecharger=False):
    disposition = "attachment" if telecharger else "inline"
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(nom)}"})


@routes.post("/clients/{cid}/{annee}/{mois}/rapports", dependencies=[Depends(verifier_csrf)])
def creer(request: Request, cid: int, annee: int, mois: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(404)
    dernier = services.dernier_rapport(db, cid, annee, mois)
    if dernier and dernier.statut == BROUILLON:
        return rediriger(f"/rapports/{dernier.id}")  # un seul brouillon à la fois
    rapport = services.creer_brouillon(db, client, annee, mois, u)
    journaliser(db, u, "création brouillon", f"{client.nom} {mois:02d}/{annee} v{rapport.version}")
    db.commit()
    flash(request, f"Brouillon v{rapport.version} créé à partir des données déposées.")
    return rediriger(f"/rapports/{rapport.id}")


@routes.get("/rapports/{rid}")
def relecture(request: Request, rid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    versions = db.scalars(select(Rapport).where(Rapport.client_id == r.client_id, Rapport.periodicite == r.periodicite,
                                                Rapport.annee == r.annee, Rapport.mois == r.mois)
                          .order_by(Rapport.version.desc())).all()
    modifiable = r.statut == BROUILLON and u.peut("validateur")
    if r.periodicite != "mensuel":
        return page(request, "relecture_bilan.html", u, r=r, c=r.contenu, d=r.donnees, versions=versions,
                    modifiable=modifiable, NIVEAUX=NIVEAUX_RISQUE, libelle=services.libelle_rapport(r),
                    section="bilans")
    return page(request, "relecture.html", u, r=r, c=r.contenu, d=r.donnees, versions=versions, modifiable=modifiable,
                PRIORITES=PRIORITES, STATUTS=STATUTS_ACTION, NIVEAUX=NIVEAUX_RISQUE)


def _liste(formulaire, nom):
    return [v.strip() for v in formulaire.getlist(nom)]


@routes.post("/rapports/{rid}/contenu", dependencies=[Depends(verifier_csrf)])
async def enregistrer(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != BROUILLON:
        raise HTTPException(400, "Ce rapport est validé : créez une nouvelle version pour le modifier.")
    f = await request.form()
    niveau = f.get("niveau_risque", "")
    if r.periodicite != "mensuel":
        r.contenu = {
            **r.contenu,
            "niveau_risque": niveau if niveau in NIVEAUX_RISQUE else r.contenu["niveau_risque"],
            "motifs_risque": [m.strip() for m in f.get("motifs_risque", "").splitlines() if m.strip()],
            **{k: f.get(k, "").strip() for k in ("synthese", "commentaire_evolution", "perspectives", "conclusion")},
        }
        journaliser(db, u, "modification brouillon", _ref(r))
        db.commit()
        flash(request, "Modifications enregistrées.")
        return rediriger(f"/rapports/{rid}")
    actions = [{"action": a, "pourquoi": p, "priorite": pr if pr in PRIORITES else "Normale", "responsable": re_,
                "statut": "À faire"}
               for a, p, pr, re_ in zip(_liste(f, "action"), _liste(f, "pourquoi"), _liste(f, "priorite"),
                                        _liste(f, "responsable")) if a]
    suivi = [{"action": a, "priorite": pr, "responsable": re_, "statut": st if st in STATUTS_ACTION else "À faire",
              "commentaire": co}
             for a, pr, re_, st, co in zip(_liste(f, "suivi_action"), _liste(f, "suivi_priorite"),
                                            _liste(f, "suivi_responsable"), _liste(f, "suivi_statut"),
                                            _liste(f, "suivi_commentaire")) if a]
    r.contenu = {
        **r.contenu,
        "niveau_risque": niveau if niveau in NIVEAUX_RISQUE else r.contenu["niveau_risque"],
        "motifs_risque": [m.strip() for m in f.get("motifs_risque", "").splitlines() if m.strip()],
        "synthese": f.get("synthese", "").strip(),
        "commentaires": {k: f.get(f"com_{k}", "").strip() for k in ("mdr", "protection", "menaces", "vulnerabilites")},
        "suggestion_mdr": f.get("suggestion_mdr", "").strip(),
        "conclusion": f.get("conclusion", "").strip(),
        "actions": actions,
        "suivi": suivi,
    }
    journaliser(db, u, "modification brouillon", _ref(r))
    db.commit()
    flash(request, "Modifications enregistrées.")
    return rediriger(f"/rapports/{rid}")


@routes.post("/rapports/{rid}/actualiser", dependencies=[Depends(verifier_csrf)])
async def actualiser(request: Request, rid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != BROUILLON:
        raise HTTPException(400, "Seul un brouillon peut être actualisé.")
    reinitialiser = (await request.form()).get("reinitialiser") == "1"
    if reinitialiser and not u.peut("validateur"):
        raise HTTPException(403, "La réinitialisation des textes est réservée aux validateurs.")
    if r.periodicite == "mensuel":
        services.actualiser_brouillon(db, r, reinitialiser)
    else:
        services.actualiser_bilan(db, r, reinitialiser)
    journaliser(db, u, "actualisation brouillon" + (" (textes réinitialisés)" if reinitialiser else ""),
                _ref(r))
    db.commit()
    flash(request, ("Chiffres recalculés à partir des fichiers déposés." if r.periodicite == "mensuel"
                    else "Bilan recalculé à partir des rapports mensuels validés.")
                   + (" Les textes ont été régénérés." if reinitialiser else " Vos textes ont été conservés."))
    return rediriger(f"/rapports/{rid}")


@routes.get("/rapports/{rid}/apercu.pdf")
def apercu_pdf(rid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut == VALIDE and r.pdf:
        return FileResponse(absolu(r.pdf), media_type="application/pdf")
    return _pdf(services.generer_pdf(r), "apercu.pdf")


@routes.post("/rapports/{rid}/valider", dependencies=[Depends(verifier_csrf)])
def valider(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != BROUILLON:
        raise HTTPException(400, "Ce rapport est déjà validé.")
    services.valider(db, r, u)
    journaliser(db, u, "validation rapport", _ref(r))
    db.commit()
    if r.periodicite == "mensuel":
        alertes.evaluer_et_notifier(db)  # niveau critique, hausse des détections
    flash(request, f"Rapport v{r.version} validé : le PDF définitif est archivé.")
    return rediriger(f"/rapports/{rid}")


@routes.post("/rapports/{rid}/nouvelle-version", dependencies=[Depends(verifier_csrf)])
def nouvelle_version(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    dernier = services.dernier_rapport(db, r.client_id, r.annee, r.mois, periodicite=r.periodicite)
    if dernier.statut == BROUILLON:
        flash(request, f"Un brouillon (v{dernier.version}) existe déjà.", "info")
        return rediriger(f"/rapports/{dernier.id}")
    if r.periodicite == "mensuel":
        nouveau = services.creer_brouillon(db, r.client, r.annee, r.mois, u, base=r)
    else:
        nouveau = services.creer_bilan(db, r.client, r.periodicite, r.annee,
                                       mbilan.numero_periode(r.periodicite, r.mois), u, base=r)
    journaliser(db, u, "nouvelle version", _ref(nouveau))
    db.commit()
    flash(request, f"Version v{nouveau.version} créée en brouillon, avec les textes de la v{r.version}.")
    return rediriger(f"/rapports/{nouveau.id}")


def mettre_a_jour_rapport(db, r, u):
    """Nouvelle version d'un rapport validé, entièrement recalculée : chiffres, textes et plan d'action régénérés à
    partir des fichiers déposés et des règles actuelles. La version validée reste archivée telle quelle."""
    if r.periodicite == "mensuel":
        nouveau = services.creer_brouillon(db, r.client, r.annee, r.mois, u)
    else:
        nouveau = services.creer_bilan(db, r.client, r.periodicite, r.annee, mbilan.numero_periode(r.periodicite, r.mois), u)
    journaliser(db, u, "mise à jour (nouvelle version régénérée)", f"{_ref(nouveau)} depuis v{r.version}")
    return nouveau


@routes.post("/rapports/{rid}/mettre-a-jour", dependencies=[Depends(verifier_csrf)])
def mettre_a_jour(request: Request, rid: int, u=Depends(validateur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    dernier = services.dernier_rapport(db, r.client_id, r.annee, r.mois, periodicite=r.periodicite)
    if dernier.statut == BROUILLON:
        flash(request, f"Un brouillon (v{dernier.version}) existe déjà : utilisez « Actualiser les chiffres » "
                       "ou « Régénérer les textes ».", "info")
        return rediriger(f"/rapports/{dernier.id}")
    nouveau = mettre_a_jour_rapport(db, r, u)
    db.commit()
    flash(request, f"Version v{nouveau.version} créée en brouillon, recalculée avec les données et les règles actuelles. "
                   f"Relisez-la puis validez-la ; la v{r.version} reste archivée.")
    return rediriger(f"/rapports/{nouveau.id}")


@routes.get("/rapports/{rid}/pdf")
def telecharger_pdf(rid: int, u=Depends(lecteur), db: SessionDB = Depends(session_db)):
    r = _rapport(db, rid, u)
    if r.statut != VALIDE or not r.pdf:
        raise HTTPException(400, "Le PDF définitif n'existe qu'une fois le rapport validé.")
    return FileResponse(absolu(r.pdf), media_type="application/pdf", filename=services.nom_fichier_rapport(r))


@routes.get("/rapports/{rid}/word")
def telecharger_word(rid: int, u=Depends(operateur), db: SessionDB = Depends(session_db)):
    """Export Word de dépannage (mêmes données et textes que le PDF)."""
    r = _rapport(db, rid, u)
    if r.periodicite != "mensuel":
        raise HTTPException(400, "L'export Word n'existe que pour les rapports mensuels.")
    contenu = docx_rapport(r.donnees, r.contenu, PRESTATAIRE, (r.valide_le or r.cree_le).date())
    journaliser(db, u, "export Word", _ref(r))
    db.commit()
    nom = services.nom_fichier_rapport(r, "docx")
    return Response(contenu, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"})

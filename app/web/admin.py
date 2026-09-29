"""Administration : utilisateurs, clients, journal."""
import re
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessionDB

from ..db import session_db
from ..modeles import ROLES, Client, Hebdo, Journal, Utilisateur, journaliser
from ..securite import exiger, hacher, verifier_csrf
from .commun import flash, page, rediriger

routes = APIRouter(prefix="/admin")
admin = exiger("admin")


def mot_de_passe_provisoire():
    return secrets.token_urlsafe(9) + "7"


def tenants_connus(db):
    """Noms de tenants présents dans les rapports hebdo déjà analysés."""
    noms = set()
    for donnees in db.scalars(select(Hebdo.donnees).where(Hebdo.donnees.is_not(None))):
        noms.update(donnees.get("postes", {}).keys())
    return sorted(noms)


# --------------------------------------------------------------------------- #
# Utilisateurs
# --------------------------------------------------------------------------- #
@routes.get("/utilisateurs")
def utilisateurs(request: Request, u=Depends(admin), db: SessionDB = Depends(session_db)):
    liste = db.scalars(select(Utilisateur).order_by(Utilisateur.actif.desc(), Utilisateur.nom)).all()
    return page(request, "admin_utilisateurs.html", u, liste=liste)


@routes.post("/utilisateurs", dependencies=[Depends(verifier_csrf)])
def creer_utilisateur(request: Request, email: str = Form(...), nom: str = Form(...), role: str = Form(...),
                      u=Depends(admin), db: SessionDB = Depends(session_db)):
    email = email.strip().lower()
    if role not in ROLES:
        raise HTTPException(400, "Rôle inconnu.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash(request, "Adresse e-mail invalide.", "erreur")
        return rediriger("/admin/utilisateurs")
    if db.scalar(select(Utilisateur).where(Utilisateur.email == email)):
        flash(request, f"Un compte existe déjà pour {email}.", "erreur")
        return rediriger("/admin/utilisateurs")
    mdp = mot_de_passe_provisoire()
    db.add(Utilisateur(email=email, nom=nom.strip(), role=role, mot_de_passe=hacher(mdp), doit_changer_mdp=True))
    journaliser(db, u, "création utilisateur", f"{email} ({ROLES[role]})")
    db.commit()
    flash(request, f"Compte créé pour {email}. Mot de passe provisoire à lui transmettre : {mdp} "
                   "(il devra le changer à la première connexion).", "info")
    return rediriger("/admin/utilisateurs")


def _dernier_admin(db, cible):
    admins = db.scalar(select(func.count()).select_from(Utilisateur)
                       .where(Utilisateur.role == "admin", Utilisateur.actif.is_(True)))
    return cible.role == "admin" and cible.actif and admins <= 1


@routes.post("/utilisateurs/{uid}", dependencies=[Depends(verifier_csrf)])
def modifier_utilisateur(request: Request, uid: int, nom: str = Form(...), role: str = Form(...),
                         actif: bool = Form(False), u=Depends(admin), db: SessionDB = Depends(session_db)):
    cible = db.get(Utilisateur, uid)
    if cible is None:
        raise HTTPException(404)
    if role not in ROLES:
        raise HTTPException(400, "Rôle inconnu.")
    if (role != "admin" or not actif) and _dernier_admin(db, cible):
        flash(request, "Impossible : ce compte est le dernier administrateur actif.", "erreur")
        return rediriger("/admin/utilisateurs")
    cible.nom, cible.role, cible.actif = nom.strip(), role, actif
    journaliser(db, u, "modification utilisateur", f"{cible.email} : {ROLES[role]}, {'actif' if actif else 'désactivé'}")
    db.commit()
    flash(request, f"Compte {cible.email} mis à jour.")
    return rediriger("/admin/utilisateurs")


@routes.post("/utilisateurs/{uid}/reinitialiser", dependencies=[Depends(verifier_csrf)])
def reinitialiser(request: Request, uid: int, u=Depends(admin), db: SessionDB = Depends(session_db)):
    cible = db.get(Utilisateur, uid)
    if cible is None:
        raise HTTPException(404)
    mdp = mot_de_passe_provisoire()
    cible.mot_de_passe, cible.doit_changer_mdp = hacher(mdp), True
    journaliser(db, u, "réinitialisation mot de passe", cible.email)
    db.commit()
    flash(request, f"Nouveau mot de passe provisoire pour {cible.email} : {mdp}", "info")
    return rediriger("/admin/utilisateurs")


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
@routes.get("/clients")
def clients(request: Request, u=Depends(admin), db: SessionDB = Depends(session_db)):
    liste = db.scalars(select(Client).order_by(Client.actif.desc(), Client.nom)).all()
    return page(request, "admin_clients.html", u, liste=liste)


@routes.get("/clients/nouveau")
def nouveau_client(request: Request, u=Depends(admin), db: SessionDB = Depends(session_db)):
    return page(request, "admin_client.html", u, client=None, tenants=tenants_connus(db))


@routes.get("/clients/{cid}")
def fiche_client(request: Request, cid: int, u=Depends(admin), db: SessionDB = Depends(session_db)):
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(404)
    return page(request, "admin_client.html", u, client=client, tenants=tenants_connus(db))


@routes.post("/clients", dependencies=[Depends(verifier_csrf)])
@routes.post("/clients/{cid}", dependencies=[Depends(verifier_csrf)])
def enregistrer_client(request: Request, cid: int | None = None, nom: str = Form(...),
                       avec_mdr: bool = Form(False), avec_ksc: bool = Form(False), suggerer_mdr: bool = Form(False),
                       tenants_mdr: str = Form(""), notes: str = Form(""), actif: bool = Form(False),
                       u=Depends(admin), db: SessionDB = Depends(session_db)):
    client = db.get(Client, cid) if cid else Client()
    if cid and client is None:
        raise HTTPException(404)
    nom = nom.strip()
    tenants = [t.strip() for t in re.split(r"[\n,;]", tenants_mdr) if t.strip()]
    erreur = None
    if not nom:
        erreur = "Le nom du client est obligatoire."
    elif not (avec_mdr or avec_ksc):
        erreur = "Le client doit avoir au moins un service : MDR ou KSC."
    elif avec_mdr and not tenants:
        erreur = "Indiquez au moins un tenant MDR (tel qu'il apparaît dans les rapports hebdomadaires)."
    else:
        doublon = db.scalar(select(Client).where(func.lower(Client.nom) == nom.lower(), Client.id != (cid or 0)))
        if doublon:
            erreur = f"Un client « {doublon.nom} » existe déjà."
    if erreur:
        brouillon = Client(id=cid, nom=nom, avec_mdr=avec_mdr, avec_ksc=avec_ksc, suggerer_mdr=suggerer_mdr,
                           tenants_mdr=tenants, notes=notes, actif=actif)
        return page(request, "admin_client.html", u, client=brouillon, tenants=tenants_connus(db), erreur=erreur)

    client.nom, client.avec_mdr, client.avec_ksc = nom, avec_mdr, avec_ksc
    client.suggerer_mdr = suggerer_mdr and not avec_mdr
    client.tenants_mdr = tenants if avec_mdr else []
    client.notes, client.actif = notes.strip(), actif if cid else True
    if not cid:
        db.add(client)
    journaliser(db, u, "modification client" if cid else "création client", f"{nom} ({client.profil})")
    db.commit()
    flash(request, f"Client {nom} enregistré.")
    return rediriger("/admin/clients")


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #
@routes.get("/journal")
def journal(request: Request, u=Depends(admin), db: SessionDB = Depends(session_db)):
    lignes = db.scalars(select(Journal).order_by(Journal.quand.desc()).limit(300)).all()
    return page(request, "admin_journal.html", u, lignes=lignes)

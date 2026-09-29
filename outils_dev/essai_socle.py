"""Test de bout en bout du socle (comptes, rôles, CSRF, clients). Nettoie ses données à la fin.

    python -m outils_dev.essai_socle        (depuis le dossier « plateforme »)
"""
import re

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import Session
from app.main import app
from app.modeles import Client, Journal, Utilisateur
from app.securite import hacher

PREFIXE = "essai.socle"
MDP = "MotDePasse2026!"


def csrf(reponse):
    return re.search(r'name="csrf" value="([^"]+)"', reponse.text).group(1)


def connecter(client_http, email, mdp=MDP):
    r = client_http.get("/connexion")
    return client_http.post("/connexion", data={"email": email, "mot_de_passe": mdp, "csrf": csrf(r)},
                            follow_redirects=False)


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def main():
    with Session() as db:
        for role in ("admin", "operateur", "lecteur"):
            db.add(Utilisateur(email=f"{PREFIXE}.{role}@esay.local", nom=f"Essai {role}", role=role,
                               mot_de_passe=hacher(MDP), doit_changer_mdp=(role == "lecteur")))
        db.commit()
    try:
        with TestClient(app) as http:
            verifier(http.get("/", follow_redirects=False).headers["location"] == "/connexion",
                     "page protégée sans session -> connexion")
            r = connecter(http, f"{PREFIXE}.admin@esay.local", "mauvais")
            verifier("incorrect" in r.text, "mauvais mot de passe refusé")
            r = http.post("/connexion", data={"email": "x", "mot_de_passe": "y", "csrf": "faux"})
            verifier(r.status_code == 400, "formulaire sans jeton CSRF valide refusé")

            r = connecter(http, f"{PREFIXE}.admin@esay.local")
            verifier(r.headers["location"] == "/", "connexion administrateur")
            r = http.get("/")
            verifier("HUDSON" in r.text and "Tableau de bord" in r.text, "tableau de bord avec les clients")
            r = http.get("/admin/clients")
            verifier("root tenant" in r.text, "liste des clients avec tenants")

            jeton = csrf(http.get("/admin/clients/nouveau"))
            r = http.post("/admin/clients", data={"csrf": jeton, "nom": "ESSAI KSC", "avec_ksc": "true",
                                                  "suggerer_mdr": "true", "actif": "true"}, follow_redirects=True)
            verifier("ESSAI KSC" in r.text and "KSC seul" in r.text, "création d'un client KSC seul")
            r = http.post("/admin/clients", data={"csrf": jeton, "nom": "ESSAI MDR", "avec_mdr": "true", "actif": "true"})
            verifier("au moins un tenant" in r.text, "client MDR sans tenant refusé")
            r = http.post("/admin/clients", data={"csrf": jeton, "nom": "essai ksc", "avec_ksc": "true", "actif": "true"})
            verifier("existe déjà" in r.text, "doublon de nom refusé")

            r = http.post("/admin/utilisateurs", data={"csrf": jeton, "nom": "Essai créé", "role": "validateur",
                                                       "email": f"{PREFIXE}.cree@esay.local"}, follow_redirects=True)
            verifier("Mot de passe provisoire" in r.text, "création d'un compte avec mot de passe provisoire")

        with TestClient(app) as http:
            connecter(http, f"{PREFIXE}.operateur@esay.local")
            verifier(http.get("/").status_code == 200, "opérateur : accès au tableau de bord")
            verifier(http.get("/admin/clients").status_code == 403, "opérateur : administration interdite")

        with TestClient(app) as http:
            r = connecter(http, f"{PREFIXE}.lecteur@esay.local")
            verifier(r.headers["location"] == "/mon-compte", "mot de passe provisoire -> changement obligatoire")
            verifier(http.get("/", follow_redirects=False).headers["location"] == "/mon-compte",
                     "navigation bloquée tant que le mot de passe n'est pas changé")
            jeton = csrf(http.get("/mon-compte"))
            r = http.post("/mon-compte", data={"csrf": jeton, "actuel": MDP, "nouveau": "court", "confirmation": "court"})
            verifier("10 caractères" in r.text, "mot de passe trop court refusé")
            r = http.post("/mon-compte", data={"csrf": jeton, "actuel": MDP, "nouveau": "NouveauMdp2026",
                                               "confirmation": "NouveauMdp2026"}, follow_redirects=True)
            verifier("Mot de passe modifié" in r.text, "changement de mot de passe puis accès")
    finally:
        with Session() as db:
            ids = db.scalars(select(Utilisateur.id).where(Utilisateur.email.like(f"{PREFIXE}%"))).all()
            db.execute(delete(Journal).where(Journal.utilisateur_id.in_(ids)))
            db.execute(delete(Utilisateur).where(Utilisateur.id.in_(ids)))
            db.execute(delete(Client).where(Client.nom.like("ESSAI%")))
            db.commit()
        print("Données d'essai supprimées.")


if __name__ == "__main__":
    main()

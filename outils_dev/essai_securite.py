"""Test de bout en bout de la phase 1 (socle sécurisé) : verrouillage, message d'erreur uniforme, double
authentification (activation, connexion, rejeu, désactivation, réinitialisation), invalidation des sessions,
déconnexion par POST, journal chaîné. Supprime ses comptes à la fin (les lignes du journal sont conservées).

    python -m outils_dev.essai_securite        (depuis le dossier « plateforme »)
"""
import re
import time

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import config, integrite, totp
from app.db import Session
from app.main import app
from app.modeles import Journal, Utilisateur
from app.securite import hacher, limiteur_ip

PREFIXE, MDP = "essai.securite", "MotDePasse2026!"


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(texte):
    return re.search(r'name="csrf" value="([^"]+)"', texte).group(1)


def connexion(http, email, mdp):
    r = http.get("/connexion")
    return http.post("/connexion", data={"email": email, "mot_de_passe": mdp, "csrf": jeton(r.text)}, follow_redirects=False)


def main():
    emails = {r: f"{PREFIXE}.{r}@esay.local" for r in ("admin", "operateur")}
    with Session() as db:
        for role, email in emails.items():
            db.add(Utilisateur(email=email, nom=f"Essai {role}", role=role, mot_de_passe=hacher(MDP), doit_changer_mdp=False))
        db.commit()
        ids = db.scalars(select(Utilisateur.id).where(Utilisateur.email.like(f"{PREFIXE}%"))).all()
        premiere_ligne = (db.scalar(select(Journal.id).order_by(Journal.id.desc()).limit(1)) or 0) + 1
    limiteur_ip.reinitialiser("testclient")
    try:
        # --- Verrouillage et message uniforme
        http = TestClient(app)
        r = connexion(http, "inconnu@esay.local", "x")
        message_inconnu = re.search(r'class="message erreur"><div>([^<]+)', r.text).group(1)
        for _ in range(config.VERROUILLAGE_ECHECS):
            r = connexion(http, emails["operateur"], "mauvais")
        message_verrouille = re.search(r'class="message erreur"><div>([^<]+)', r.text).group(1)
        verifier(message_inconnu == message_verrouille, "même message pour un compte inconnu et un compte verrouillé")
        r = connexion(http, emails["operateur"], MDP)
        verifier(r.status_code == 200 and "Connexion impossible" in r.text, "compte verrouillé : le bon mot de passe est refusé")
        with Session() as db:
            u = db.scalar(select(Utilisateur).where(Utilisateur.email == emails["operateur"]))
            verifier(u.bloque_jusqua is not None, "verrouillage enregistré en base")
            actions = db.scalars(select(Journal.action).where(Journal.id >= premiere_ligne)).all()
            verifier(actions.count("échec de connexion") >= config.VERROUILLAGE_ECHECS and "compte verrouillé" in actions,
                     "échecs et verrouillage journalisés (compte inconnu compris)")

        # --- Déverrouillage par un administrateur, invalidation de session
        limiteur_ip.reinitialiser("testclient")
        adm = TestClient(app)
        verifier(connexion(adm, emails["admin"], MDP).headers["location"] == "/", "connexion administrateur")
        page = adm.get("/admin/utilisateurs").text
        verifier("verrouillé jusqu" in page, "administration : compte signalé verrouillé")
        adm.post(f"/admin/utilisateurs/{u.id}/deverrouiller", data={"csrf": jeton(page)})
        op = TestClient(app)
        verifier(connexion(op, emails["operateur"], MDP).headers["location"] == "/production", "déverrouillé : connexion possible")
        op2 = TestClient(app)
        connexion(op2, emails["operateur"], MDP)
        verifier(op2.get("/production", follow_redirects=False).status_code == 200, "seconde session ouverte")
        page = op.get("/mon-compte").text
        op.post("/mon-compte", data={"csrf": jeton(page), "actuel": MDP, "nouveau": "NouveauMdp2026", "confirmation": "NouveauMdp2026"})
        verifier(op2.get("/production", follow_redirects=False).headers.get("location") == "/connexion",
                 "changement de mot de passe : l'autre session est fermée")
        verifier(op.get("/production", follow_redirects=False).status_code == 200, "la session courante reste ouverte")

        # --- Double authentification
        page = op.get("/mon-compte").text
        r = op.post("/mon-compte/2fa/preparer", data={"csrf": jeton(page)}, follow_redirects=True)
        cle = re.search(r'class="cle-2fa">([A-Z2-7 ]+)<', r.text).group(1).replace(" ", "")
        verifier("<svg" in r.text and len(cle) == 32, "activation : QR code et clé affichés")
        r = op.post("/mon-compte/2fa/activer", data={"csrf": jeton(r.text), "code": "000000"}, follow_redirects=True)
        verifier("Code incorrect" in r.text, "activation refusée avec un mauvais code")
        r = op.post("/mon-compte/2fa/activer", data={"csrf": jeton(r.text), "code": totp.code(cle)}, follow_redirects=True)
        verifier("Double authentification activée" in r.text, "activation avec le code de l'application")

        op3 = TestClient(app)
        r = connexion(op3, emails["operateur"], "NouveauMdp2026")
        verifier(r.headers["location"] == "/connexion/code", "connexion : code demandé après le mot de passe")
        verifier(op3.get("/production", follow_redirects=False).headers.get("location") == "/connexion",
                 "sans code : aucun accès")
        page = op3.get("/connexion/code").text
        r = op3.post("/connexion/code", data={"csrf": jeton(page), "code": "123456"})
        verifier("Code incorrect" in r.text, "mauvais code refusé")
        # attendre un nouveau pas si le code courant a déjà servi à l'activation
        with Session() as db:
            dernier = db.scalar(select(Utilisateur.totp_dernier_pas).where(Utilisateur.email == emails["operateur"]))
        while totp.pas_courant() <= dernier:
            time.sleep(1)
        bon = totp.code(cle)
        r = op3.post("/connexion/code", data={"csrf": jeton(page), "code": bon}, follow_redirects=False)
        verifier(r.headers.get("location") == "/production", "bon code : connexion")
        op4 = TestClient(app)
        connexion(op4, emails["operateur"], "NouveauMdp2026")
        r = op4.post("/connexion/code", data={"csrf": jeton(op4.get("/connexion/code").text), "code": bon})
        verifier("Code incorrect ou déjà utilisé" in r.text, "rejeu du même code refusé")

        page = adm.get("/admin/utilisateurs").text
        verifier(">2FA<" in page, "administration : double authentification signalée")
        adm.post(f"/admin/utilisateurs/{u.id}/reinitialiser-2fa", data={"csrf": jeton(page)})
        verifier(op3.get("/production", follow_redirects=False).headers.get("location") == "/connexion",
                 "réinitialisation 2FA par l'administrateur : sessions fermées")
        with Session() as db:
            verifier(not db.scalar(select(Utilisateur.totp_actif).where(Utilisateur.email == emails["operateur"])),
                     "double authentification désactivée en base")

        # --- 2FA obligatoire pour un rôle
        config.EXIGER_2FA_ROLES[:] = ["admin"]
        verifier(adm.get("/production", follow_redirects=False).headers.get("location") == "/mon-compte",
                 "2FA obligatoire pour les administrateurs : redirection vers Mon compte")
        config.EXIGER_2FA_ROLES[:] = []

        # --- Déconnexion
        verifier(adm.get("/deconnexion", follow_redirects=False).headers.get("location") == "/mon-compte"
                 and adm.get("/production", follow_redirects=False).status_code == 200, "un simple lien ne déconnecte pas")
        adm.post("/deconnexion", data={"csrf": jeton(adm.get("/production").text)})
        verifier(adm.get("/production", follow_redirects=False).headers.get("location") == "/connexion", "déconnexion par formulaire")

        # --- Journal chaîné
        with Session() as db:
            r = integrite.verifier(db)
        verifier(r["ok"], f"journal intègre après le scénario ({r['lignes']} lignes)")
        page = TestClient(app)
        connexion(page, emails["admin"], MDP)
        verifier("Intégrité vérifiée" in page.get("/admin/journal").text, "page Journal : intégrité affichée")
    finally:
        config.EXIGER_2FA_ROLES[:] = []
        limiteur_ip.reinitialiser("testclient")
        with Session() as db:
            db.execute(delete(Utilisateur).where(Utilisateur.id.in_(ids)))  # le journal garde ses lignes (acteur figé)
            db.commit()
            verifier(integrite.verifier(db)["ok"], "suppression des comptes d'essai : chaîne intacte")
        print("Comptes d'essai supprimés (lignes du journal conservées).")


if __name__ == "__main__":
    main()

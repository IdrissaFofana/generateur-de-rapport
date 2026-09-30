"""Test des dépôts : hebdos + exports HUDSON réels, fichier invalide, doublon, tableau de bord, aperçu.
Les dépôts valides (données réelles de septembre) sont conservés ; le compte d'essai est supprimé.

    python -m outils_dev.essai_depots        (depuis le dossier « plateforme »)
"""
import glob
import os
import re
import time

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.db import Session
from app.main import app
from app.modeles import Client, ExportKsc, Hebdo, Journal, Utilisateur
from app.securite import hacher

RACINE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
EMAIL, MDP = "essai.depots@esay.local", "MotDePasse2026!"


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(r):
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def attendre(modele, limite=900):
    debut = time.time()
    while time.time() - debut < limite:
        with Session() as db:
            restants = db.scalar(select(modele.id).where(modele.statut.in_(("en_attente", "en_cours"))))
        if restants is None:
            return True
        time.sleep(3)
    return False


def main():
    with Session() as db:
        db.add(Utilisateur(email=EMAIL, nom="Essai dépôts", role="operateur", mot_de_passe=hacher(MDP),
                           doit_changer_mdp=False))
        db.commit()
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
    try:
        with TestClient(app) as http:
            r = http.get("/connexion")
            http.post("/connexion", data={"email": EMAIL, "mot_de_passe": MDP, "csrf": jeton(r)})
            csrf = jeton(http.get("/hebdos"))

            hebdos = sorted(glob.glob(os.path.join(RACINE, "HEBDO", "*.pdf")))
            fichiers = [("fichiers", (os.path.basename(f), open(f, "rb"), "application/pdf")) for f in hebdos]
            r = http.post("/hebdos?annee=2026&mois=9", data={"csrf": csrf}, files=fichiers, follow_redirects=True)
            verifier("4 fichier(s) déposé(s)" in r.text or "déjà été déposé" in r.text, "dépôt de 4 hebdos")
            r = http.post("/hebdos", data={"csrf": csrf}, files=[("fichiers", (os.path.basename(hebdos[0]),
                          open(hebdos[0], "rb"), "application/pdf"))], follow_redirects=True)
            verifier("déjà été déposé" in r.text, "doublon d'hebdo détecté")
            r = http.post("/hebdos", data={"csrf": csrf}, files=[("fichiers", ("note.txt", b"bonjour", "text/plain"))],
                          follow_redirects=True)
            verifier("pas un fichier PDF" in r.text, "fichier non PDF refusé")

            base = f"/clients/{hudson.id}/2026/9"
            exports = glob.glob(os.path.join(RACINE, "HUDSON", "Rapport sur*.pdf"))
            faux = os.path.join(RACINE, "HUDSON", "Rapport_Sec_FEV2026.pdf")
            fichiers = [("fichiers", (os.path.basename(f), open(f, "rb"), "application/pdf")) for f in exports + [faux]]
            r = http.post(base + "/exports", data={"csrf": csrf}, files=fichiers, follow_redirects=True)
            verifier("export(s) déposé(s)" in r.text or "déjà été déposé" in r.text, "dépôt des exports HUDSON + un faux")

            t0 = time.time()
            verifier(attendre(Hebdo) and attendre(ExportKsc), f"analyses terminées ({time.time() - t0:.0f} s)")
            with Session() as db:
                faux_export = db.scalar(select(ExportKsc).where(ExportKsc.fichier == "Rapport_Sec_FEV2026.pdf"))
                verifier(faux_export.statut == "erreur" and "reconnu" in faux_export.erreur, "faux export signalé en erreur")
                types = sorted(e.type for e in db.scalars(select(ExportKsc).where(
                    ExportKsc.client_id == hudson.id, ExportKsc.statut == "ok")))
                verifier(types == ["menaces", "protection", "vulnerabilites"], "3 types reconnus automatiquement")
            r = http.post(f"/exports/{faux_export.id}/supprimer", data={"csrf": csrf}, follow_redirects=True)
            verifier("supprimé" in r.text, "suppression du faux export")

            r = http.get("/production?annee=2026&mois=9")
            verifier("27/30 jours" in r.text and "Partiel" in r.text, "tableau de bord : couverture MDR et état")
            r = http.get(base + "/apercu")
            texte = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
            verifier("Critique" in texte and re.search(r"Menaces détections 462 ", texte)
                     and re.search(r"Vulnérabilités critiques 71 / 199 ", texte),
                     "aperçu : risque et chiffres de HUDSON")
            anare = http.get("/production?annee=2026&mois=9").text
            verifier(anare.count("Aucune donnée") == 0, "ANARE retrouvé via le tenant racine")
    finally:
        with Session() as db:
            uid = db.scalar(select(Utilisateur.id).where(Utilisateur.email == EMAIL))
            db.execute(update(Hebdo).where(Hebdo.depose_par_id == uid).values(depose_par_id=None))
            db.execute(update(ExportKsc).where(ExportKsc.depose_par_id == uid).values(depose_par_id=None))
            db.execute(delete(Journal).where(Journal.utilisateur_id == uid))
            db.execute(delete(Utilisateur).where(Utilisateur.id == uid))
            db.commit()
        print("Compte d'essai supprimé (les dépôts réels de septembre sont conservés).")


if __name__ == "__main__":
    main()

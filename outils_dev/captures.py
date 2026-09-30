"""Captures d'écran des pages principales (Chrome sans fenêtre), pour relecture visuelle.

    python -m outils_dev.captures <dossier_sortie>        (depuis le dossier « plateforme »)
"""
import os
import re
import subprocess
import sys

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import Session
from app.main import app
from app.modeles import Client, Journal, Rapport, Utilisateur
from app.securite import hacher

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
STATIQUE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static")).replace("\\", "/")
EMAIL, MDP = "essai.captures@esay.local", "MotDePasse2026!"


def capturer(html, nom, sortie, hauteur=1100):
    html = html.replace('href="/static/', f'href="file:///{STATIQUE}/').replace('src="/static/', f'src="file:///{STATIQUE}/')
    html = re.sub(r'<script src="file:///[^"]+htmx[^"]+"[^>]*></script>', "", html)
    source = os.path.join(sortie, nom + ".html")
    with open(source, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars", "--force-prefers-reduced-motion",
                    f"--window-size=1400,{hauteur}", f"--screenshot={os.path.join(sortie, nom + '.png')}",
                    "file:///" + source.replace("\\", "/")], check=True, capture_output=True, timeout=60)
    os.remove(source)


def main(sortie):
    os.makedirs(sortie, exist_ok=True)
    with Session() as db:
        db.add(Utilisateur(email=EMAIL, nom="Awa Koné", role="admin", mot_de_passe=hacher(MDP), doit_changer_mdp=False))
        db.commit()
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
    try:
        with TestClient(app) as http:
            capturer(http.get("/connexion").text, "01_connexion", sortie, 700)
            r = http.get("/connexion")
            csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
            http.post("/connexion", data={"email": EMAIL, "mot_de_passe": MDP, "csrf": csrf})
            capturer(http.get("/production?annee=2026&mois=9").text, "02_tableau", sortie, 700)
            capturer(http.get("/hebdos?annee=2026&mois=9").text, "03_hebdos", sortie, 1100)
            base = f"/clients/{hudson.id}/2026/9"
            fiche = http.get(base).text
            fiche = fiche.replace('<p class="aide">Calcul en cours…</p>', http.get(base + "/apercu").text)
            capturer(fiche, "04_fiche_client", sortie, 1500)
            csrf = re.search(r'name="csrf" value="([^"]+)"', fiche).group(1)
            r = http.post(base + "/rapports", data={"csrf": csrf}, follow_redirects=False)
            capturer(http.get(r.headers["location"]).text, "05_relecture", sortie, 1600)
            capturer(http.get(f"/admin/clients/{hudson.id}").text, "06_client_admin", sortie, 900)
            capturer(http.get("/admin/utilisateurs").text, "07_utilisateurs", sortie, 700)
    finally:
        with Session() as db:
            uid = db.scalar(select(Utilisateur.id).where(Utilisateur.email == EMAIL))
            db.execute(delete(Rapport).where(Rapport.cree_par_id == uid))
            db.execute(delete(Journal).where(Journal.utilisateur_id == uid))
            db.execute(delete(Utilisateur).where(Utilisateur.id == uid))
            db.commit()


if __name__ == "__main__":
    main(sys.argv[1])

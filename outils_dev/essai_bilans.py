"""Test des évolutions multi-mois, des bilans, des actions groupées, du journal et de la règle de fin de mois.
Crée des rapports mensuels validés fictifs pour HUDSON (juillet, août, septembre 2026) à partir des données
de septembre, puis supprime tout ce qu'il a créé (comptes, rapports, PDF, journal).

    python -m outils_dev.essai_bilans        (depuis le dossier « plateforme », après essai_depots)
"""
import copy
import io
import re
import zipfile
from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app import services
from app.db import Session
from app.main import app
from app.modeles import Alerte, VALIDE, Client, Rapport, Utilisateur
from app.moteur import bilan as mbilan
from app.moteur.analyse import analyser_mdr
from app.securite import hacher
from app.stockage import supprimer

EMAIL, MDP = "essai.bilans@esay.local", "MotDePasse2026!"
# Indicateurs fictifs des mois précédents (septembre = données réelles déposées)
FICTIFS = {7: {"appareils_critiques": 30, "detections": 210, "vulnerabilites_critiques": 95},
           8: {"appareils_critiques": 41, "detections": 380, "vulnerabilites_critiques": 80}}


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(r):
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def regle_fin_de_mois():
    """Règle pure : un jour dont l'hebdo ne peut pas encore être paru n'est pas manquant."""
    hebdo = {"postes": {"X": {date(2026, 9, j): 10 for j in range(1, 28)}}, "incidents": [],
             "debut": date(2026, 9, 21), "fin": date(2026, 9, 28), "fichier": "s4"}
    fin_mois = (date(2026, 9, 1), date(2026, 10, 1))
    le_29 = analyser_mdr([hebdo], {"X"}, *fin_mois, aujourd_hui=date(2026, 9, 29))
    verifier(len(le_29["jours_manquants"]) == 3 and len(le_29["jours_a_venir"]) == 3,
             "29/09 : les 28-30/09 sont « à venir », pas manquants")
    le_12 = analyser_mdr([hebdo], {"X"}, *fin_mois, aujourd_hui=date(2026, 10, 12))
    verifier(le_12["jours_a_venir"] == [], "12/10 : l'hebdo aurait dû paraître, les 28-30/09 redeviennent manquants")


def main():
    regle_fin_de_mois()
    verifier(mbilan.bornes_periode("trimestriel", 2026, 3) == (date(2026, 7, 1), date(2026, 10, 1)), "bornes du T3 2026")
    verifier(mbilan.bornes_periode("semestriel", 2026, 2) == (date(2026, 7, 1), date(2027, 1, 1)), "bornes du S2 2026")

    with Session() as db:
        u = Utilisateur(email=EMAIL, nom="Essai Bilans", role="admin", mot_de_passe=hacher(MDP), doit_changer_mdp=False)
        db.add(u)
        db.commit()
        uid = u.id
        alerte_max = db.scalar(select(func.max(Alerte.id))) or 0
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
    try:
        with TestClient(app) as http:
            r = http.get("/connexion")
            http.post("/connexion", data={"email": EMAIL, "mot_de_passe": MDP, "csrf": jeton(r)})
            csrf = jeton(http.get("/production"))

            # --- Actions groupées : HUDSON est « Prêt » grâce à la règle de fin de mois
            page = http.get("/production?annee=2026&mois=9").text
            verifier("Créer les brouillons prêts" in page, "tableau de bord : barre d'actions groupées")
            r = http.post("/tableau/brouillons", data={"csrf": csrf, "annee": 2026, "mois": 9}, follow_redirects=True)
            verifier("1 brouillon(s) créé(s) : HUDSON" in r.text, "création groupée : le brouillon HUDSON (seul client prêt)")
            r = http.post("/tableau/actualiser", data={"csrf": csrf, "annee": 2026, "mois": 9}, follow_redirects=True)
            verifier("Chiffres recalculés pour 1 brouillon(s)" in r.text, "actualisation groupée des brouillons")

            # --- Mois précédents validés (fictifs), puis validation de septembre
            with Session() as db:
                sept = services.dernier_rapport(db, hudson.id, 2026, 9)
                for mois, valeurs in FICTIFS.items():
                    debut, fin = date(2026, mois, 1), date(2026, mois + 1, 1)
                    donnees = copy.deepcopy(sept.donnees)
                    donnees.update(mois=mois, debut=debut.isoformat(), fin=fin.isoformat())
                    contenu = copy.deepcopy(sept.contenu)
                    contenu["niveau_risque"] = "Élevé" if mois == 7 else "Critique"
                    if mois == 8:
                        contenu["actions"][0]["action"] = "Action d'août à suivre"
                    db.add(Rapport(client_id=hudson.id, periodicite="mensuel", annee=2026, mois=mois, debut=debut, fin=fin,
                                   version=1, statut=VALIDE, profil=sept.profil, donnees=donnees, contenu=contenu,
                                   indicateurs={**sept.indicateurs, **valeurs}, cree_par_id=uid, valide_par_id=uid,
                                   valide_le=datetime(2026, mois + 1, 3)))
                db.commit()
                sid = sept.id
            http.post(f"/rapports/{sid}/actualiser", data={"csrf": csrf}, follow_redirects=True)  # historique à jour
            with Session() as db:
                historique = db.get(Rapport, sid).donnees["historique"]
            verifier([p["mois"] for p in historique] == [7, 8], "brouillon de septembre : historique juillet-août figé")
            r = http.get(f"/rapports/{sid}/apercu.pdf")
            verifier(r.content.startswith(b"%PDF"), "PDF mensuel avec graphique d'évolution")
            with Session() as db:
                html = services.html_rapport(db.get(Rapport, sid).donnees, db.get(Rapport, sid).contenu, services.PRESTATAIRE)
            verifier("Évolution sur 3 mois" in html and html.count("<svg") >= 5, "PDF mensuel : section « Évolution sur 3 mois »")
            r = http.post(f"/rapports/{sid}/valider", data={"csrf": csrf}, follow_redirects=True)
            verifier("validé" in r.text, "validation de septembre")
            with Session() as db:
                verifier("\\" not in db.get(Rapport, sid).pdf, "chemin du PDF archivé au format « / »")

            # --- Fiche client : courbes
            page = http.get(f"/clients/{hudson.id}/2026/9").text
            verifier("Évolution sur 12 mois" in page and page.count('class="courbe"') >= 3,
                     "fiche client : petites courbes d'évolution")
            verifier("sept. 26 : 46" in page, "infobulle d'un point (septembre : 46 appareils critiques)")
            r = http.get("/tableau/pdf-valides.zip?annee=2026&mois=9")
            noms = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
            verifier(noms == ["Rapport mensuel sécurité - HUDSON - Septembre 2026 - v1.pdf"], "ZIP des PDF validés du mois")

            # --- Bilan T3 2026
            page = http.get("/bilans?periodicite=trimestriel&annee=2026&numero=3").text
            verifier("3e trimestre 2026" in page and "3/3" in page, "page Bilans : HUDSON complet (3/3)")
            r = http.post("/bilans/creer-tous", data={"csrf": csrf, "periodicite": "trimestriel", "annee": 2026, "numero": 3},
                          follow_redirects=True)
            verifier("1 bilan(s) créé(s) : HUDSON" in r.text, "création groupée des bilans complets")
            with Session() as db:
                b = services.dernier_rapport(db, hudson.id, 2026, 7, periodicite="trimestriel")
                bid, d = b.id, b.donnees
            verifier(d["totaux"]["detections"] == 210 + 380 + 462, "bilan : détections cumulées (1 052)")
            verifier(d["totaux"]["appareils_critiques_debut"] == 30 and d["totaux"]["appareils_critiques_fin"] == 46,
                     "bilan : appareils critiques de 30 à 46")
            verifier(d["niveau_max"] == "Critique" and not d["manquants"], "bilan : niveau max et aucun mois manquant")
            verifier(any(a["action"] == "Action d'août à suivre" for a in d["actions"]), "bilan : actions de tous les mois")
            page = http.get(f"/rapports/{bid}").text
            verifier("Perspectives et recommandations" in page and "Mois consolidés" in page, "relecture du bilan")
            b_contenu = {"csrf": csrf, "niveau_risque": "Élevé", "motifs_risque": "Motif de test",
                         "synthese": "Synthèse **modifiée**.", "commentaire_evolution": "Tendance à la hausse.",
                         "perspectives": "Priorité : KSN.", "conclusion": "Conclusion."}
            http.post(f"/rapports/{bid}/contenu", data=b_contenu, follow_redirects=True)
            with Session() as db:
                verifier(db.get(Rapport, bid).contenu["synthese"] == "Synthèse **modifiée**.", "bilan : textes enregistrés")
            r = http.get(f"/rapports/{bid}/apercu.pdf")
            verifier(r.content.startswith(b"%PDF") and len(r.content) > 20000, "aperçu PDF du bilan")
            r = http.post(f"/rapports/{bid}/valider", data={"csrf": csrf}, follow_redirects=True)
            r = http.get(f"/rapports/{bid}/pdf")
            verifier(r.content.startswith(b"%PDF") and "Bilan%20trimestriel" in r.headers["content-disposition"],
                     "bilan validé : PDF téléchargeable")
            verifier(http.get(f"/rapports/{bid}/word").status_code == 400, "pas d'export Word pour un bilan")

            # --- Journal : filtres, pagination, CSV
            page = http.get(f"/admin/journal?utilisateur={uid}&action=création+bilan").text
            verifier("1</span> action(s) correspondant aux filtres" in page and "HUDSON T3 2026 v1" in page,
                     "journal filtré par utilisateur et action")
            page = http.get(f"/admin/journal?utilisateur={uid}&du=2000-01-01&au=2000-01-02").text
            verifier("Aucune action ne correspond" in page, "journal filtré par dates (aucun résultat)")
            r = http.get(f"/admin/journal.csv?utilisateur={uid}")
            verifier(r.text.startswith("﻿Date;Utilisateur") and "validation rapport" in r.text, "export CSV du journal")
    finally:
        with Session() as db:
            for r in db.scalars(select(Rapport).where(Rapport.cree_par_id == uid)):
                if r.pdf:
                    supprimer(r.pdf)
                db.delete(r)
            db.execute(delete(Alerte).where(Alerte.id > alerte_max))
            db.execute(delete(Utilisateur).where(Utilisateur.id == uid))
            db.commit()
        print("Compte, rapports et bilans d'essai supprimés.")


if __name__ == "__main__":
    main()

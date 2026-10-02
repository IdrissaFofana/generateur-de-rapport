"""Test de bout en bout de la supervision (axe R3) : route /metrics protégée par jeton, compteurs par modèle de route,
métriques métier, émission du journal d'audit vers l'extérieur après validation (et pas après annulation),
événements de sécurité au format fail2ban.

    python -m outils_dev.essai_supervision        (depuis le dossier « plateforme »)
"""
import logging
import re

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app import config
from app.db import Session
from app.main import app
from app.modeles import Utilisateur, journaliser
from app.securite import hacher, limiteur_ip

PREFIXE, MDP = "essai.supervision", "MotDePasse2026!"


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def main():
    capture = Capture()
    for nom in ("rapports.journal", "rapports.securite"):
        logging.getLogger(nom).addHandler(capture)
    email = f"{PREFIXE}@esay.local"
    with Session() as db:
        u = Utilisateur(email=email, nom="Essai Supervision", role="admin", mot_de_passe=hacher(MDP), doit_changer_mdp=False)
        db.add(u)
        db.commit()
        uid = u.id
    jeton_initial = config.METRIQUES_JETON
    limiteur_ip.reinitialiser("testclient")
    try:
        http = TestClient(app)
        config.METRIQUES_JETON = ""
        verifier(http.get("/metrics").status_code == 404, "sans jeton configuré : /metrics n'existe pas")
        config.METRIQUES_JETON = "jeton-de-test-0123456789"
        verifier(http.get("/metrics").status_code == 401, "jeton configuré : accès refusé sans jeton")
        verifier(http.get("/metrics", headers={"Authorization": "Bearer mauvais"}).status_code == 401, "mauvais jeton refusé")

        # Trafic : échec puis succès de connexion, quelques pages
        r = http.get("/connexion")
        csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
        http.post("/connexion", data={"email": email, "mot_de_passe": "faux", "csrf": csrf})
        verifier(any(re.fullmatch(r'evenement=echec_connexion ip=testclient compte="essai\.supervision@esay\.local" detail="mot de passe"', m)
                     for m in capture.messages), "événement de sécurité « echec_connexion » au format stable (fail2ban)")
        http.post("/connexion", data={"email": email, "mot_de_passe": MDP, "csrf": csrf})
        verifier(any(m.startswith("evenement=connexion ip=testclient") for m in capture.messages), "événement « connexion »")
        for _ in range(3):
            http.get("/rapports/999999")

        m = http.get("/metrics", headers={"Authorization": "Bearer jeton-de-test-0123456789"})
        texte = m.text
        verifier(m.status_code == 200 and m.headers["content-type"].startswith("text/plain; version=0.0.4"), "bon jeton : format Prometheus")
        verifier('rapports_esay_requetes_total{methode="GET",route="/rapports/{rid}",statut="4xx"} 3' in texte,
                 "requêtes regroupées par modèle de route (/rapports/{rid}), sans identifiant réel")
        verifier('route="/metrics"' not in texte, "la route /metrics ne se compte pas elle-même")
        verifier(re.search(r'rapports_esay_requete_duree_secondes_bucket\{methode="POST",route="/connexion",le="\+Inf"\} \d+', texte),
                 "histogramme des durées")
        verifier("rapports_esay_journal_integre 1" in texte and "rapports_esay_imports_en_attente" in texte
                 and "rapports_esay_analyses{" in texte, "métriques métier : intégrité du journal, analyses, imports")

        # Journal d'audit émis après validation seulement
        capture.messages.clear()
        with Session() as db:
            journaliser(db, db.get(Utilisateur, uid), "essai supervision annulée", "ne doit pas partir")
            db.rollback()
            journaliser(db, db.get(Utilisateur, uid), "essai supervision validée", "doit partir")
            db.commit()
        verifier(not any("annulée" in x for x in capture.messages), "ligne de journal annulée : rien n'est émis")
        verifier(any(re.search(r'action="essai supervision validée" .* empreinte=[0-9a-f]{64}$', x) for x in capture.messages),
                 "ligne validée émise avec son empreinte (copie externe de la chaîne)")
    finally:
        config.METRIQUES_JETON = jeton_initial
        limiteur_ip.reinitialiser("testclient")
        for nom in ("rapports.journal", "rapports.securite"):
            logging.getLogger(nom).removeHandler(capture)
        with Session() as db:
            db.execute(delete(Utilisateur).where(Utilisateur.id == uid))
            db.commit()
        print("Compte d'essai supprimé (lignes du journal conservées).")


if __name__ == "__main__":
    main()

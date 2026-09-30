"""Test du cycle de vie des rapports : brouillon, relecture, droits, validation, versions, suivi des actions.
Supprime ses comptes et ses rapports à la fin (les fichiers déposés sont conservés).

    python -m outils_dev.essai_rapports        (depuis le dossier « plateforme », après essai_depots)
"""
import re

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db import Session
from app.main import app
from app.modeles import Alerte, Client, Rapport, Utilisateur
from app.securite import hacher
from app.stockage import supprimer

PREFIXE, MDP = "essai.rapports", "MotDePasse2026!"


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(r):
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def session(role):
    http = TestClient(app)
    r = http.get("/connexion")
    http.post("/connexion", data={"email": f"{PREFIXE}.{role}@esay.local", "mot_de_passe": MDP, "csrf": jeton(r)})
    return http


def formulaire_depuis(contenu, csrf, **changements):
    """Reproduit l'envoi du formulaire de relecture."""
    donnees = [("csrf", csrf), ("niveau_risque", contenu["niveau_risque"]),
               ("motifs_risque", "\n".join(contenu["motifs_risque"])), ("synthese", contenu["synthese"]),
               ("suggestion_mdr", contenu["suggestion_mdr"]), ("conclusion", contenu["conclusion"])]
    donnees += [(f"com_{k}", v) for k, v in contenu["commentaires"].items()]
    for a in changements.pop("actions", contenu["actions"]):
        donnees += [("action", a["action"]), ("pourquoi", a["pourquoi"]), ("priorite", a["priorite"]),
                    ("responsable", a["responsable"])]
    for a in contenu.get("suivi", []):
        donnees += [("suivi_action", a["action"]), ("suivi_priorite", a["priorite"]),
                    ("suivi_responsable", a["responsable"]), ("suivi_statut", changements.get("suivi_statut", a["statut"])),
                    ("suivi_commentaire", "")]
    groupes = {}
    for k, v in donnees:
        groupes.setdefault(k, []).append(v)
    return {k: v for k, v in changements.items() if k != "suivi_statut"}, groupes


def main():
    with Session() as db:
        for role in ("validateur", "operateur", "lecteur"):
            db.add(Utilisateur(email=f"{PREFIXE}.{role}@esay.local", nom=f"Essai {role}", role=role,
                               mot_de_passe=hacher(MDP), doit_changer_mdp=False))
        db.commit()
        alerte_max = db.scalar(select(func.max(Alerte.id))) or 0
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
    base = f"/clients/{hudson.id}/2026/9"
    try:
        with TestClient(app):
            op, val, lec = session("operateur"), session("validateur"), session("lecteur")

            r = op.post(base + "/rapports", data={"csrf": jeton(op.get(base))}, follow_redirects=False)
            rid = int(r.headers["location"].rsplit("/", 1)[1])
            verifier(r.status_code == 303, "opérateur : création du brouillon")
            with Session() as db:
                rapport = db.get(Rapport, rid)
                verifier(rapport.version == 1 and rapport.contenu["niveau_risque"] == "Critique"
                         and len(rapport.contenu["actions"]) == 17, "brouillon v1 : risque Critique, 17 actions")
                contenu = rapport.contenu

            r = op.post(base + "/rapports", data={"csrf": jeton(op.get(base))}, follow_redirects=False)
            verifier(r.headers["location"] == f"/rapports/{rid}", "un seul brouillon à la fois")
            r = op.get(f"/rapports/{rid}")
            verifier("Lecture seule" in r.text, "opérateur : relecture en lecture seule")
            _, donnees = formulaire_depuis(contenu, jeton(r))
            r = op.post(f"/rapports/{rid}/contenu", data=donnees)
            verifier(r.status_code == 403, "opérateur : modification refusée")
            verifier(lec.get(f"/rapports/{rid}").status_code == 403, "lecteur : brouillon inaccessible")

            r = val.get(f"/rapports/{rid}")
            csrf = jeton(r)
            actions = contenu["actions"][1:] + [{"action": "Action ajoutée à la main", "pourquoi": "Test",
                                                 "priorite": "Haute", "responsable": "ESAY"}]
            _, donnees = formulaire_depuis(contenu, csrf, actions=actions)
            donnees["synthese"] = ["Synthèse **modifiée** par le validateur."]
            r = val.post(f"/rapports/{rid}/contenu", data=donnees, follow_redirects=True)
            verifier("Modifications enregistrées" in r.text, "validateur : textes et actions modifiés")
            with Session() as db:
                c = db.get(Rapport, rid).contenu
                verifier(c["synthese"].startswith("Synthèse **modifiée**") and len(c["actions"]) == 17
                         and c["actions"][-1]["action"] == "Action ajoutée à la main", "modifications bien enregistrées")

            r = val.post(f"/rapports/{rid}/actualiser", data={"csrf": csrf}, follow_redirects=True)
            verifier("textes ont été conservés" in r.text, "actualisation des chiffres sans perte des textes")
            with Session() as db:
                verifier(db.get(Rapport, rid).contenu["synthese"].startswith("Synthèse **modifiée**"), "textes intacts")

            r = val.get(f"/rapports/{rid}/apercu.pdf")
            verifier(r.status_code == 200 and r.content.startswith(b"%PDF"), f"aperçu PDF ({len(r.content) // 1024} Ko)")
            r = val.post(f"/rapports/{rid}/valider", data={"csrf": csrf}, follow_redirects=True)
            verifier("validé" in r.text, "validation")
            r = val.post(f"/rapports/{rid}/contenu", data=donnees)
            verifier(r.status_code == 400, "rapport validé : plus modifiable")

            r = lec.get(f"/rapports/{rid}/pdf")
            verifier(r.status_code == 200 and r.content.startswith(b"%PDF")
                     and "v1.pdf" in r.headers["content-disposition"], "lecteur : téléchargement du PDF validé")
            fiche = lec.get(base).text
            verifier("Validé" in fiche and "Télécharger le PDF" in fiche and "Déposer" not in fiche,
                     "lecteur : rapport validé visible, pas de dépôt possible")

            r = val.post(f"/rapports/{rid}/nouvelle-version", data={"csrf": csrf}, follow_redirects=False)
            rid2 = int(r.headers["location"].rsplit("/", 1)[1])
            with Session() as db:
                v2 = db.get(Rapport, rid2)
                verifier(v2.version == 2 and v2.statut == "brouillon"
                         and v2.contenu["synthese"].startswith("Synthèse **modifiée**"), "v2 créée avec les textes de la v1")
                db.delete(v2)
                db.commit()

            octobre = f"/clients/{hudson.id}/2026/10"
            r = op.post(octobre + "/rapports", data={"csrf": jeton(op.get(octobre))}, follow_redirects=False)
            rid_oct = int(r.headers["location"].rsplit("/", 1)[1])
            with Session() as db:
                suivi = db.get(Rapport, rid_oct).contenu["suivi"]
                verifier(len(suivi) == 17 and suivi[-1]["action"] == "Action ajoutée à la main",
                         "octobre : les 17 actions ouvertes de septembre sont reprises dans le suivi")
            r = val.get(f"/rapports/{rid_oct}/apercu.pdf")
            verifier(r.content.startswith(b"%PDF"), "aperçu d'un rapport avec suivi (et sans exports KSC d'octobre)")
            for h in (op, val, lec):
                h.close()
    finally:
        with Session() as db:
            for r in db.scalars(select(Rapport).where(Rapport.client_id == hudson.id)):
                if r.pdf:
                    supprimer(r.pdf)
                db.delete(r)
            ids = db.scalars(select(Utilisateur.id).where(Utilisateur.email.like(f"{PREFIXE}%"))).all()
            db.execute(delete(Alerte).where(Alerte.id > alerte_max))
            db.execute(delete(Utilisateur).where(Utilisateur.id.in_(ids)))
            db.commit()
        print("Comptes et rapports d'essai supprimés.")


if __name__ == "__main__":
    main()

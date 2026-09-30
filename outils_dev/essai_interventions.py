"""Test des rapports d'intervention : saisie, bibliothèque, PDF (titre selon le type), envoi, historique, plan d'action.
Supprime ses données à la fin (interventions, éléments de bibliothèque ajoutés, rapports, comptes) et rétablit le client.

    python -m outils_dev.essai_interventions        (depuis le dossier « plateforme », après essai_depots)
"""
import email
import re

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import alertes, config, services
from app.db import Session
from app.main import app
from app.modeles import Client, ElementBibliotheque, Intervention, Rapport, Utilisateur
from app.securite import hacher
from app.stockage import supprimer

PREFIXE, MDP = "essai.interventions", "MotDePasse2026!"
ENVOYES = []


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(texte):
    return re.search(r'name="csrf" value="([^"]+)"', texte).group(1)


class FauxSMTP:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): pass
    def login(self, *a): pass
    def send_message(self, m): ENVOYES.append(m)


def connecter(role):
    http = TestClient(app)
    r = http.get("/connexion")
    http.post("/connexion", data={"email": f"{PREFIXE}.{role}@esay.local", "mot_de_passe": MDP, "csrf": jeton(r.text)})
    return http


def texte_pdf(contenu):
    return re.sub(r"\s+", " ", "".join(p.get_text() for p in fitz.open(stream=contenu, filetype="pdf")))


def main():
    with Session() as db:
        for role in ("operateur", "validateur", "lecteur", "admin"):
            db.add(Utilisateur(email=f"{PREFIXE}.{role}@esay.local", nom=f"Essai {role.capitalize()}", role=role,
                               mot_de_passe=hacher(MDP), doit_changer_mdp=False))
        db.commit()
        ids = db.scalars(select(Utilisateur.id).where(Utilisateur.email.like(f"{PREFIXE}%"))).all()
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
        code_initial, emails_initiaux = hudson.code, list(hudson.emails_rapports or [])
        biblio_max = db.scalar(select(ElementBibliotheque.id).order_by(ElementBibliotheque.id.desc()).limit(1)) or 0
    try:
        op, val, lec, adm = (connecter(r) for r in ("operateur", "validateur", "lecteur", "admin"))

        # --- Création et contexte pré-rempli
        csrf = jeton(op.get("/interventions").text)
        r = op.post("/interventions", data={"csrf": csrf, "client_id": hudson.id, "type": "deploiement", "date_debut": "2026-09-21"},
                    follow_redirects=True)
        verifier("RI-2026-HUD-001" in r.text and "Rapport de déploiement" in r.text, "création : numéro RI-2026-HUD-001, titre selon le type")
        with Session() as db:
            i = db.scalar(select(Intervention).where(Intervention.numero == "RI-2026-HUD-001"))
            iid, contexte = i.id, i.contexte
        verifier(contexte["serveurs"] == "11" and "Windows 11" in contexte["systemes"], "contexte pré-rempli depuis le dernier export KSC")
        verifier("Génération d'un paquet autonome combiné KES + Agent d'administration + module MDR" in r.text
                 and '"recommandation"' in r.text, "formulaire : bibliothèque par type (actions et recommandations)")

        # --- Saisie
        formulaire = {
            "csrf": jeton(r.text), "type": "deploiement", "mode": "site", "interlocuteur": "M. Aka, DSI",
            "intervenants": "Koffi Youann Ange Stéphane\nFofana Tennan Idrissa", "date_debut": "2026-09-21", "date_fin": "2026-09-22",
            "heure_debut": "10:00", "heure_fin": "17:30",
            "objet": "Poursuite du déploiement de **Kaspersky EDR Optimum** et intégration du module MDR.",
            "ctx_postes": "38", "ctx_serveurs": "11", "ctx_systemes": "Windows 11, Windows Server 2022", "ctx_version_ksc": "15.1", "ctx_autres": "",
            "tr_module": ["Kaspersky EDR Optimum"], "tr_resultat": ["OK"], "tr_actions": ["Déploiement de KES"],
            "resultat": ["Génération d'un paquet autonome combiné KES + Agent d'administration + module MDR",
                         "Génération des paquets de points de distribution pour chaque plage d'adresses",
                         "Paramétrage spécifique du proxy KSN de l'essai"],
            "resultat_biblio": ["0", "0", "1"],
            "recommandation": ["Ouvrir les ports 135, 139 et 445 (et 13000, 14000, 15000) pour permettre l'installation à distance"],
            "recommandation_biblio": ["0"],
            "statut_global": "Partiel",
            "pb_probleme": ["Ports 135, 139 et 445 fermés"], "pb_impact": ["Installation à distance de KES impossible"],
            "pb_action": ["Ouvrir les ports 135, 139 et 445 sur le pare-feu"], "pb_responsable": ["HUDSON"],
            "pb_echeance": ["2026-10-15"], "pb_plan": ["1"],
        }
        r = op.post(f"/interventions/{iid}", data=formulaire, follow_redirects=True)
        verifier("1 élément(s) ajouté(s) à la bibliothèque" in r.text, "enregistrement + action personnalisée ajoutée à la bibliothèque")
        with Session() as db:
            i = db.get(Intervention, iid)
            verifier(len(i.resultat) == 3 and i.heure_debut.strftime("%H:%M") == "10:00" and i.points_bloquants[0]["plan_action"],
                     "résultat, heures de passage et point bloquant enregistrés")
            verifier(db.scalar(select(ElementBibliotheque).where(ElementBibliotheque.libelle == "Paramétrage spécifique du proxy KSN de l'essai"))
                     is not None, "bibliothèque : nouvel élément disponible pour les prochains rapports")
        verifier("Paramétrage spécifique du proxy KSN de l&#39;essai" in op.get(f"/interventions/{iid}").text
                 or "Paramétrage spécifique du proxy KSN de l'essai" in op.get(f"/interventions/{iid}").text, "élément visible dans le panneau")

        # --- Aperçu, génération
        r = op.get(f"/interventions/{iid}/apercu.pdf")
        verifier(r.content.startswith(b"%PDF"), "aperçu PDF")
        verifier(lec.get(f"/interventions/{iid}").status_code == 403, "lecteur : brouillon inaccessible")
        r = op.post(f"/interventions/{iid}/valider", data={"csrf": jeton(op.get(f"/interventions/{iid}").text)}, follow_redirects=True)
        verifier("généré" in r.text, "génération du rapport définitif")
        pdf = op.get(f"/interventions/{iid}/pdf")
        texte = texte_pdf(pdf.content)
        verifier("RAPPORT DE DÉPLOIEMENT" in texte and "RI-2026-HUD-001" in texte and "Recommandations" in texte
                 and "Ports 135, 139 et 445 fermés" in texte and "10h00" in texte, "PDF : titre, numéro, heures, points bloquants, recommandations")
        verifier("RI-2026-HUD-001" in pdf.headers["content-disposition"], "nom du fichier PDF")
        verifier(lec.get(f"/interventions/{iid}").status_code == 200, "lecteur : rapport validé consultable")

        # --- Envoi
        page = op.get(f"/interventions/{iid}").text
        r = op.post(f"/interventions/{iid}/envoyer", data={"csrf": jeton(page), "destinataires": "dsi@hudson.ci"}, follow_redirects=True)
        verifier("Envoi impossible" in r.text and "non configuré" in r.text, "envoi sans serveur de messagerie : message clair")
        eml = op.get(f"/interventions/{iid}/brouillon.eml")
        message = email.message_from_bytes(eml.content)
        pieces = [p.get_filename() for p in message.walk() if p.get_filename()]
        verifier(message["X-Unsent"] == "1" and pieces == ["RI-2026-HUD-001 - Rapport de déploiement - HUDSON.pdf"],
                 "brouillon Outlook avec le PDF joint")
        config.SMTP.update(hote="smtp.essai.local", expediteur="rapports@esay.local")
        alertes.smtplib.SMTP = FauxSMTP
        r = op.post(f"/interventions/{iid}/envoyer", data={"csrf": jeton(page), "destinataires": "dsi@hudson.ci, rssi@hudson.ci"},
                    follow_redirects=True)
        verifier("envoyé à dsi@hudson.ci, rssi@hudson.ci" in r.text and len(ENVOYES) == 1
                 and any(p.get_filename() for p in ENVOYES[0].iter_attachments()), "envoi par e-mail avec pièce jointe")

        # --- Duplication, titre selon le type, historique
        r = op.post(f"/interventions/{iid}/dupliquer", data={"csrf": jeton(page)}, follow_redirects=True)
        verifier("RI-2026-HUD-002" in r.text, "duplication : numéro suivant")
        with Session() as db:
            d = db.scalar(select(Intervention).where(Intervention.numero == "RI-2026-HUD-002"))
            verifier(d.objet.startswith("Poursuite") and not d.resultat and d.points_bloquants, "duplication : objet et points repris, résultat vide")
            did = d.id
        formulaire.update(csrf=jeton(r.text), type="migration")
        op.post(f"/interventions/{did}", data=formulaire)
        verifier("Rapport de migration" in op.get(f"/interventions/{did}").text, "changement de type : « Rapport de migration »")
        page = op.get(f"/clients/{hudson.id}/interventions").text
        verifier("RI-2026-HUD-001" in page and "RI-2026-HUD-002" in page and 'class="chronologie"' in page, "historique du client (chronologie)")
        r = op.post(f"/interventions/{did}/supprimer", data={"csrf": jeton(page)}, follow_redirects=True)
        verifier("Brouillon RI-2026-HUD-002 supprimé" in r.text, "suppression d'un brouillon")

        # --- Plan d'action du rapport mensuel
        with Session() as db:
            u = db.get(Utilisateur, min(ids))
            rapport = services.creer_brouillon(db, db.get(Client, hudson.id), 2026, 9, u)
            db.commit()
            actions = [a["action"] for a in rapport.contenu["actions"]]
        verifier("Ouvrir les ports 135, 139 et 445 sur le pare-feu" in actions, "point bloquant repris dans le plan d'action de septembre")

        # --- Code client, bibliothèque, droits
        page = adm.get(f"/admin/clients/{hudson.id}").text
        adm.post(f"/admin/clients/{hudson.id}", data={"csrf": jeton(page), "nom": "HUDSON", "avec_mdr": "true", "avec_ksc": "true",
                                                     "tenants_mdr": "HUDSON", "actif": "true", "code": "hds", "emails_rapports": "dsi@hudson.ci"})
        r = op.post("/interventions", data={"csrf": jeton(op.get("/interventions").text), "client_id": hudson.id, "type": "assistance",
                                            "date_debut": "2026-09-28"}, follow_redirects=True)
        verifier("RI-2026-HDS-002" in r.text and ("Rapport d&#39;assistance" in r.text or "Rapport d'assistance" in r.text),
                 "code client personnalisé (HDS) et titre « Rapport d'assistance »")
        page = op.get("/bibliotheque?type=incident&genre=recommandation").text
        verifier("Changer les mots de passe des comptes exposés" in page, "bibliothèque : recommandations par type")
        r = op.post("/bibliotheque", data={"csrf": jeton(page), "type": "incident", "genre": "action", "categorie": "Essai",
                                           "libelle": "Action d'essai ajoutée"}, follow_redirects=True)
        verifier("Élément ajouté à la bibliothèque" in r.text, "ajout manuel dans la bibliothèque (opérateur)")
        with Session() as db:
            eid = db.scalar(select(ElementBibliotheque.id).where(ElementBibliotheque.libelle == "Action d'essai ajoutée"))
        verifier(op.post(f"/bibliotheque/{eid}/supprimer", data={"csrf": jeton(page)}).status_code == 403,
                 "opérateur : suppression réservée aux validateurs")
        r = val.post(f"/bibliotheque/{eid}/supprimer", data={"csrf": jeton(val.get("/bibliotheque").text)}, follow_redirects=True)
        verifier("supprimé de la bibliothèque" in r.text, "validateur : suppression d'un élément")
        r = val.post(f"/interventions/{iid}/rouvrir", data={"csrf": jeton(val.get("/interventions").text)}, follow_redirects=True)
        verifier("rouvert en modification" in r.text, "validateur : réouverture d'un rapport généré")
    finally:
        with Session() as db:
            for i in db.scalars(select(Intervention).where(Intervention.cree_par_id.in_(ids))):
                if i.pdf:
                    supprimer(i.pdf)
                db.delete(i)
            db.execute(delete(ElementBibliotheque).where(ElementBibliotheque.id > biblio_max))
            for r in db.scalars(select(Rapport).where(Rapport.cree_par_id.in_(ids))):
                db.delete(r)
            client = db.get(Client, hudson.id)
            client.code, client.emails_rapports = code_initial, emails_initiaux
            db.execute(delete(Utilisateur).where(Utilisateur.id.in_(ids)))
            db.commit()
        print("Données d'essai supprimées.")


if __name__ == "__main__":
    main()

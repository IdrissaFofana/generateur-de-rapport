"""Test de bout en bout du service technique : assistances mensuelles, techniciens (formations, certifications,
justificatifs), activités internes, import d'anciens rapports, base de connaissances, rapport d'activité du service.
Utilise les vrais rapports du dossier parent (R-I HUDSON en PDF, rapport BSIC en Word). Nettoie tout à la fin.

    python -m outils_dev.essai_service        (depuis le dossier « plateforme », avec WeasyPrint)
"""
import os
import re
from datetime import date, timedelta

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app import alertes
from app.db import Session
from app.main import app
from app.modeles import (ActiviteInterne, Alerte, AssistancePlanifiee, Certification, Client, ImportEnAttente, Intervention,
                         RapportService, Utilisateur)
from app.securite import hacher
from app.stockage import supprimer

PREFIXE, MDP = "essai.service", "MotDePasse2026!"
DOSSIER = os.path.join(os.path.dirname(__file__), "..", "..")
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 64  # signature PNG suffisante pour le contrôle


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(texte):
    return re.search(r'name="csrf" value="([^"]+)"', texte).group(1)


def connecter(role):
    http = TestClient(app)
    r = http.get("/connexion")
    http.post("/connexion", data={"email": f"{PREFIXE}.{role}@esay.local", "mot_de_passe": MDP, "csrf": jeton(r.text)})
    return http


def main():
    with Session() as db:
        for role, nom in (("admin", "Essai Admin"), ("operateur", "Koffi Essai"), ("operateur2", "Autre Essai"), ("validateur", "Valérie Essai")):
            db.add(Utilisateur(email=f"{PREFIXE}.{role}@esay.local", nom=nom, role="operateur" if role == "operateur2" else role,
                               mot_de_passe=hacher(MDP), doit_changer_mdp=False))
        db.commit()
        ids = db.scalars(select(Utilisateur.id).where(Utilisateur.email.like(f"{PREFIXE}%"))).all()
        op_id = db.scalar(select(Utilisateur.id).where(Utilisateur.email == f"{PREFIXE}.operateur@esay.local"))
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
        anare = db.scalar(select(Client).where(Client.nom == "ANARE"))
        pac = db.scalar(select(Client).where(Client.nom == "PAC CI"))
        etat_initial = {c.id: (c.assistance_mensuelle, c.assistance_depuis) for c in (hudson, anare)}
        maxima = {m: db.scalar(select(func.max(m.id))) or 0 for m in (AssistancePlanifiee, Alerte, ActiviteInterne)}
    try:
        adm, op, op2, val = (connecter(r) for r in ("admin", "operateur", "operateur2", "validateur"))

        # --- Assistance mensuelle sur deux clients
        with Session() as db:
            for c in (db.get(Client, hudson.id), db.get(Client, anare.id)):
                c.assistance_mensuelle, c.assistance_depuis = True, date(2026, 1, 1)
            db.commit()
        page = op.get("/assistances?annee=2026&mois=9").text
        verifier("HUDSON" in page and "ANARE" in page and "À planifier" in page, "planning : assistances de septembre créées automatiquement")
        with Session() as db:
            a_h = db.scalar(select(AssistancePlanifiee).where(AssistancePlanifiee.client_id == hudson.id, AssistancePlanifiee.annee == 2026,
                                                              AssistancePlanifiee.mois == 9))
            a_a = db.scalar(select(AssistancePlanifiee).where(AssistancePlanifiee.client_id == anare.id, AssistancePlanifiee.annee == 2026,
                                                              AssistancePlanifiee.mois == 9))
        op.post(f"/assistances/{a_h.id}", data={"csrf": jeton(page), "date_prevue": "2026-09-29", "technicien_id": str(op_id)})
        page = op.get("/assistances?annee=2026&mois=9").text
        verifier("En retard" in page and "Koffi Essai" in page, "planification : date passée non réalisée → « En retard »")
        with Session() as db:
            nouvelles = alertes.evaluer(db, reference=(2026, 9))
            db.commit()
            titres = [a.titre for a in nouvelles]
        verifier(any("assistance de septembre 2026 pas encore réalisée" in t for t in titres), "alerte : assistance du mois non réalisée (après le 20)")

        r = op.post(f"/assistances/{a_h.id}/rediger", data={"csrf": jeton(page)}, follow_redirects=True)
        verifier("Rapport d&#39;assistance" in r.text or "Rapport d'assistance" in r.text, "rédaction du rapport depuis le planning")
        with Session() as db:
            iid = db.get(AssistancePlanifiee, a_h.id).intervention_id
            i = db.get(Intervention, iid)
            verifier(i.type == "assistance" and i.date_debut == date(2026, 9, 29) and i.intervenants[0] == "Koffi Essai",
                     "rapport lié, daté du jour prévu, technicien planifié en tête")
        formulaire = {"csrf": jeton(r.text), "type": "assistance", "mode": "site", "interlocuteur": "", "intervenants": "Koffi Essai",
                      "date_debut": "2026-09-29", "date_fin": "2026-09-29", "heure_debut": "09:00", "heure_fin": "12:30",
                      "objet": "Assistance mensuelle de septembre 2026.", "resultat": ["Vérification de l'exécution des tâches planifiées"],
                      "resultat_biblio": ["0"], "statut_global": "OK", "pb_probleme": ["Port (135, 445, 139) fermé"],
                      "pb_impact": ["Installation à distance impossible"], "pb_action": ["Ouvrir les ports sur le pare-feu"],
                      "pb_responsable": ["HUDSON"], "pb_echeance": [""], "pb_plan": ["0"]}
        op.post(f"/interventions/{iid}", data=formulaire)
        op.post(f"/interventions/{iid}/valider", data={"csrf": jeton(r.text)})
        page = op.get("/assistances?annee=2026&mois=9").text
        verifier("Réalisée" in page and "RI-2026-HUD" in page, "rapport validé → assistance « Réalisée »")
        r = val.post(f"/assistances/{a_a.id}/reporter", data={"csrf": jeton(val.get('/assistances?annee=2026&mois=9').text),
                                                             "justification": "Client en congés annuels"}, follow_redirects=True)
        verifier("reportée" in r.text and "Client en congés annuels" in r.text, "report justifié par un validateur")
        verifier("100 %" in r.text, "conformité 100 % (le report justifié n'est pas compté comme manqué)")
        verifier(op.post(f"/assistances/{a_a.id}/reporter", data={"csrf": jeton(page), "justification": "x"}).status_code == 403,
                 "opérateur : report réservé aux validateurs")
        verifier("3,5" in r.text and 'class="liste triable"' in r.text, "classement clients (heures 3,5) triable")

        # --- Techniciens : formation, certification, justificatif
        page = op.get(f"/techniciens/{op_id}").text
        op.post(f"/techniciens/{op_id}/formations", data={"csrf": jeton(page), "intitule": "KL 002 — Kaspersky Security Center",
                                                         "organisme": "Kaspersky Academy", "statut": "Terminée", "debut": "2026-09-01",
                                                         "fin": "2026-09-03", "heures": "24"})
        r = op.post(f"/techniciens/{op_id}/certifications", data={"csrf": jeton(page), "intitule": "Kaspersky Endpoint Security Professional",
                                                                 "editeur": "Kaspersky", "numero": "KES-ESSAI-1", "obtenue_le": "2026-09-10",
                                                                 "expire_le": (date.today() + timedelta(days=30)).isoformat()},
                    files={"justificatif": ("certificat.png", PNG, "image/png")}, follow_redirects=True)
        verifier("Kaspersky Endpoint Security Professional" in r.text and "Expire dans 30 j" in r.text and "KL 002" in r.text,
                 "fiche : formation et certification enregistrées")
        r = op.post(f"/techniciens/{op_id}/certifications", data={"csrf": jeton(page), "intitule": "Faux", "editeur": "X",
                                                                 "obtenue_le": "2026-09-10"},
                    files={"justificatif": ("certificat.png", b"%PDF-1.4 pas une image", "image/png")}, follow_redirects=True)
        verifier("ne correspond pas à son extension" in r.text, "justificatif refusé : contenu différent de l'extension")
        with Session() as db:
            cid = db.scalar(select(Certification.id).where(Certification.numero == "KES-ESSAI-1"))
        verifier(op.get(f"/certifications/{cid}/fichier").content.startswith(PNG[:8]), "justificatif téléchargeable par son titulaire")
        verifier(op2.get(f"/certifications/{cid}/fichier").status_code == 403, "justificatif refusé à un autre opérateur")
        verifier(val.get(f"/certifications/{cid}/fichier").status_code == 200, "justificatif accessible au validateur")
        verifier(op2.post(f"/techniciens/{op_id}/formations", data={"csrf": jeton(op2.get('/techniciens').text), "intitule": "x"}).status_code == 403,
                 "un opérateur ne modifie pas la fiche d'un autre")
        with Session() as db:
            titres = [a.titre for a in alertes.evaluer(db, reference=(2026, 9))]
            db.commit()
        verifier(any("Koffi Essai : certification" in t for t in titres), "alerte : certification expirant sous 60 jours")

        # --- Activité interne
        r = op.post("/activites", data={"csrf": jeton(page), "date": "2026-09-15", "type": "webinaire", "titre": "Webinaire Kaspersky Next",
                                        "participants": "Koffi Essai, Autre Essai", "duree": "1,5", "description": ""}, follow_redirects=True)
        verifier("Webinaire Kaspersky Next" in r.text and "1,5" in r.text, "activité interne enregistrée")

        # --- Import d'anciens rapports
        with open(os.path.join(DOSSIER, "R-I UDSON 21-04-2026.pdf"), "rb") as f:
            ri = f.read()
        page = op.get("/interventions/importer").text
        r = op.post("/interventions/importer", data={"csrf": jeton(page)}, files=[("fichiers", ("R-I UDSON 21-04-2026.pdf", ri, "application/pdf"))],
                    follow_redirects=True)
        verifier("1 rapport(s) importé(s)" in r.text and "RI-2026-HUD" in r.text, "import du PDF : client reconnu (HUDSON)")
        with Session() as db:
            imp = db.scalar(select(Intervention).where(Intervention.nom_fichier_source == "R-I UDSON 21-04-2026.pdf"))
            verifier(imp.type == "deploiement" and imp.date_debut == date(2026, 4, 21) and len(imp.resultat) == 8
                     and imp.points_bloquants[0]["probleme"].startswith("Port (135"), "champs extraits : type, dates, 8 actions, point bloquant")
            imp_id = imp.id
        r = op.post("/interventions/importer", data={"csrf": jeton(page)}, files=[("fichiers", ("copie.pdf", ri, "application/pdf"))],
                    follow_redirects=True)
        verifier("déjà importé" in r.text, "doublon refusé (même fichier)")
        page = op.get(f"/interventions/{imp_id}").text
        verifier("Rapport importé à vérifier" in page, "page de vérification de l'import")
        op.post(f"/interventions/{imp_id}/confirmer-import", data={"csrf": jeton(page)})
        pdf = op.get(f"/interventions/{imp_id}/pdf")
        verifier(pdf.content == ri, "import confirmé : le PDF d'origine fait foi")
        # Même rapport, fichier différent (réexport) : doublon probable → annuler, puis importer quand même
        copie = ri + b"\n% reexport\n"
        r = op.post("/interventions/importer", data={"csrf": jeton(page)}, files=[("fichiers", ("R-I HUDSON (copie).pdf", copie, "application/pdf"))],
                    follow_redirects=True)
        verifier("ressemblent à une intervention déjà enregistrée" in r.text and "Doublons probables" in r.text,
                 "réexport du même rapport : signalé comme doublon probable, rien n'est créé")
        with Session() as db:
            d = db.scalar(select(ImportEnAttente).where(ImportEnAttente.motif == "doublon"))
            verifier(d.doublon_id == imp_id and d.similarite >= 0.85, f"doublon rattaché au bon rapport (similarité {d.similarite:.0%})")
            did = d.id
        r = op.post(f"/interventions/attente/{did}/supprimer", data={"csrf": jeton(r.text)}, follow_redirects=True)
        with Session() as db:
            verifier("annulé" in r.text and db.get(ImportEnAttente, did) is None, "« Annuler l'import » : document retiré")
        r = op.post("/interventions/importer", data={"csrf": jeton(r.text)}, files=[("fichiers", ("R-I HUDSON (copie).pdf", copie, "application/pdf"))],
                    follow_redirects=True)
        with Session() as db:
            did = db.scalar(select(ImportEnAttente.id).where(ImportEnAttente.motif == "doublon"))
        r = op.post(f"/interventions/attente/{did}/accepter", data={"csrf": jeton(r.text)}, follow_redirects=True)
        with Session() as db:
            verifier("importé quand même" in r.text and db.scalar(select(func.count()).select_from(Intervention)
                                                                   .where(Intervention.nom_fichier_source == "R-I HUDSON (copie).pdf")) == 1,
                     "« Importer quand même » : intervention créée malgré la ressemblance")
        with open(os.path.join(DOSSIER, "Rapport_Intervention_Migration_KSC_Web_BSIC.docx"), "rb") as f:
            docx = f.read()
        with open(os.path.join(DOSSIER, "RI-Migration_KSC_Web-BSIC.pdf"), "rb") as f:
            bsic_pdf = f.read()
        # Lot de deux rapports d'un client non enregistré, avec un client choisi : il est ignoré, rien n'est mal rattaché
        r = op.post("/interventions/importer", data={"csrf": jeton(page), "client_impose": str(pac.id)},
                    files=[("fichiers", ("bsic.docx", docx, "application/octet-stream")),
                           ("fichiers", ("bsic.pdf", bsic_pdf, "application/pdf"))], follow_redirects=True)
        verifier("le client choisi a été ignoré" in r.text and "2 rapport(s) d&#39;un client non enregistré" in r.text.replace("'", "&#39;"),
                 "lot : client choisi ignoré, les 2 rapports d'un client inconnu mis en attente")
        verifier("En attente de client" in r.text and "<strong>BSIC</strong>" in r.text, "attente : nom écrit dans le document détecté (BSIC)")
        with Session() as db:
            attentes = {a.nom_fichier: a.id for a in db.scalars(select(ImportEnAttente))}
            verifier(not db.scalar(select(Intervention.id).where(Intervention.nom_fichier_source.in_(("bsic.docx", "bsic.pdf")))),
                     "aucune intervention créée pour un client inconnu")
        r = op.post("/interventions/importer", data={"csrf": jeton(r.text)}, files=[("fichiers", ("encore.pdf", bsic_pdf, "application/pdf"))],
                    follow_redirects=True)
        verifier("déjà en attente" in r.text, "doublon d'un document en attente refusé")
        r = op.post(f"/interventions/attente/{attentes['bsic.pdf']}/rattacher", data={"csrf": jeton(r.text), "client_id": str(pac.id)},
                    follow_redirects=True)
        verifier("rattaché à PAC CI" in r.text and "RI-2026-PAC" in r.text, "rattachement manuel à un client existant")
        # Création du client par un administrateur, avec « BSIC » en autre nom : le Word en attente est rattaché tout seul
        page_adm = adm.get("/admin/clients/nouveau?nom=BSIC").text
        verifier('value="BSIC"' in page_adm and "Nom repris d&#39;un rapport importé" in page_adm.replace("'", "&#39;"),
                 "création du client pré-remplie depuis l'import")
        r = adm.post("/admin/clients", data={"csrf": jeton(page_adm), "nom": "Banque Essai Import", "autres_noms": "BSIC, Banque Sahélo",
                                             "avec_ksc": "true", "tenants_mdr": "", "notes": "", "code": "", "emails_rapports": ""},
                     follow_redirects=True)
        verifier("1 rapport(s) importé(s) en attente lui ont été rattachés" in r.text, "client créé : rapport en attente rattaché automatiquement")
        with Session() as db:
            banque = db.scalar(select(Client).where(Client.nom == "Banque Essai Import"))
            banque_id = banque.id
            verifier(banque.autres_noms == ["BSIC", "Banque Sahélo"] and not db.scalar(select(ImportEnAttente.id)),
                     "autres noms enregistrés, plus rien en attente")
            w = db.scalar(select(Intervention).where(Intervention.nom_fichier_source == "bsic.docx"))
            verifier(w.client_id == banque_id, "le Word est rattaché au nouveau client (reconnu par son autre nom)")
        with Session() as db:
            w = db.scalar(select(Intervention).where(Intervention.nom_fichier_source == "bsic.docx"))
            verifier(w.type == "migration" and "reconstruire" in w.objet, "Word : type migration et objet extraits")
            wid, wfichier = w.id, w.fichier_source
        op.post(f"/interventions/{wid}/supprimer", data={"csrf": jeton(page)})
        with Session() as db:
            verifier(db.get(Intervention, wid) is None and not os.path.exists(os.path.join(os.environ.get("STOCKAGE_DIR", "donnees"), wfichier))
                     , "suppression d'un brouillon importé (fichier d'origine supprimé)")

        # --- Base de connaissances et problèmes récurrents
        with Session() as db:
            from app import interventions as mi
            u = db.get(Utilisateur, op_id)
            x = mi.creer(db, db.get(Client, anare.id), "deploiement", u, date(2026, 8, 12))
            x.objet, x.resultat = "Déploiement KES chez ANARE.", ["Déploiement de KES"]
            x.points_bloquants = [{"probleme": "Ports 135 445 139 fermés", "impact": "", "action": "Ouverture des ports par le client",
                                   "responsable": "ANARE", "echeance": None, "plan_action": False}]
            x.statut = "valide"
            db.commit()
        page = op.get("/connaissances?q=port+135").text
        verifier("RI-2026-HUD" in page and "importé" in page, "recherche : rapports saisis et importés trouvés")
        verifier("Problèmes récurrents" in page and "ANARE, HUDSON" in page, "problème récurrent détecté chez 2 clients (formulations différentes)")

        # --- Rapport d'activité du service (T3 2026)
        page = val.get("/service?periodicite=trimestriel&annee=2026&numero=3").text
        r = val.post("/service", data={"csrf": jeton(page), "periodicite": "trimestriel", "annee": 2026, "numero": 3}, follow_redirects=True)
        verifier("3e trimestre 2026" in r.text, "rapport du service T3 2026 créé")
        with Session() as db:
            rs_ = db.scalar(select(RapportService).where(RapportService.annee == 2026, RapportService.numero == 3,
                                                         RapportService.periodicite == "trimestriel").order_by(RapportService.version.desc()))
            ch, rid = rs_.donnees["chiffres"], rs_.id
            verifier(ch["interventions"] >= 2 and ch["assistances_realisees"] == 1 and ch["assistances_reportees"] == 1
                     and ch["certifications_obtenues"] >= 1 and ch["activites_internes"] >= 1, "chiffres consolidés (interventions, assistances, certifications, activités)")
            verifier(any(p["probleme"] for p in rs_.donnees["recurrents"]), "problèmes récurrents dans le rapport")
        pdf = val.get(f"/service/{rid}/apercu.pdf")
        texte = " ".join("".join(p.get_text() for p in fitz.open(stream=pdf.content, filetype="pdf")).split())
        verifier("RAPPORT D'ACTIVITÉ" in texte and "Assistances mensuelles" in texte and "Kaspersky Endpoint Security Professional" in texte
                 and "Webinaire Kaspersky Next" in texte, "PDF : sections assistances, certifications, activités internes")
        val.post(f"/service/{rid}/contenu", data={"csrf": jeton(r.text), "synthese": "Synthèse **validée**.", "faits_marquants": "Fait A\nFait B",
                                                  "perspectives": "Perspective 1", "conclusion": "Conclusion."})
        val.post(f"/service/{rid}/valider", data={"csrf": jeton(r.text)})
        verifier(val.get(f"/service/{rid}/pdf").content.startswith(b"%PDF"), "rapport du service validé, PDF archivé")
        verifier(op.post("/service", data={"csrf": jeton(op.get("/service").text), "periodicite": "annuel", "annee": 2026, "numero": 1}).status_code == 403,
                 "création du rapport du service réservée aux validateurs")
    finally:
        with Session() as db:
            for i in db.scalars(select(Intervention).where(Intervention.cree_par_id.in_(ids))):
                for chemin in {i.pdf, i.fichier_source} - {None}:
                    supprimer(chemin)
            db.execute(delete(AssistancePlanifiee).where(AssistancePlanifiee.id > maxima[AssistancePlanifiee]))
            db.execute(delete(Intervention).where(Intervention.cree_par_id.in_(ids)))
            for r in db.scalars(select(RapportService).where(RapportService.cree_par_id.in_(ids))):
                if r.pdf:
                    supprimer(r.pdf)
                db.delete(r)
            for c in db.scalars(select(Certification).where(Certification.utilisateur_id.in_(ids))):
                if c.fichier:
                    supprimer(c.fichier)
            db.execute(delete(ActiviteInterne).where(ActiviteInterne.id > maxima[ActiviteInterne]))
            db.execute(delete(Alerte).where(Alerte.id > maxima[Alerte]))
            for cid_, (actif, depuis) in etat_initial.items():
                c = db.get(Client, cid_)
                c.assistance_mensuelle, c.assistance_depuis = actif, depuis
            for a in db.scalars(select(ImportEnAttente).where(ImportEnAttente.cree_par_id.in_(ids))):
                supprimer(a.fichier)
                db.delete(a)
            db.execute(delete(Client).where(Client.nom == "Banque Essai Import"))
            db.execute(delete(Utilisateur).where(Utilisateur.id.in_(ids)))
            db.commit()
        print("Données d'essai supprimées.")


if __name__ == "__main__":
    main()

"""Test du pilotage : vue d'ensemble, suivi du parc, contrats et licences, alertes et notifications, résumé hebdomadaire.
Fabrique des données (rapports validés, export d'août, hebdo avec incident, contrat) pour HUDSON, puis les supprime.
Les notifications passent par un faux serveur SMTP et un faux webhook Teams (aucun envoi réel).

    python -m outils_dev.essai_pilotage        (depuis le dossier « plateforme », après essai_depots)
"""
import copy
import json
import re
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app import alertes, config, services
from app.db import Session
from app.main import app
from app.modeles import VALIDE, Alerte, Client, Contrat, Envoi, ExportKsc, Hebdo, Rapport, Utilisateur
from app.moteur import parc as mparc
from app.securite import hacher

PREFIXE, MDP = "essai.pilotage", "MotDePasse2026!"
FICTIFS = {7: ("Élevé", 30, 210, 95), 8: ("Critique", 41, 380, 80)}
ENVOYES, TEAMS = [], []


def verifier(condition, libelle):
    print(("  OK   " if condition else "  ÉCHEC ") + libelle)
    assert condition, libelle


def jeton(texte):
    return re.search(r'name="csrf" value="([^"]+)"', texte).group(1)


class FauxSMTP:
    def __init__(self, hote, port, timeout=None):
        self.hote = hote
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def starttls(self):
        pass
    def login(self, *a):
        pass
    def send_message(self, message):
        ENVOYES.append(message)


class FausseReponse:
    status = 202
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def faux_urlopen(requete, timeout=None):
    TEAMS.append(json.loads(requete.data))
    return FausseReponse()


def connecter(role):
    http = TestClient(app)
    r = http.get("/connexion")
    r = http.post("/connexion", data={"email": f"{PREFIXE}.{role}@esay.local", "mot_de_passe": MDP, "csrf": jeton(r.text)},
                  follow_redirects=False)
    return http, r.headers["location"]


def main():
    verifier(mparc.fin_de_support("Microsoft Windows 10 Pro") == date(2025, 10, 14), "fin de support : Windows 10")
    verifier(mparc.fin_de_support("Windows 8.1") == date(2023, 1, 10), "fin de support : 8.1 distinct de 8")
    verifier(mparc.statut_support(date(2027, 1, 12), date(2026, 9, 29))[0] == "urgent", "Server 2016 : fin sous 6 mois")

    with Session() as db:
        for role in ("admin", "operateur"):
            db.add(Utilisateur(email=f"{PREFIXE}.{role}@esay.local", nom=f"Essai {role}", role=role,
                               mot_de_passe=hacher(MDP), doit_changer_mdp=False))
        db.commit()
        ids = db.scalars(select(Utilisateur.id).where(Utilisateur.email.like(f"{PREFIXE}%"))).all()
        uid = min(ids)
        hudson = db.scalar(select(Client).where(Client.nom == "HUDSON"))
        alerte_max = db.scalar(select(func.max(Alerte.id))) or 0
    crees = {"rapports": [], "export": None, "hebdo": None, "contrat": None}
    config.SMTP.update(hote="smtp.essai.local", expediteur="rapports@esay.local", securite="starttls")
    config.ALERTES_EMAILS[:] = ["soc@esay.local"]
    config.RESUME_EMAILS[:] = ["direction@esay.local"]
    config.TEAMS_WEBHOOK = "https://teams.essai.local/webhook"
    alertes.smtplib.SMTP = FauxSMTP
    alertes.urllib.request.urlopen = faux_urlopen
    try:
        admin, accueil = connecter("admin")
        verifier(accueil == "/", "connexion administrateur : arrivée sur la vue d'ensemble")
        op, accueil_op = connecter("operateur")
        verifier(accueil_op == "/production", "connexion opérateur : arrivée sur la production")
        page = admin.get("/").text
        verifier("Vue d&#39;ensemble" in page or "Vue d'ensemble" in page, "vue d'ensemble accessible")

        # --- Données : septembre (brouillon validé) + juillet / août validés, export et hebdo fictifs
        with Session() as db:
            u = db.get(Utilisateur, uid)
            sept = services.creer_brouillon(db, hudson, 2026, 9, u)
            db.commit()
            for m, (niveau, crit, det, vc) in FICTIFS.items():
                dn = copy.deepcopy(sept.donnees)
                dn.update(mois=m)
                ct = copy.deepcopy(sept.contenu)
                ct["niveau_risque"] = niveau
                if m == 7:  # action recommandée en juillet, toujours en cours en septembre
                    ct["actions"] = ct["actions"] + [{"action": "Action de juillet", "pourquoi": "", "priorite": "Haute",
                                                      "responsable": "ESAY + HUDSON", "statut": "À faire"}]
                r = Rapport(client_id=hudson.id, periodicite="mensuel", annee=2026, mois=m, debut=date(2026, m, 1),
                            fin=date(2026, m + 1, 1), version=1, statut=VALIDE, profil=sept.profil, donnees=dn, contenu=ct,
                            indicateurs={**sept.indicateurs, "appareils_critiques": crit, "detections": det,
                                         "vulnerabilites_critiques": vc},
                            cree_par_id=uid, valide_par_id=uid, valide_le=datetime(2026, m + 1, 4))
                db.add(r)
            sept.contenu = {**sept.contenu, "suivi": [{"action": "Action de juillet", "priorite": "Haute",
                                                       "responsable": "ESAY + HUDSON", "statut": "En cours", "commentaire": ""}]}
            services.valider(db, sept, u)
            db.commit()
            crees["rapports"] = db.scalars(select(Rapport.id).where(Rapport.cree_par_id == uid)).all()
            sept_export = db.scalar(select(ExportKsc).where(ExportKsc.client_id == hudson.id, ExportKsc.type == "protection",
                                                             ExportKsc.annee == 2026, ExportKsc.mois == 9))
            aout = copy.deepcopy(sept_export.donnees)
            retire = aout["appareils"].pop(0)["appareil"]  # un appareil absent en août : série d'un seul mois
            e = ExportKsc(client_id=hudson.id, annee=2026, mois=8, type="protection", fichier="essai-aout.pdf",
                          chemin="essai/aout.pdf", empreinte="essai-pilotage", donnees=aout, statut="ok",
                          genere_le=datetime(2026, 8, 25), depose_par_id=uid)
            h = Hebdo(fichier="essai-incident.pdf", chemin="essai/incident.pdf", empreinte="essai-pilotage-incident",
                      debut=date(2026, 7, 6), fin=date(2026, 7, 13), statut="ok", depose_par_id=uid,
                      donnees={"fichier": "essai-incident.pdf", "debut": "2026-07-06", "fin": "2026-07-13", "postes": {},
                               "incidents": [{"tenant": "HUDSON", "numero": "ESSAI-4242", "nom": "Exécution suspecte",
                                              "priorite": "High", "statut": "Open", "cree": "07.07.2026 10:00"}]})
            k = Contrat(client_id=hudson.id, produit="KSC", reference="ESSAI-KSC", licences=40,
                        debut=date(2025, 10, 1), echeance=date.today() + timedelta(days=20))
            db.add_all([e, h, k])
            db.commit()
            crees.update(export=e.id, hebdo=h.id, contrat=k.id)

        # --- Alertes
        with Session() as db:
            nouvelles = alertes.evaluer_et_notifier(db, reference=(2026, 9), en_arriere_plan=False)
            types = {a.type for a in nouvelles if a.client_id == hudson.id}
            titres = [a.titre for a in nouvelles]
        verifier("risque_critique" in types and any("passe au niveau de risque critique (Août 2026)" in t for t in titres),
                 "alerte : passage au niveau critique en août")
        verifier(any("détections de menaces +81 %" in t for t in titres), "alerte : hausse des détections de +81 % (210 → 380)")
        verifier(any("serveur(s) en état critique deux mois de suite" in t for t in titres), "alerte : serveurs critiques 2 mois")
        verifier(any("incident MDR n° ESSAI-4242" in t for t in titres), "alerte : incident MDR de l'hebdo")
        verifier(any("49 appareils pour 40 licences KSC" in t for t in titres), "alerte : licences dépassées (49 / 40)")
        verifier(any("à renouveler avant le" in t for t in titres), "alerte : contrat à échéance sous 30 jours")
        verifier(len(ENVOYES) == 1 and "soc@esay.local" in ENVOYES[0]["To"] and "ESSAI-4242" in ENVOYES[0].get_body(("html",)).get_content(),
                 "notification : un seul e-mail groupé aux destinataires des alertes")
        verifier(len(TEAMS) == 1 and TEAMS[0]["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive",
                 "notification : carte adaptative Teams")
        with Session() as db:
            verifier(not alertes.evaluer(db, reference=(2026, 9)), "réévaluation : aucune alerte en double")
            verifier(all(a.notifiee_le for a in db.scalars(select(Alerte).where(Alerte.id > alerte_max))), "alertes marquées notifiées")

        # --- Pages
        page = admin.get("/?annee=2026&mois=9").text
        verifier(page.count('class="case critique"') >= 2 and 'class="case eleve"' in page, "vue d'ensemble : carte de chaleur")
        verifier("Clients les plus exposés" in page and "Mozilla Firefox" in page, "vue d'ensemble : classement et applications")
        verifier("Windows 10" in page and "Support terminé" in page, "vue d'ensemble : systèmes en fin de support")
        verifier(page.count('class="courbe"') >= 4, "vue d'ensemble : tendances du portefeuille")
        verifier("ESSAI-KSC" not in page and "HUDSON — KSC · 40 licences" in page, "vue d'ensemble : contrat à surveiller")
        verifier('class="badge"' in page, "badge du nombre d'alertes dans le menu")
        verifier(f'href="/clients/{hudson.id}/2026/9" title="Fiche du client"' in page, "classement : lien vers la fiche client")
        verifier('<strong class="hors-mdr">22</strong>' in page, "couverture : 22 postes hors MDR (49 administrés, 27 supervisés)")
        verifier("Action de juillet" in page and "2 mois</span>" in page and "juillet 2026" in page,
                 "actions : ouverte depuis 2 mois, avec son mois d'origine")
        verifier(all(t in page for t in ("Partagée</strong> 9", "ESAY</strong> 6", "Client</strong> 3")), "actions : répartition partagée 9 / ESAY 6 / client 3")
        menaces = page.split("Évolution des menaces par catégorie")[1].split("Actions ouvertes depuis")[0]
        verifier("Adware" in menaces and menaces.count('class="courbe"') >= 2, "évolution des menaces : une courbe par catégorie")
        verifier("engagement : validé sous 10 jours" in page and re.search(r">J[+-]\d+<", page), "délai de production par rapport (J-2 : validé avant la fin du mois)")
        filtre = admin.get(f"/?annee=2026&mois=9&client={hudson.id}").text
        verifier("vue filtrée" in filtre and "1 client(s) sur 1" in filtre, "filtre par client")
        filtre = admin.get("/?annee=2026&mois=9&profil=ksc").text
        with Session() as db:  # dépend du portefeuille réel : compter les clients « KSC seul » actifs
            nb_ksc = db.scalar(select(func.count()).select_from(Client).where(
                Client.actif.is_(True), Client.avec_ksc.is_(True), Client.avec_mdr.is_(False)))
        verifier(("Aucun client ne correspond à ces filtres" in filtre) if nb_ksc == 0 else f"client(s) sur {nb_ksc}\n" in filtre,
                 f"filtre par profil « KSC seul » ({nb_ksc} client(s))")
        filtre = admin.get("/?annee=2026&mois=9&profil=mdr-ksc").text
        verifier("Clients les plus exposés" in filtre, "filtre par profil « MDR + KSC »")
        page = admin.get(f"/clients/{hudson.id}/parc?annee=2026&mois=9").text
        verifier("Appareils en anomalie récurrente" in page and page.count("2 mois</span>") >= 40, "parc : appareils en anomalie 2 mois de suite")
        verifier(retire not in page.split("Appareils en anomalie récurrente")[1].split("Planning")[0], "parc : appareil absent en août non récurrent")
        verifier("Windows Server 2016" in page and "Fin sous 6 mois" in page, "parc : planning des fins de support")
        page = admin.get("/contrats").text
        verifier("Dépassement : 9 de plus que les licences" in page and "122 %" in page, "contrats : usage et taux (49/40 = 122 %)")
        page = admin.get(f"/admin/clients/{hudson.id}").text
        verifier('id="contrats"' in page and "ESSAI-KSC" in page, "fiche client admin : contrats modifiables")
        r = admin.post(f"/admin/contrats/{crees['contrat']}", data={"csrf": jeton(page), "produit": "KSC", "licences": 60,
                                                                  "reference": "ESSAI-KSC", "echeance": (date.today() + timedelta(days=20)).isoformat(),
                                                                  "actif": "true"}, follow_redirects=True)
        verifier("Contrat KSC de HUDSON enregistré" in r.text, "modification d'un contrat (60 licences)")
        page = admin.get("/contrats").text
        verifier("82 %" in page and "Conforme" in page, "contrats : 49/60 = 82 %, conforme")

        page = admin.get("/alertes").text
        verifier("ESSAI-4242" in page and "E-mail" in page, "page des alertes")
        a_ids = [str(i) for i in re.findall(r'name="ids" value="(\d+)"', page)]
        r = op.post("/alertes/traiter", data={"csrf": jeton(op.get("/alertes").text), "ids": a_ids}, follow_redirects=True)
        verifier(f"{len(a_ids)} alerte(s) marquée(s) comme traitée(s)" in r.text, "traitement groupé des alertes")
        verifier('class="badge"' not in admin.get("/production").text, "badge disparu une fois les alertes traitées")

        # --- Résumé hebdomadaire
        verifier("Résumé hebdomadaire" in admin.get("/alertes/resume").text, "aperçu du résumé hebdomadaire")
        with Session() as db:
            envoye, message = alertes.envoyer_resume(db)
            verifier(envoye and "direction@esay.local" in ENVOYES[-1]["To"], "résumé envoyé à la direction")
            deja, message = alertes.envoyer_resume(db)
            verifier(not deja and "déjà envoyé" in message, "résumé : une seule fois par semaine")
    finally:
        with Session() as db:
            db.execute(delete(Alerte).where(Alerte.id > alerte_max))
            db.execute(update(Alerte).where(Alerte.traitee_par_id.in_(ids)).values(traitee_par_id=None))
            db.execute(delete(Envoi).where(Envoi.periode == alertes.periode_semaine()))
            for cle, modele in (("contrat", Contrat), ("export", ExportKsc), ("hebdo", Hebdo)):
                if crees[cle]:
                    db.execute(delete(modele).where(modele.id == crees[cle]))
            for r in db.scalars(select(Rapport).where(Rapport.cree_par_id.in_(ids))):
                if r.pdf:
                    from app.stockage import supprimer
                    supprimer(r.pdf)
                db.delete(r)
            db.execute(delete(Utilisateur).where(Utilisateur.id.in_(ids)))
            db.commit()
        print("Données d'essai supprimées.")


if __name__ == "__main__":
    main()

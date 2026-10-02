"""Commandes d'administration de la plateforme.

    python gerer.py init                                   crée ou met à jour les tables (migrations)
    python gerer.py creer-admin <email> "<Nom>"            crée un administrateur (mot de passe provisoire affiché)
    python gerer.py importer-clients <config.json>         importe les clients du générateur en ligne de commande
    python gerer.py alertes                                évalue les alertes et envoie les notifications (tâche quotidienne)
    python gerer.py resume-hebdo [--forcer]                envoie le résumé hebdomadaire (une fois par semaine)
    python gerer.py verifier-journal [--ancre EMPREINTE]  vérifie la chaîne ; avec une ancre conservée ailleurs, vérifie
                                                           aussi qu'aucune ligne n'a été supprimée depuis (troncature)
    python gerer.py ancre-journal                          émet l'empreinte de tête vers syslog / SIEM (tâche quotidienne)
    python gerer.py planificateur                          exécute les tâches planifiées en continu (déploiement Docker)
"""
import json
import sys

from sqlalchemy import select

from app.db import Session, migrer
from app.modeles import Client, Utilisateur, journaliser
from app.securite import hacher
from app.web.admin import mot_de_passe_provisoire


def init():
    migrer()
    print("Base à jour (migrations appliquées).")


def creer_admin(email, nom):
    migrer()
    email = email.strip().lower()
    with Session() as db:
        if db.scalar(select(Utilisateur).where(Utilisateur.email == email)):
            sys.exit(f"Un compte existe déjà pour {email}.")
        mdp = mot_de_passe_provisoire()
        db.add(Utilisateur(email=email, nom=nom, role="admin", mot_de_passe=hacher(mdp), doit_changer_mdp=True))
        journaliser(db, None, "création administrateur (ligne de commande)", email)
        db.commit()
    print(f"Administrateur créé : {email}\nMot de passe provisoire : {mdp}\n"
          "Il devra être changé à la première connexion.")


def importer_clients(chemin):
    migrer()
    with open(chemin, encoding="utf-8") as f:
        config = json.load(f)
    with Session() as db:
        for c in config["clients"]:
            if db.scalar(select(Client).where(Client.nom == c["nom"])):
                print(f"  = {c['nom']} (déjà présent)")
                continue
            db.add(Client(nom=c["nom"], avec_mdr=True, avec_ksc=True, tenants_mdr=c.get("tenants_mdr", []),
                          notes=c.get("note", "")))
            print(f"  + {c['nom']}")
        journaliser(db, None, "import des clients (ligne de commande)", chemin)
        db.commit()


def evaluer_alertes():
    from app import alertes
    migrer()
    with Session() as db:
        nouvelles = alertes.evaluer_et_notifier(db, en_arriere_plan=False)
    print(f"{len(nouvelles)} nouvelle(s) alerte(s).")
    for a in nouvelles:
        print(f"  [{a.niveau}] {a.titre}")


def resume_hebdo(*options):
    from app import alertes
    migrer()
    with Session() as db:
        envoye, message = alertes.envoyer_resume(db, forcer="--forcer" in options)
    print(message)
    if not envoye and "déjà envoyé" not in message:
        sys.exit(1)


def verifier_journal(*options):
    from app import integrite
    ancre = options[options.index("--ancre") + 1] if "--ancre" in options and len(options) > options.index("--ancre") + 1 else None
    with Session() as db:
        r = integrite.verifier(db)
        present = integrite.contient(db, ancre) if ancre else None
    if not r["ok"]:
        print(f"INTÉGRITÉ ROMPUE à la ligne {r['rupture']['id']} : {r['rupture']['raison']}")
        sys.exit(2)
    print(f"Journal intact : {r['lignes']} lignes. Ancre (empreinte de la dernière ligne) : {r['ancre']}")
    if ancre is not None:
        if not present:
            print(f"ANCRE INTROUVABLE : aucune ligne n'a l'empreinte {ancre} — des lignes ont été supprimées "
                  "(fin du journal tronquée) ou l'ancre ne provient pas de cette base.")
            sys.exit(3)
        print("Ancre retrouvée dans la chaîne : aucune troncature depuis cette ancre.")


def ancre_journal():
    """Empreinte de tête du journal envoyée à l'extérieur (syslog / SIEM) : preuve datée de l'état de la chaîne."""
    import logging
    from app import integrite, supervision
    supervision.configurer_journalisation()
    with Session() as db:
        r = integrite.verifier(db)
    logging.getLogger("rapports.journal").info(f"ancre lignes={r['lignes']} integre={int(r['ok'])} empreinte={r['ancre']}")
    print(f"Ancre émise : {r['ancre']} ({r['lignes']} lignes, intégrité {'OK' if r['ok'] else 'ROMPUE'})")
    if not r["ok"]:
        sys.exit(2)


def planificateur():
    """Boucle des tâches planifiées (conteneur « taches ») : alertes et ancre du journal chaque jour à 7 h, résumé
    hebdomadaire le lundi à 8 h. Remplace les timers systemd du déploiement sans conteneurs."""
    import time
    from datetime import datetime
    faites = set()
    print("Planificateur démarré : alertes et ancre du journal à 7 h, résumé hebdomadaire le lundi à 8 h.", flush=True)
    while True:
        maintenant = datetime.now()
        jour = maintenant.date().isoformat()
        taches = []
        if maintenant.hour >= 7 and ("quotidien", jour) not in faites:
            taches.append((("quotidien", jour), [evaluer_alertes, ancre_journal]))
        if maintenant.weekday() == 0 and maintenant.hour >= 8 and ("hebdo", jour) not in faites:
            taches.append((("hebdo", jour), [resume_hebdo]))
        for cle, fonctions in taches:
            for f in fonctions:
                try:
                    f()
                except SystemExit:
                    pass
                except Exception as e:  # noqa: BLE001  (une tâche en échec ne doit pas arrêter les suivantes)
                    print(f"Tâche {f.__name__} en échec : {e}", flush=True)
            faites.add(cle)
        time.sleep(60)


if __name__ == "__main__":
    commandes = {"init": init, "creer-admin": creer_admin, "importer-clients": importer_clients,
                 "alertes": evaluer_alertes, "resume-hebdo": resume_hebdo, "verifier-journal": verifier_journal,
                 "ancre-journal": ancre_journal, "planificateur": planificateur}
    if len(sys.argv) < 2 or sys.argv[1] not in commandes:
        sys.exit(__doc__)
    commandes[sys.argv[1]](*sys.argv[2:])

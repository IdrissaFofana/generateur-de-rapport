# Plateforme « Rapports de sécurité » — ESAY

Application web interne qui produit, pour chaque client, le rapport mensuel de sécurité
(PDF aux couleurs d'ESAY) à partir :

- des **rapports hebdomadaires Kaspersky MDR** (tous clients, répartis par tenant) ;
- des **exports Kaspersky Security Center** transmis par chaque client (protection, menaces, vulnérabilités).

## Utilisation au quotidien

| Qui | Quoi |
|---|---|
| Opérateur | Dépose les hebdos MDR (menu **Hebdos MDR**) et les exports KSC (fiche du client) ; crée le brouillon |
| Validateur | Relit : niveau de risque, textes, plan d'action, suivi des actions ; enregistre ; **valide** |
| Lecteur | Consulte et télécharge les rapports validés |
| Administrateur | Tout, plus les comptes, les clients (profil MDR / KSC, tenants) et le journal |

Cycle d'un rapport : **Incomplet → Partiel / Prêt → Brouillon → Validé**.

- Un brouillon peut être créé même s'il manque des données : les sections concernées sont marquées « en attente ».
- **Actualiser les chiffres** recalcule tout à partir des fichiers déposés, sans toucher aux textes relus.
- Un rapport **validé est figé** : son PDF est archivé. Pour le corriger, créer une **nouvelle version**.
- Les actions encore ouvertes du mois précédent sont reprises dans le **suivi** du mois suivant.
- **Word (dépannage)** : export modifiable avec les mêmes textes ; le PDF reste la référence.
- **Fin de mois** : un hebdo MDR couvre une semaine du lundi au lundi et paraît quelques jours après. Les jours dont
  l'hebdo ne peut pas encore être paru sont affichés « à venir » et ne rendent pas le client « Partiel ».
  Passé ce délai (lundi suivant + 3 jours), ils redeviennent manquants.

### Sécurité des comptes

- **Double authentification** (Mon compte) : code à 6 chiffres d'une application d'authentification (TOTP).
  Obligatoire pour certains rôles avec EXIGER_2FA_ROLES. Téléphone perdu : Administration → Utilisateurs →
  « Réinit. 2FA ».
- Après 5 échecs de connexion, le compte est verrouillé 15 minutes (déverrouillage possible par un administrateur).
- Changer de mot de passe ferme les sessions ouvertes ailleurs.
- **Journal infalsifiable** : chaque ligne est chaînée à la précédente (SHA-256). Vérification : page Journal ou
  `python gerer.py verifier-journal`. Ne jamais supprimer de lignes du journal : la chaîne serait rompue.

### Pages de la plateforme

| Menu | Rôle |
|---|---|
| **Vue d'ensemble** (accueil) | Statistiques du portefeuille à partir des rapports **validés**, filtrables par mois, client et profil : indicateurs avec écart au mois précédent, niveau de risque client × mois, tendances, clients les plus exposés, applications vulnérables communes, couverture MDR (postes hors supervision), suivi des actions (taux de réalisation, actions ouvertes depuis 2 mois ou plus, répartition ESAY / client / partagée), menaces par catégorie et leur évolution, délai de validation de chaque rapport (engagement `ENGAGEMENT_DELAI_JOURS`, 10 jours par défaut), fins de support, contrats et alertes |
| **Alertes** | Alertes ouvertes et traitées ; canaux de notification ; résumé hebdomadaire |
| **Contrats** | Licences souscrites comparées à l'usage réel, échéances de renouvellement |
| **Production** | Liste de travail du mois : données reçues, brouillons, validation, actions groupées |
| **Bilans** · **Hebdos MDR** | Bilans trimestriels / semestriels ; dépôt des rapports hebdomadaires |

Après connexion, opérateurs et validateurs arrivent sur **Production**, les autres rôles sur **Vue d'ensemble**.

### Rapports d'intervention (menu **Interventions**)

Saisis au retour d'intervention, puis générés et envoyés au client :

1. **Nouveau rapport** : client, type, date. Le numéro est attribué automatiquement : `RI-2026-HUD-004`
   (code du client, défini dans sa fiche, sinon les 3 premières lettres du nom ; compteur remis à 1 chaque année).
2. **Saisie** : mode, dates et heures de passage, interlocuteur, intervenants, objet, contexte (pré-rempli depuis le
   dernier export KSC), travaux par module, **résultat global**, statut global, points bloquants, **recommandations**.
   Le panneau **Bibliothèque** propose les actions et recommandations du type d'intervention : un clic les ajoute,
   le texte reste modifiable. Un texte saisi à la main peut être ajouté à la bibliothèque (case « bibliothèque »).
3. **Générer le rapport** : PDF à la charte (logos ESAY et Kaspersky Gold Partner), titre selon le type
   (Rapport de déploiement, de migration, de maintenance, d'assistance, d'intervention sur incident, d'audit, de formation).
4. **Envoi** : par e-mail (serveur de messagerie configuré) ou **brouillon Outlook** avec le PDF joint ; la date est notée.

Un point bloquant coché « reprendre dans le plan d'action » devient une action du rapport mensuel du mois de
l'intervention. **Dupliquer** crée la suite d'une intervention (objet, contexte, points bloquants repris).
L'historique complet d'un client est dans sa fiche → **Interventions** (chronologie).
La **bibliothèque** (105 actions et recommandations de départ, terminologie Kaspersky) se gère depuis
Interventions → Bibliothèque d'actions : ajout par tous, modification et suppression par les validateurs.

### Service technique (menu **Service technique**)

- **Assistances** : cocher « Assistance mensuelle » dans la fiche d'un client (Administration → Clients). Chaque mois,
  une assistance « à planifier » est créée ; on lui donne une date et un technicien, puis « Rédiger le rapport ». Elle
  devient « Réalisée » dès qu'un rapport d'intervention validé du mois la couvre (type assistance ou maintenance).
  Un validateur peut la **reporter** avec justification. Classements des clients et des techniciens (mois, trimestre,
  année), triables par colonne. Alerte si l'assistance du mois n'est pas faite à partir du 20.
- **Techniciens** : chaque utilisateur complète sa fiche (formations, certifications avec justificatif PDF ou image).
  Alerte 60 jours avant l'expiration d'une certification.
- **Activités internes** : projets internes, webinaires, réunions, veille.
- **Connaissances** : recherche dans toutes les interventions ; problèmes rencontrés chez plusieurs clients.
- **Rapport du service** : rapport d'activité mensuel, trimestriel, semestriel ou annuel, calculé puis relu et validé.
- **Import** (Interventions → Importer d'anciens rapports) : PDF ou Word ; les champs sont extraits puis vérifiés
  avant confirmation ; le fichier d'origine reste la référence. Le client est reconnu par son nom, ses **autres noms**
  (fiche client) ou ses tenants, sans tenir compte des majuscules, accents et tirets. Un rapport d'un client non
  enregistré est placé **en attente** : le rattacher à un client existant (« retenir ce nom » l'ajoute à ses autres
  noms) ou créer le client — les rapports en attente qui le citent lui sont alors rattachés automatiquement. Le choix
  manuel d'un client ne vaut que pour un fichier seul.
  **Doublons** : un fichier identique déjà importé est refusé. Un document qui **ressemble** fortement à une
  intervention du même client (même rapport en Word et en PDF, réexport, rapport déjà saisi) apparaît dans
  « Doublons probables » avec le rapport concerné et le pourcentage de similarité : **Importer quand même** ou
  **Annuler l'import**.

### Suivi du parc (fiche client → **Suivi du parc**)

À partir des exports « État de la protection » successifs : appareils en anomalie plusieurs mois de suite
(série en cours, serveurs en premier), appareils revenus à la normale, et planning des fins de support Microsoft
(support terminé, fin sous 6 mois, fin sous 18 mois). Windows 11 n'est pas suivi : l'export ne précise pas sa version.

### Contrats et licences

Saisis par un administrateur dans la fiche du client (Administration → Clients). Un contrat **KSC** est comparé au
nombre d'appareils administrés (dernier export) ; un contrat **MDR** au maximum journalier de postes supervisés du mois.
Dépassement, sous-utilisation (seuil `SEUIL_SOUS_UTILISATION_PCT`, 70 % par défaut) et échéances (30 et 90 jours) sont signalés.

### Alertes et notifications

| Alerte | Déclencheur |
|---|---|
| Niveau critique | un rapport mensuel validé passe au niveau « Critique » |
| Hausse des détections | + `SEUIL_HAUSSE_DETECTIONS_PCT` % (50 % par défaut) d'un mois validé au suivant |
| Incident MDR | incident présent dans un rapport hebdomadaire, rattaché au client par son tenant |
| Serveur critique 2 mois | même serveur en état critique dans deux exports mensuels successifs |
| Licences / échéance | dépassement de licences, contrat à renouveler sous 90 jours, contrat expiré |

Les règles sont évaluées après chaque validation, chaque analyse de fichier, chaque modification de contrat, au démarrage
et chaque jour (tâche planifiée). Une même situation n'est signalée qu'une fois. Notifications facultatives par e-mail
(serveur de messagerie interne) et Teams ; sans configuration, les alertes restent visibles dans la plateforme (badge du menu).
Le **résumé hebdomadaire** (direction) reprend les alertes de la semaine, la production, les clients exposés et les contrats.

### Production : actions groupées

- **Créer les brouillons prêts** : un brouillon pour chaque client « Prêt » (option : inclure les « Partiel »).
- **Actualiser les brouillons** : recalcule les chiffres de tous les brouillons du mois (après un nouveau dépôt).
- **Télécharger les PDF validés** : archive ZIP des rapports validés du mois.

### Évolution sur plusieurs mois

La fiche client montre, sur 12 mois, le niveau de risque de chaque mois et une courbe par indicateur
(appareils critiques, menaces, vulnérabilités critiques, postes MDR), à partir des rapports **validés**.
Le rapport mensuel PDF contient la même évolution dans sa synthèse ; elle est figée à la validation.

### Bilans trimestriels et semestriels (menu **Bilans**)

Un bilan consolide les rapports mensuels **validés** de la période : tableau mois par mois, courbes, incidents MDR,
menaces cumulées, vulnérabilités, bilan des actions (dernier avancement connu), perspectives.
Il suit le même cycle qu'un rapport mensuel : brouillon → relecture des textes → validation → PDF archivé ;
**Actualiser les chiffres** le recalcule si un mois est validé ou corrigé entre-temps.
Un bilan est possible dès qu'un mois est validé ; les mois non validés en sont exclus et signalés.

### Journal

Filtres par utilisateur, action, période et texte du détail ; 50 lignes par page ; **Exporter en CSV** (lignes filtrées).

## Profils clients

- **MDR + KSC** : rapport complet.
- **KSC seul** : pas de section MDR ; case « Proposer le service MDR » pour recommander l'offre quand la situation le justifie.
- **MDR seul** : sections KSC « en attente ».

Le tenant MDR d'un client se choisit dans sa fiche : les tenants trouvés dans les hebdos déposés sont proposés.
Le tenant racine s'écrit `root tenant` (c'est celui d'ANARE).

## Développement (poste Windows)

```bash
pip install -r requirements.txt
python gerer.py init
python gerer.py creer-admin vous@esay.ci "Votre Nom"
python -m app.main            # http://127.0.0.1:8010
```

Sous Windows, WeasyPrint s'installe difficilement : télécharger la version autonome
(`weasyprint-windows-onedir.zip` sur la page GitHub de WeasyPrint) et indiquer son chemin dans la variable
d'environnement `WEASYPRINT_EXE`. Sur le serveur Linux, la bibliothèque Python suffit.

Tests de bout en bout (base de développement ; ils nettoient leurs données) :

```bash
python -m outils_dev.essai_socle       # comptes, rôles, CSRF, clients
python -m outils_dev.essai_depots      # dépôt et analyse des fichiers réels
python -m outils_dev.essai_rapports    # brouillon, relecture, validation, versions, suivi
python -m outils_dev.essai_bilans      # fin de mois, actions groupées, évolution, bilans, journal
python -m outils_dev.essai_pilotage    # vue d'ensemble, parc, contrats, alertes, notifications (simulées), résumé
python -m outils_dev.essai_interventions  # rapports d'intervention, bibliothèque, PDF, envoi, historique
python -m outils_dev.essai_securite    # verrouillage, double authentification, sessions, journal chaîné
python -m outils_dev.essai_service     # assistances, techniciens, import, connaissances, rapport du service
python -m outils_dev.essai_supervision # métriques, journal vers syslog, événements de sécurité
python -m pytest                        # tests unitaires (pip install -r requirements-dev.txt)
```

## Évolution de la base (migrations Alembic)

Le schéma est géré par **Alembic** (`migrations/`). Les migrations en attente sont appliquées
**automatiquement au démarrage** de l'application (et par `python gerer.py init`) : aucun SQL à écrire sur le serveur.
Une base créée avant l'introduction des migrations est reconnue et marquée au niveau du schéma initial, sans perte.

Pour modifier la structure (nouvelle colonne, index…) :

```bash
# 1. modifier app/modeles.py
python -m alembic revision --autogenerate -m "ajout colonne x"   # 2. génère migrations/versions/xxxx_….py
# 3. relire le fichier généré (renommages, valeurs par défaut des colonnes non nulles…)
python -m alembic upgrade head                                   # 4. appliquer en local, puis tester
python -m alembic current                                        # révision actuelle de la base
```

Les migrations de données (ex. `0003` : chemins de fichiers au format « / ») s'écrivent à la main dans le même dossier.

## Organisation du code

```
app/
  moteur/      lecture des PDF (hebdos MDR, exports KSC), analyse, textes par défaut
  rendu/       rapport HTML/CSS -> PDF (WeasyPrint), graphiques, export Word
  web/         pages : connexion, tableau de bord, dépôts, relecture, administration
  templates/   gabarits des pages     static/   style, logo, polices, htmx
  modeles.py   tables PostgreSQL       services.py   données d'un client pour un mois, cycle des rapports
  vue_ensemble.py  statistiques du portefeuille     parc.py  parc et licences     alertes.py  règles, notifications, résumé
  analyses.py  analyse des fichiers en arrière-plan (processus séparés)
migrations/     migrations Alembic du schéma (appliquées au démarrage)
gerer.py       commandes : init, creer-admin, importer-clients, alertes, resume-hebdo
```

Voir **INSTALLATION.md** pour le déploiement sur le serveur.

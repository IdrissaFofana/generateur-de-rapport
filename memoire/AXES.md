# Axes du projet de mémoire

**Titre de travail** : *Plateforme locale et sécurisée d'analyse et de reporting de cybersécurité : détection
d'anomalies par apprentissage automatique et génération vérifiable de rapports par modèle de langage.*

**Type** : master professionnel en informatique, avec une contribution de type recherche (question, hypothèses,
protocole, résultats mesurés).

**Fil conducteur** : une plateforme hébergée en local qui **collecte** les données MDR/EDR (systèmes et réseaux),
les **analyse** (apprentissage automatique), **rédige** les rapports (modèle de langage) et **protège** ses propres
données et son infrastructure (sécurité).

> Confidentialité : ce dépôt est public. Les clients y sont désignés **Client A, B, C, D** ; aucun nom de client,
> d'appareil ou d'adresse réelle ne doit figurer dans les documents du mémoire.

Légende de l'état : ✅ fait · 🔄 en cours · ⏳ à faire

---

## Socle existant (partie professionnelle)

| Élément | État |
|---|---|
| Lecture des rapports hebdomadaires MDR et des exports KSC (PDF) | ✅ |
| Consolidation mensuelle, niveau de risque par règles, plan d'action | ✅ |
| Rapports mensuels PDF, relecture, validation, versions | ✅ |
| Bilans trimestriels et semestriels | ✅ |
| Rapports d'intervention avec bibliothèque d'actions | ✅ |
| Vue d'ensemble (statistiques du portefeuille), suivi du parc, contrats, alertes | ✅ |
| Service technique : assistances mensuelles planifiées, techniciens (formations, certifications), activités internes, rapport d'activité du service | ✅ |
| Import d'anciens rapports d'intervention (PDF, Word) et base de connaissances | ✅ |
| Migrations de schéma (Alembic), rôles, CSRF, journal | ✅ |

---

## Axe 1 — Intelligence artificielle générative (LLM)

**Problème** : la rédaction des rapports est coûteuse et de qualité variable ; un LLM rédige bien mais peut
**inventer des faits**, et les données clients ne peuvent pas quitter l'infrastructure.

**Question de recherche** : un modèle de langage exécuté **en local**, encadré par des données structurées et un
**vérificateur de faits**, produit-il des textes de rapport jugés aussi utiles que ceux d'un expert, sans erreur factuelle ?

**Hypothèses**
- H1 : les textes du LLM sont jugés plus clairs et plus utiles que les textes générés par règles.
- H2 : sans contrôle, le LLM introduit des erreurs factuelles mesurables.
- H3 : le vérificateur ramène ces erreurs à un niveau proche de zéro sans dégrader la qualité perçue.

| Élément | Détail | État |
|---|---|---|
| LLM1 — Serveur local | Ollama, modèle open-weight 7-8 Md de paramètres (2 modèles comparés), sans accès internet | ⏳ |
| LLM2 — Dossier de faits | Données consolidées réduites aux faits utiles, format structuré, champs non fiables isolés | ⏳ |
| LLM3 — Rédaction | Synthèse, commentaires de section, conclusion ; repli automatique sur les textes par règles | ⏳ |
| LLM4 — Vérificateur de faits | Extraction des nombres, appareils, menaces, dates du texte ; confrontation aux données ; correction ou signalement | ⏳ |
| LLM5 — Mode expérimental | Trois versions d'un même rapport (règles / LLM seul / LLM + vérification) présentées à l'aveugle | ⏳ |

**Évaluation** : exactitude factuelle, taux d'hallucination, couverture des points clés, notes d'experts à l'aveugle
(accord inter-évaluateurs : Fleiss / ICC), tests de Wilcoxon / Friedman, distance d'édition avec le texte validé.

---

## Axe 2 — Apprentissage automatique (ML)

**Contrainte** : peu de données (4 clients, historique court) → privilégier le **non supervisé**, les séries
journalières et l'**injection d'anomalies synthétiques** pour mesurer précision et rappel.

| Élément | Détail | État |
|---|---|---|
| ML1 — Anomalies de télémétrie MDR | Série journalière de postes par client : décomposition (tendance, jours ouvrés / week-end) + détection d'écarts, comparée à Isolation Forest et à un seuil statistique. Alerte « chute anormale de la télémétrie », marquage sur les courbes | ⏳ |
| ML2 — Priorité par appareil | Caractéristiques issues du suivi du parc (anomalies, jours sans connexion, OS, serveur, série en cours, détections). Score non supervisé (Isolation Forest), puis modèle explicable (arbre / gradient boosting + SHAP) prédisant « encore critique le mois suivant » | ⏳ |
| ML4 — Problèmes similaires et suggestion d'actions | Regroupement des points bloquants par similarité (Jaccard sur mots racinisés : version de base en place) ; évolution vers une similarité sémantique (TF-IDF ou plongements) et la suggestion d'actions à partir d'interventions passées comparables. Données : interventions saisies et importées | 🔄 base en place |
| ML3 — Générateur de données synthétiques | Séries et parcs réalistes, anomalies injectées et étiquetées ; sert aussi au corpus du LLM | ⏳ |

**Évaluation** : ML1 — précision, rappel, F1, délai de détection sur anomalies injectées ; ML2 — précision@10,
comparaison au classement par règles, stabilité des explications.

---

## Axe 3 — Sécurité informatique

| Élément | Détail | État |
|---|---|---|
| S1 — Injection de prompt indirecte | Les exports contiennent des noms d'appareils, fichiers, URL contrôlables par un attaquant et transmis au LLM. Jeu d'attaques, taux de succès sans / avec protections (neutralisation des champs, sortie structurée, vérificateur) | ⏳ |
| S2 — Authentification et sessions | Limitation des tentatives et verrouillage temporaire, double authentification TOTP (RFC 6238), invalidation des sessions (changement de mot de passe, désactivation), déconnexion par POST | ✅ |
| S3 — Journal d'audit infalsifiable | Chaînage des lignes par SHA-256 (chaque ligne contient l'empreinte de la précédente), verrou transactionnel, commande et page de vérification d'intégrité | ✅ |
| S4 — Pseudonymisation | Remplacement cohérent des clients, appareils, IP, utilisateurs ; corpus du mémoire et protection des données envoyées au LLM | ⏳ |
| S5 — Chiffrement au repos | PDF clients archivés et secrets TOTP chiffrés | ⏳ |
| S6 — Analyse outillée | Modèle de menaces STRIDE, grille OWASP ASVS, bandit (SAST), pip-audit (dépendances), OWASP ZAP (DAST), mesures avant / après | ⏳ |

---

## Axe 4 — Systèmes et réseaux

| Élément | Détail | État |
|---|---|---|
| R1 — Déploiement segmenté | Docker Compose : réseau d'accès (Nginx TLS + application), réseau de données (PostgreSQL non exposé), réseau LLM sans accès internet ; pare-feu ; accès distant par VPN ; schéma réseau | ⏳ |
| R2 — Collecte par services réseau | Boîte e-mail relevée en IMAP (envoi programmé depuis le KSC des clients), dossier partagé SMB surveillé ; TLS, filtrage des expéditeurs, contrôle des pièces jointes | ⏳ |
| R3 — Supervision | Métriques Prometheus / Grafana (analyses, erreurs, disponibilité du LLM), journaux vers syslog / SIEM | ⏳ |
| R4 — Durcissement du serveur | systemd durci, SSH par clés, fail2ban, audit Lynis avant / après | ⏳ |

---

## Ordre de développement

| Phase | Contenu | État |
|---|---|---|
| 1. Socle sécurisé | S2, S3, tests unitaires pytest | ✅ |
| 2. Infrastructure | R1, R4, R3 | ⏳ prochaine |
| 3. Données | S4, ML3, R2 | ⏳ |
| 4. Apprentissage automatique | ML1, ML2 | ⏳ |
| 5. Modèle de langage | LLM1 à LLM4 | ⏳ |
| 6. Sécurité du LLM | S1, LLM5 | ⏳ |
| 7. Expérimentations | Toutes les mesures, gel du code | ⏳ |

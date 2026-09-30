# Axes du projet de mémoire

**Titre de travail** : *Plateforme locale et sécurisée de pilotage d'un service de sécurité managée : analyse par
apprentissage automatique et génération vérifiable de rapports par modèle de langage.*

*(Titre précédent : « Plateforme locale et sécurisée d'analyse et de reporting de cybersécurité… ». Élargi le
30/09/2026 : la plateforme couvre désormais aussi l'exploitation du service technique.)*

**Type** : master professionnel en informatique, avec une contribution de type recherche (question, hypothèses,
protocole, résultats mesurés).

**Fil conducteur** : une plateforme hébergée en local qui **collecte** les données MDR/EDR et l'historique des
interventions (systèmes et réseaux), les **analyse** (apprentissage automatique), **rédige** les rapports clients et
les rapports du service (modèle de langage) et **protège** ses propres données et son infrastructure (sécurité).

**Deux volets professionnels**
- **A. Reporting de sécurité client** : rapports mensuels, bilans, vue d'ensemble, parc, contrats, alertes ;
- **B. Exploitation du service technique** : interventions, assistances mensuelles, techniciens, import de
  l'historique, base de connaissances, rapport d'activité du service.

**Règles contre la dispersion**
1. Une seule question de recherche principale (axe 1 : LLM + vérification des faits). ML4 est une contribution
   **secondaire**, annoncée comme telle.
2. Ce qui n'est pas évalué par une métrique reste dans la partie professionnelle (description courte, capture,
   chiffre de gain).
3. Tout élément présenté aux chapitres 6 ou 7 a une référence de base, une méthode et une métrique.

> Confidentialité : ce dépôt est public. Les clients y sont désignés **Client A, B, C, D** ; aucun nom de client,
> d'appareil ou d'adresse réelle ne doit figurer dans les documents du mémoire.

Légende de l'état : ✅ fait · 🔄 en cours · ⏳ à faire

---

## Socle existant (partie professionnelle)

| Élément | Volet | État |
|---|---|---|
| Lecture des rapports hebdomadaires MDR et des exports KSC (PDF) | A | ✅ |
| Consolidation mensuelle, niveau de risque par règles, plan d'action | A | ✅ |
| Rapports mensuels PDF, relecture, validation, versions | A | ✅ |
| Bilans trimestriels et semestriels | A | ✅ |
| Vue d'ensemble (statistiques du portefeuille), suivi du parc, contrats, alertes | A | ✅ |
| Rapports d'intervention avec bibliothèque d'actions | B | ✅ |
| Assistances mensuelles planifiées, techniciens (formations, certifications), activités internes, rapport d'activité du service | B | ✅ |
| Import d'anciens rapports d'intervention (PDF, Word) et base de connaissances | B | ✅ |
| Migrations de schéma (Alembic), rôles, CSRF, journal | transverse | ✅ |

---

## Axe 1 — Intelligence artificielle générative (LLM) — question principale

**Problème** : la rédaction des rapports est coûteuse et de qualité variable ; un LLM rédige bien mais peut
**inventer des faits**, et les données clients ne peuvent pas quitter l'infrastructure.

**Question de recherche** : un modèle de langage exécuté **en local**, encadré par des données structurées et un
**vérificateur de faits**, produit-il des textes de rapport jugés aussi utiles que ceux d'un expert, sans erreur factuelle ?

**Hypothèses**
- H1 : les textes du LLM sont jugés plus clairs et plus utiles que les textes générés par règles.
- H2 : sans contrôle, le LLM introduit des erreurs factuelles mesurables.
- H3 : le vérificateur ramène ces erreurs à un niveau proche de zéro sans dégrader la qualité perçue.
- H4 (partie professionnelle) : la plateforme réduit le temps de production des rapports (clients et service) et
  améliore la conformité des assistances mensuelles.

| Élément | Détail | État |
|---|---|---|
| LLM1 — Serveur local | Ollama, modèle open-weight 7-8 Md de paramètres (2 modèles comparés), sans accès internet | ⏳ |
| LLM2 — Dossier de faits | Données consolidées réduites aux faits utiles, format structuré, champs non fiables isolés | ⏳ |
| LLM3 — Rédaction | Synthèse, commentaires de section, conclusion ; repli automatique sur les textes par règles | ⏳ |
| LLM4 — Vérificateur de faits | Extraction des nombres, appareils, menaces, dates du texte ; confrontation aux données ; correction ou signalement | ⏳ |
| LLM5 — Mode expérimental | Trois versions d'un même rapport (règles / LLM seul / LLM + vérification) présentées à l'aveugle | ⏳ |
| LLM6 — Généralisation | Même chaîne appliquée au rapport d'activité du service (autre genre de document, autres données) : la vérification des faits se transpose-t-elle ? | ⏳ |

**Évaluation** : exactitude factuelle, taux d'hallucination, couverture des points clés, notes d'experts à l'aveugle
(accord inter-évaluateurs : Fleiss / ICC), tests de Wilcoxon / Friedman, distance d'édition avec le texte validé.

---

## Axe 2 — Apprentissage automatique (ML)

**Contrainte** : peu de données (4 clients, historique court) → privilégier le **non supervisé**, les séries
journalières et l'**injection d'anomalies synthétiques** pour mesurer précision et rappel. L'import de l'historique
des interventions (volet B) fournit un **second corpus**, textuel, avec des étiquettes naturelles (actions choisies
dans la bibliothèque) : c'est le support de ML4.

**Hypothèse H5** : la suggestion d'actions par similarité sémantique est plus précise que la référence lexicale
(Jaccard) sur des interventions mises de côté pour le test.

| Élément | Détail | État |
|---|---|---|
| ML1 — Anomalies de télémétrie MDR | Série journalière de postes par client : décomposition (tendance, jours ouvrés / week-end) + détection d'écarts, comparée à Isolation Forest et à un seuil statistique. Alerte « chute anormale de la télémétrie », marquage sur les courbes | ⏳ |
| ML2 — Priorité par appareil (optionnel) | Caractéristiques issues du suivi du parc (anomalies, jours sans connexion, OS, serveur, série en cours, détections). Score non supervisé (Isolation Forest), puis modèle explicable (arbre / gradient boosting + SHAP) prédisant « encore critique le mois suivant » | ⏳ |
| ML3 — Générateur de données synthétiques | Séries et parcs réalistes, anomalies injectées et étiquetées ; sert aussi au corpus du LLM | ⏳ |
| ML4 — Interventions similaires et suggestion d'actions (contribution secondaire) | Pour une nouvelle intervention (type, contexte, problème), retrouver les interventions passées comparables et suggérer actions et recommandations. Méthodes comparées : (1) Jaccard sur mots racinisés — **référence, en place** (regroupement des problèmes récurrents) ; (2) TF-IDF + cosinus ; (3) plongements sémantiques d'un modèle **local**. Données : interventions saisies et importées, actions issues de la bibliothèque | 🔄 référence en place |

**Évaluation** : ML1 — précision, rappel, F1, délai de détection sur anomalies injectées ; ML2 — précision@10,
comparaison au classement par règles, stabilité des explications ; ML4 — précision@k et rappel@k des actions
suggérées sur un jeu de test (validation par exclusion d'intervention), puis avis des techniciens sur l'utilité.

**Condition** : ML4 n'est solide qu'avec un corpus suffisant — objectif **plusieurs dizaines d'interventions**
importées ou saisies avant la phase 4.

---

## Axe 3 — Sécurité informatique

| Élément | Détail | État |
|---|---|---|
| S1 — Injection de prompt indirecte | Deux vecteurs : (a) les exports KSC contiennent des noms d'appareils, fichiers, URL contrôlables par un attaquant ; (b) le texte des rapports d'intervention importés (documents externes). Jeu d'attaques, taux de succès sans / avec protections (neutralisation des champs, sortie structurée, vérificateur) | ⏳ |
| S2 — Authentification et sessions | Limitation des tentatives et verrouillage temporaire, double authentification TOTP (RFC 6238), invalidation des sessions (changement de mot de passe, désactivation), déconnexion par POST | ✅ |
| S3 — Journal d'audit infalsifiable | Chaînage des lignes par SHA-256 (chaque ligne contient l'empreinte de la précédente), verrou transactionnel, commande et page de vérification d'intégrité | ✅ |
| S4 — Pseudonymisation | Remplacement cohérent des clients, appareils, IP, utilisateurs ; corpus du mémoire et protection des données envoyées au LLM | ⏳ |
| S5 — Chiffrement au repos | PDF clients archivés, justificatifs de certification et secrets TOTP chiffrés | ⏳ |
| S6 — Analyse outillée | Modèle de menaces STRIDE, grille OWASP ASVS, bandit (SAST), pip-audit (dépendances), OWASP ZAP (DAST), mesures avant / après | ⏳ |
| S7 — Fichiers déposés et données personnelles | Contrôle des dépôts par extension **et** signature binaire, taille maximale, stockage sous empreinte (nom non contrôlé par l'utilisateur) — **fait** ; accès aux justificatifs limité au titulaire, aux validateurs et aux administrateurs — **fait** ; reste : durée de conservation, droits d'accès et de suppression (loi ivoirienne n° 2013-450 sur les données personnelles, RGPD en référence), analyse des documents importés avant lecture | 🔄 |

---

## Axe 4 — Systèmes et réseaux

| Élément | Détail | État |
|---|---|---|
| R1 — Déploiement segmenté | Docker Compose : réseau d'accès (Nginx TLS + application), réseau de données (PostgreSQL non exposé), réseau LLM sans accès internet ; pare-feu ; accès distant par VPN ; schéma réseau | ⏳ |
| R2 — Collecte par services réseau | Boîte e-mail relevée en IMAP (envoi programmé depuis le KSC des clients), dossier partagé SMB surveillé ; TLS, filtrage des expéditeurs, contrôle des pièces jointes | ⏳ |
| R3 — Supervision | Métriques Prometheus / Grafana (analyses, erreurs, disponibilité du LLM), journaux et alertes métier (assistances, certifications) vers syslog / SIEM, ancre du journal d'audit | ⏳ |
| R4 — Durcissement du serveur | systemd durci, SSH par clés, fail2ban, audit Lynis avant / après | ⏳ |

---

## Ordre de développement

| Phase | Contenu | État |
|---|---|---|
| 1. Socle sécurisé | S2, S3, tests unitaires pytest | ✅ |
| — Service technique (hors plan initial) | Volet B complet, référence ML4, S7 partiel | ✅ |
| 2. Infrastructure | R1, R4, R3 | ⏳ prochaine |
| 3. Données | S4, ML3, R2 | ⏳ |
| 4. Apprentissage automatique | ML1, ML4 (puis ML2 si le temps le permet) | ⏳ |
| 5. Modèle de langage | LLM1 à LLM4, LLM6 | ⏳ |
| 6. Sécurité du LLM | S1, LLM5 | ⏳ |
| 7. Expérimentations | H1 à H5, toutes les mesures, gel du code | ⏳ |

**À faire en continu, dès maintenant** : importer les anciens rapports d'intervention (corpus ML4) et mesurer la
situation de référence **avant** adoption de la plateforme (temps d'un rapport mensuel, d'un rapport d'intervention
et du rapport semestriel du service faits à la main).

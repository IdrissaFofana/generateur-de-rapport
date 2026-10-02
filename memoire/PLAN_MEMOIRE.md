# Plan du mémoire — document de référence

> **Ce plan fait foi.** Tout travail qui ne sert pas une section de ce plan n'entre pas dans le mémoire (voir
> « Hors périmètre »). Une section n'est terminée que lorsque son **critère de fin** est rempli. Les autres documents
> (`AXES.md`, `JOURNAL_DE_BORD.md`, `CONTENU_MEMOIRE.md`) suivent ce plan.

**Titre** : *Intelligence artificielle pour le reporting de cybersécurité : détection d'anomalies et génération
vérifiable de rapports par un grand modèle de langage (LLM) local dans un service MDR/EDR.*

**Structure imposée** : 3 parties de 3 chapitres chacune, encadrées par une introduction et une conclusion générales.

---

## 1. Ce que le titre impose (le contrat)

Le titre contient trois promesses. Chacune a **sa question de recherche, sa conception et son évaluation**. Aucune ne
peut être abandonnée.

| Promesse du titre | Question de recherche | Conception | Évaluation | Hypothèses |
|---|---|---|---|---|
| « détection d'anomalies » | **QR1** — Sur des données MDR/EDR peu nombreuses, une détection d'anomalies **apprise** repère-t-elle mieux qu'un seuil fixe les dégradations de la supervision (chute de télémétrie, pic de détections) ? | 6.1 | 7 | H1 |
| « génération vérifiable de rapports par un LLM local » | **QR2** — Un LLM exécuté en local, encadré par un dossier de faits et un vérificateur, rédige-t-il des textes jugés au moins aussi utiles que la référence par règles, sans erreur factuelle ? | 6.2 | 8 | H2, H3, H4 |
| « cybersécurité » (le LLM lit des données contrôlables par un attaquant) | **QR3** — Les données de sécurité permettent-elles une injection de prompt indirecte contre le LLM, et les protections proposées l'empêchent-elles ? | 6.3 | 9 | H5 |

Une mesure professionnelle complète l'ensemble (master professionnel) : **H6** — la plateforme réduit le temps de
production des rapports (chapitre 9).

### Hypothèses (formulées pour être réfutables)

- **H1** — La détection apprise obtient un meilleur F1 que le seuil fixe sur les anomalies injectées, à taux de
  fausses alertes comparable.
- **H2** — Sans vérification, le LLM introduit des erreurs factuelles mesurables (taux de rapports erronés > 0).
- **H3** — Le vérificateur ramène ce taux à moins de 1 % des faits, sans baisse significative de la qualité perçue.
- **H4** — Les textes du LLM vérifié sont jugés au moins aussi clairs et utiles que ceux de la référence par règles
  (notes d'experts à l'aveugle, test de Wilcoxon).
- **H5** — Sans protection, une part mesurable des attaques par injection indirecte modifie le rapport ; avec les
  protections, ce taux devient nul ou quasi nul.
- **H6** — Le temps de production d'un rapport mensuel est inférieur à celui du processus manuel.

---

## 2. Plan détaillé — 3 parties de 3 chapitres

Budget indicatif : **85 à 95 pages** hors annexes. Chaque partie s'ouvre sur une courte introduction (½ page :
objectif et enchaînement des chapitres) et se ferme sur une conclusion de partie (½ page : acquis et transition).

| Partie | Chapitres | Pages | Rôle |
|---|---|---|---|
| I. Cadre de l'étude | 1 · 2 · 3 | ≈ 28 | Comprendre : le terrain, le problème, ce que dit la littérature |
| II. Conception et réalisation | 4 · 5 · 6 | ≈ 32 | Construire : la plateforme, sa sécurité, les modules d'IA |
| III. Expérimentations et résultats | 7 · 8 · 9 | ≈ 28 | Démontrer : une question de recherche par chapitre |

### Introduction générale (≈ 5 p.)
Contexte, problématique, QR1 à QR3, contributions, organisation en trois parties.
- **Critère de fin** : chaque contribution annoncée renvoie à un résultat chiffré de la partie III.

---

### PARTIE I — CADRE DE L'ÉTUDE

#### Chapitre 1 — Contexte, données et problématique (≈ 9 p.)
1. L'entreprise, le service MDR/EDR et le portefeuille (clients A à D)
2. Les sources de données (hebdomadaires MDR, exports KSC) et leurs limites
3. Le processus manuel **mesuré** (temps, corrections, délais) → référence de H6
4. Besoins et contraintes : hébergement local, confidentialité, traçabilité
5. Problématique, questions de recherche QR1 à QR3 et hypothèses H1 à H6
- **Livrable** : tableau des sources ; tableau des mesures du processus manuel.
- **Critère de fin** : temps du processus manuel **mesurés** sur au moins 3 rapports.

#### Chapitre 2 — État de l'art : supervision de sécurité et détection d'anomalies (≈ 9 p.)
1. SOC, services MDR/EDR et reporting de sécurité
2. Détection d'anomalies : approches statistiques, Isolation Forest, séries temporelles
3. Données rares et évaluation par injection d'anomalies synthétiques
4. Synthèse : manque identifié pour QR1
- **Livrable** : au moins 10 références, dont 6 articles scientifiques.
- **Critère de fin** : QR1 rattachée à un manque de la littérature.

#### Chapitre 3 — État de l'art : LLM, génération vérifiable et sécurité des LLM (≈ 10 p.)
1. Génération de texte à partir de données (data-to-text) et LLM
2. Hallucinations et vérification des faits
3. LLM exécutés localement : modèles open-weight, quantification, confidentialité
4. Sécurité des applications à base de LLM : injection de prompt directe et indirecte, défenses
5. Positionnement : tableau comparatif des travaux existants et de ce mémoire
- **Livrable** : au moins 15 références, dont 9 articles scientifiques ; tableau de positionnement.
- **Critère de fin** : QR2 et QR3 rattachées à un manque de la littérature.

---

### PARTIE II — CONCEPTION ET RÉALISATION

#### Chapitre 4 — Plateforme support et référence par règles (≈ 10 p.)
La plateforme est le **terrain d'expérimentation** : elle est décrite pour ce qu'elle apporte à la partie III.
1. Architecture logicielle et choix techniques justifiés
2. Chaîne de traitement d'un rapport mensuel (dépôt → consolidation → rapport → validation)
3. **Référence par règles** : seuils d'alerte, niveau de risque, diagnostic par raison, couverture MDR, textes par
   gabarits → bases de comparaison des chapitres 7 et 8
4. Qualité logicielle : tests unitaires et de bout en bout
- **Livrable** : schéma d'architecture, diagramme de données, description de la référence.
- **Critère de fin** : chaque règle de référence utilisée en partie III est décrite ici.

#### Chapitre 5 — Sécurité et déploiement de la plateforme (≈ 11 p.)
1. Modèle de menaces (STRIDE)
2. Authentification forte et sessions ; journal d'audit chaîné et ancré
3. Déploiement segmenté (le LLM sur un réseau sans sortie), durcissement du serveur, supervision
4. Évaluation : bandit, pip-audit, vérification du déploiement, Lynis, systemd-analyze ou Docker Bench,
   testssl.sh, OWASP ZAP — **avant / après**
- **Livrable** : schéma réseau et matrice des flux, tableau menace → mesure → test, tableau des audits.
- **Critère de fin** : audits réalisés **sur le serveur** et reportés avant / après.

#### Chapitre 6 — Conception des modules d'intelligence artificielle (≈ 11 p.)
1. Module de détection d'anomalies : caractéristiques, score statistique robuste, Isolation Forest, intégration
   aux alertes et au rapport
2. Chaîne de génération vérifiable : dossier de faits → LLM local → vérificateur de faits et règles de cohérence →
   correction, régénération ou repli sur les textes par règles
3. Protections contre l'injection de prompt : isolement des champs non fiables, sortie structurée, vérification
4. Choix et déploiement du modèle local (deux modèles open-weight comparés)
- **Livrable** : modules réalisés et intégrés ; schéma de la chaîne ; consignes (prompts) en annexe.
- **Critère de fin** : les trois modules fonctionnent dans la plateforme sur données réelles.

---

### PARTIE III — EXPÉRIMENTATIONS ET RÉSULTATS

#### Chapitre 7 — Évaluation de la détection d'anomalies (≈ 9 p.) — QR1
1. Données et corpus : séries réelles et anomalies injectées (chute brutale, dérive lente, pic)
2. Protocole et métriques : précision, rappel, F1, délai de détection, fausses alertes par mois
3. Résultats : seuil fixe, méthode statistique et Isolation Forest comparés ; épisodes réels
4. Discussion et test de H1
- **Livrable** : tableau des résultats, figure d'une série annotée.
- **Critère de fin** : H1 confirmée ou réfutée avec des chiffres.

#### Chapitre 8 — Évaluation de la génération vérifiable de rapports (≈ 11 p.) — QR2
**Chapitre central du mémoire.**
1. Corpus anonymisé (réels + synthétiques) et 3 versions par rapport (règles / LLM seul / LLM + vérification)
2. Métriques automatiques : exactitude factuelle, taux d'hallucination, couverture des points clés
3. Évaluation humaine à l'aveugle : 3 experts au minimum, accord inter-évaluateurs, test de Wilcoxon
4. Résultats, analyse des erreurs, test de H2, H3, H4
- **Livrable** : tableaux de résultats, exemples commentés.
- **Critère de fin** : H2 à H4 testées sur au moins 30 rapports avec 3 évaluateurs.

#### Chapitre 9 — Robustesse à l'injection de prompt, apport professionnel et discussion (≈ 8 p.) — QR3
1. Jeu d'attaques par injection indirecte (au moins 50) et résultats sans / avec protections ; test de H5
2. Apport professionnel : temps de production avant / après ; test de H6
3. Synthèse des réponses à QR1 à QR3
4. Limites et menaces à la validité
- **Livrable** : tableau des taux de succès des attaques ; tableau avant / après ; tableau de synthèse des hypothèses.
- **Critère de fin** : chaque hypothèse a une ligne « confirmée / réfutée / nuancée » justifiée.

---

### Conclusion générale et perspectives (≈ 3 p.)
Perspectives (éléments « hors périmètre ») et prolongement doctoral : robustesse et vérifiabilité des LLM appliqués
à l'analyse de données de sécurité.

### Annexes (hors budget)
A. Installation et déploiement · B. Fonctions de la plateforme hors sujet de recherche (≤ 3 pages) ·
C. Grilles d'évaluation et consignes aux experts · D. Exemples de rapports anonymisés · E. Consignes (prompts) ·
F. Jeu d'attaques.

### Résumé (français et anglais) et article
- Résumé rédigé **en dernier**, avec les résultats chiffrés.
- **Article** tiré des chapitres 8 et 9 (6 à 8 pages) : objectif doctoral.

---

## 3. Hors périmètre (décidé, ne pas y revenir)

Ces éléments existent ou sont intéressants, mais **ne servent pas le titre**. Ils vont en annexe B (s'ils existent)
ou en perspectives (s'ils sont à faire). **Ne pas les développer pendant le mémoire.**

| Élément | Destination |
|---|---|
| Service technique : assistances mensuelles, techniciens, activités internes, rapport d'activité du service | Annexe B (description courte) |
| Rapports d'intervention, bibliothèque d'actions, import d'anciens rapports, doublons | Annexe B |
| ML4 — suggestion d'actions par similarité | Perspectives (référence Jaccard citée) |
| ML2 — priorisation des appareils | Perspectives |
| LLM6 — génération du rapport du service | Perspectives |
| R2 — collecte automatique par e-mail (IMAP) ou partage réseau (SMB) | Perspectives |
| S5 — chiffrement au repos | Perspectives (limite citée au chapitre 5) |
| Vue d'ensemble, contrats, suivi du parc, interface | Chapitre 4 en une phrase + annexe B |

**Règle** : une nouvelle demande de fonctionnalité pour l'entreprise peut être réalisée, mais elle **n'entre pas** dans
le mémoire, sauf si elle remplit le critère de fin d'une section ci-dessus.

---

## 4. Règles contre la dispersion

1. **Une question de recherche = une conception (chapitre 6) + une évaluation (partie III) + des hypothèses
   testées.** Pas de chapitre de la partie III sans hypothèse.
2. **Pas de résultat sans référence de base** : chaque méthode est comparée à la référence par règles (chapitre 4).
3. **Pas de section « décrite » sans preuve** : un chiffre, un tableau ou une figure par section.
4. **La chaîne LLM vérifiable (6.2 et chapitre 8) passe avant tout** en cas de manque de temps : elle porte la
   contribution principale.
5. **Rédiger au fil de l'eau** : chaque phase se termine par le brouillon de ses sections dans `CONTENU_MEMOIRE.md`.
6. **Lecture continue** pour les chapitres 2 et 3 : 3 articles par semaine, fiche de lecture de 5 lignes chacun
   (`LECTURES.md`).
7. **Équilibre des parties** : 3 chapitres par partie, ni plus ni moins ; tout nouveau contenu s'insère dans un
   chapitre existant.

---

## 5. Ordre de travail

| Semaines | Travail | Sections alimentées | Critère de passage |
|---|---|---|---|
| S1 | Mesures du processus manuel (H6) ; pseudonymisation des données | 1.3, 8.1 | Tableau des temps manuels ; données anonymisées |
| S2 | Générateur d'anomalies et de rapports synthétiques ; corpus constitué | 7.1, 8.1 | ≥ 30 mois-clients exploitables |
| S3 – S5 | Détection d'anomalies : module, protocole, résultats | 6.1, 7 | H1 testée ; brouillons 6.1 et 7 |
| S6 – S9 | LLM local, dossier de faits, rédaction, vérificateur | 6.2, 6.4 | 3 versions générées pour tout le corpus |
| S10 – S11 | Injection de prompt : attaques et protections | 6.3, 9.1 | H5 testée ; brouillons 6.3 et 9.1 |
| S12 – S13 | Évaluation par les experts, statistiques ; audits sur le serveur | 5.4, 8, 9 | H2 à H4 testées ; tableau d'audit complet |
| S14 – S16 | Chapitres 2 et 3 finalisés, introduction, conclusions de partie, conclusion, résumé ; article | tous | Mémoire complet ; article soumis |

En continu dès S1 : lecture pour les chapitres 2 et 3 (règle 6).

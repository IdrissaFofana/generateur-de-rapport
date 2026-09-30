# Contenu du mémoire (brouillon rédigé au fil du développement)

Texte de travail, chapitre par chapitre. En fin de projet, il ne restera que la mise en forme (gabarit de
l'établissement, figures, bibliographie normalisée). Les passages ⏳ indiquent ce qui reste à produire et avec
quelles données.

> Confidentialité : clients désignés Client A, B, C, D ; noms d'appareils et adresses remplacés.

**Titre de travail** : *Plateforme locale et sécurisée de pilotage d'un service de sécurité managée : analyse par
apprentissage automatique et génération vérifiable de rapports par modèle de langage.*

**Plan d'ensemble**
1. Introduction · 2. État de l'art · 3. Contexte et existant · 4. Conception et réalisation (volet A : reporting
client ; volet B : service technique) · 5. Sécurité · 6. Apprentissage automatique · 7. Modèle de langage et
vérification des faits · 8. Expérimentations (H1 à H5) · 9. Conclusion.

---

## Résumé ⏳
À rédiger en dernier (contexte, problème, approche, résultats chiffrés, conclusion), en français et en anglais.

---

## Chapitre 1 — Introduction

### 1.1 Contexte
Les prestataires de services de sécurité managée assurent pour leurs clients la supervision des postes et
serveurs (antivirus et EDR administrés depuis une console centrale, détection et réponse managées — MDR).
Au-delà de la supervision, ils doivent **rendre compte** : chaque mois, chaque client reçoit un rapport qui
présente l'état de protection de son parc, les menaces détectées, les vulnérabilités, les incidents et un plan
d'action. Ce rapport engage le prestataire : il fonde les décisions du client et sert de preuve du service rendu.

Chez ESAY Corporation, partenaire Kaspersky, ces rapports étaient produits à la main à partir de documents PDF
hétérogènes (rapports hebdomadaires du service MDR, exports de la console Kaspersky Security Center transmis
par chaque client). Ce travail est long, répétitif, sujet aux erreurs de recopie, et sa qualité dépend du rédacteur.

Le même constat vaut pour l'**exploitation du service technique** : rapports d'intervention rédigés sous Word,
engagement d'assistance mensuelle suivi de mémoire, rapport d'activité semestriel du service compilé à la main,
certifications des techniciens suivies de manière informelle. Le savoir-faire accumulé dans les rapports
d'intervention passés reste inexploité : un problème déjà résolu chez un client est souvent re-diagnostiqué chez
un autre.

### 1.2 Problématique
Automatiser ce reporting soulève trois difficultés :
1. **Extraire et consolider** des données fiables depuis des sources semi-structurées et incomplètes ;
2. **Analyser** ces données au-delà de simples seuils, alors que l'historique est court et les incidents rares ;
3. **Rédiger** des textes utiles au client sans introduire d'erreur, alors que les modèles de langage peuvent
   inventer des faits et que les données, confidentielles, ne peuvent pas quitter l'infrastructure ;
4. **Capitaliser** sur l'historique des interventions pour guider les interventions futures, à partir de documents
   hétérogènes rédigés librement.

À cela s'ajoute une exigence transversale : une plateforme qui centralise les données de sécurité de plusieurs
clients devient elle-même une **cible** ; sa sécurité et celle de son infrastructure font partie du problème.

### 1.3 Question de recherche et hypothèses
*Un modèle de langage exécuté en local, encadré par des données structurées et un vérificateur de faits,
peut-il produire des textes de rapport de sécurité jugés aussi utiles que ceux d'un expert, sans erreur factuelle ?*
Hypothèses H1 à H3 : voir `AXES.md`, axe 1. H4 (partie professionnelle) : la plateforme réduit le temps de
production des rapports (clients et service) et améliore la conformité des assistances mensuelles.
H5 (contribution secondaire) : la suggestion d'actions par similarité sémantique est plus précise que la référence
lexicale.

### 1.4 Contributions ⏳ (à confirmer par les résultats)
**Contribution principale**
1. Une chaîne de rédaction hybride (données structurées + modèle de langage local) avec vérification des faits,
   évaluée sur les rapports clients et généralisée au rapport du service.
2. Une évaluation de la robustesse à l'injection de prompt indirecte via les données de sécurité et les documents
   importés.

**Contributions secondaires**
3. Une suggestion d'actions à partir des interventions passées similaires (ML4), comparée à une référence lexicale.
4. Une détection d'anomalies adaptée à des données rares (télémétrie MDR).

**Contributions professionnelles**
5. Une plateforme hébergée en local couvrant le reporting de sécurité client et l'exploitation du service technique.
6. Une infrastructure segmentée et durcie, évaluée par des outils d'audit.

### 1.5 Organisation du document ⏳

---

## Chapitre 2 — État de l'art ⏳
- 2.1 Centres opérationnels de sécurité, MDR/EDR et reporting de sécurité
- 2.2 Extraction d'information depuis des documents semi-structurés
- 2.3 Détection d'anomalies dans les séries temporelles et sur données rares (Isolation Forest, décompositions saisonnières)
- 2.4 Génération de texte à partir de données (data-to-text), modèles de langage, hallucinations et vérification des faits
- 2.5 Recherche d'information et recommandation : similarité lexicale (Jaccard), TF-IDF, plongements sémantiques,
  raisonnement à partir de cas (retrouver un cas passé similaire pour résoudre le nouveau)
- 2.6 Sécurité des applications à base de LLM : injection de prompt directe et indirecte
- 2.7 Sécurité des applications web (OWASP), authentification forte, journalisation infalsifiable
- 2.8 Positionnement du travail

---

## Chapitre 3 — Contexte et analyse de l'existant

### 3.1 L'entreprise et le service
ESAY Corporation fournit à ses clients des solutions Kaspersky (protection des terminaux, EDR, service MDR) et
en assure l'administration et le suivi. Le portefeuille étudié compte quatre clients (A à D), tous au profil
« MDR + KSC ».

### 3.2 Les sources de données
| Source | Contenu | Fréquence | Particularités |
|---|---|---|---|
| Rapport hebdomadaire MDR | Postes transmettant leur télémétrie par jour et par tenant, incidents | Hebdomadaire, tous clients | Semaine du lundi au lundi, parution différée ; un même fichier couvre tous les clients (répartition par tenant) |
| Export KSC « État de la protection » | Appareils, état, anomalies, système, groupe | Mensuel, par client | Transmis par le client |
| Export KSC « Menaces » | Détections, catégories, appareils touchés | Mensuel, par client | Détail parfois tronqué par la console |
| Export KSC « Vulnérabilités » | Vulnérabilités par application et gravité | Mensuel, par client | Détail limité à 1 000 lignes ; totaux fiables dans le récapitulatif |

### 3.3 Les processus manuels ⏳ (mesures à faire avant adoption)
Deux circuits à décrire et à **mesurer**, références pour H4 :
- **Rapport mensuel client** : collecte, recopie, graphiques, rédaction, relecture, envoi — temps moyen par
  rapport, nombre de corrections, délai après la fin du mois.
- **Service technique** : rapport d'intervention sous Word (temps de rédaction), suivi des assistances mensuelles
  (mois sans assistance, constatés a posteriori), rapport d'activité semestriel compilé à la main (temps de
  compilation), suivi des certifications.

### 3.4 Besoins et contraintes
- Fonctionnels (volet A) : dépôt des sources, consolidation, rapport PDF à la charte, relecture et validation,
  suivi des actions d'un mois sur l'autre, bilans périodiques, pilotage du portefeuille.
- Fonctionnels (volet B) : rapports d'intervention, assistance mensuelle garantie, suivi des techniciens, reprise
  de l'historique, rapport d'activité du service.
- Non fonctionnels : **hébergement local** (pas d'accès distant aux consoles des clients, données confidentielles),
  traçabilité, rôles (lecteur, opérateur, validateur, administrateur), robustesse face aux données manquantes.

---

## Chapitre 4 — Conception et réalisation de la plateforme

### 4.1 Architecture générale
Application web Python (FastAPI) rendue côté serveur (Jinja2) avec interactions légères (HTMX), base
PostgreSQL, génération PDF par WeasyPrint. Les analyses de fichiers lourds s'exécutent dans des **processus
séparés** (lecture PDF non réentrante, serveur web réactif). ⏳ Schéma d'architecture (modèle C4).

**Justifications** : rendu serveur plutôt qu'application monopage — moins de surface d'attaque, pas de
chaîne de construction front, adapté à un outil interne ; WeasyPrint plutôt que Word — rendu reproductible,
versionnable, sans suite bureautique sur le serveur ; hébergement local — imposé par la confidentialité.

### 4.2 Modèle de données
Tables principales : utilisateurs, clients, hebdos, exports_ksc, rapports (mensuels, trimestriels, semestriels,
versionnés), journal, contrats, alertes, envois, interventions, bibliothèque. Les données consolidées et les
textes d'un rapport sont stockés en JSONB et **figés à la validation** (le PDF archivé reste la référence).
Évolution du schéma par migrations Alembic appliquées au démarrage. ⏳ Diagramme entité-association.

### Volet A — Reporting de sécurité client

### 4.3 Chaîne de traitement d'un rapport mensuel
1. Dépôt des hebdos MDR (une fois pour tous les clients) et des exports KSC (par client) ; empreinte SHA-256
   (dédoublonnage, nom de fichier non contrôlé par l'utilisateur).
2. Analyse en arrière-plan, reconnaissance automatique du type d'export, détection des exports hors période.
3. Consolidation : couverture MDR (jours à venir distingués des jours manquants), protection, menaces,
   vulnérabilités, niveau de risque par règles, plan d'action, suivi des actions du mois précédent.
4. Brouillon, relecture, validation → PDF archivé, version figée ; nouvelle version possible.

### 4.4 Règles métier notables
- **Jours à venir** : un jour n'est compté manquant que si l'hebdo qui le couvre aurait déjà dû paraître
  (lundi suivant + 3 jours).
- **Remplacement des exports** : le dernier export analysé d'un type remplace les précédents du même mois.
- **Suivi des actions** : les actions encore ouvertes sont reprises dans le rapport suivant ; les points bloquants
  d'une intervention peuvent y être ajoutés.
- **Diagnostic par raison** : la colonne « Raison » de l'export KSC est lue phrase par phrase et rapprochée d'une base
  de règles (16 raisons : cause probable, recommandation, responsable). Le rapport présente un diagnostic par raison
  et un classement des appareils par état et par combinaison de raisons ; une raison inconnue est signalée
  telle quelle plutôt qu'ignorée. Cette base de règles constitue la référence à laquelle seront comparées les
  recommandations rédigées par le modèle de langage (chapitre 7).
- **Couverture MDR** : statut calculé sur la part du parc supervisée (≥ 95 % normal, < 50 % critique), et non sur la
  seule présence de télémétrie.

### 4.5 Pilotage du portefeuille
Vue d'ensemble, suivi du parc, contrats, alertes : description et captures ⏳.

### Volet B — Exploitation du service technique

### 4.6 Service technique
Au-delà du reporting client, la plateforme outille le **service technique** :
- **Assistance mensuelle** : pour chaque client sous contrat, au moins une assistance par mois, planifiée
  automatiquement et rapprochée des rapports d'intervention validés ; conformité mensuelle, reports justifiés,
  alertes de fin de mois.
- **Rapports d'intervention** : saisie assistée par une bibliothèque de 105 actions et recommandations
  (terminologie Kaspersky) filtrée par type d'intervention, titre du document selon le type, envoi au client.
- **Import de l'historique** : anciens rapports PDF / Word lus automatiquement puis vérifiés ; le document d'origine
  fait foi. Cet import constitue le corpus exploitable par les volets d'analyse (base de connaissances, ML4).
  Le client est reconnu par son nom, ses autres noms ou ses tenants, indépendamment de la casse, des accents et de la
  ponctuation ; un document d'un client inconnu est **mis en attente** (jamais rattaché d'office), puis rattaché
  manuellement ou automatiquement dès la création du client. Principe retenu : préférer une attente explicite à un
  rattachement silencieux et possiblement faux.
  Les **doublons** sont contrôlés à deux niveaux : fichier identique (empreinte SHA-256, refus) et **doublon
  probable** sur le contenu (similarité de Jaccard ≥ 0,6 à dates proches, ≥ 0,85 sinon), soumis à la décision de
  l'utilisateur (importer quand même / annuler). Sur les documents réels, le même rapport en Word et en PDF obtient
  0,99 et deux rapports différents 0,12. Ce contrôle protège la qualité du corpus utilisé au chapitre 6.
- **Base de connaissances** : recherche plein texte dans toutes les interventions, et détection des problèmes
  récurrents entre clients par similarité de Jaccard sur des mots racinisés.
- **Techniciens** : parcours de formation, certifications avec justificatifs et échéances.
- **Rapport d'activité du service** (mensuel, trimestriel, semestriel, annuel) : indicateurs, assistances, activité
  par client et par technicien, faits marquants, incidents, problèmes récurrents, compétences, activités internes.
⏳ Captures et mesure du gain de temps sur le rapport semestriel (auparavant rédigé à la main).

### Aspects transverses

### 4.7 Interface
Choix de conception (hiérarchie, typographie, motif hexagonal, couleurs validées pour la lisibilité et le
daltonisme, petits multiples plutôt que doubles axes) ⏳ captures.

### 4.8 Tests
Deux niveaux de tests. **Tests unitaires** (pytest, 46 tests) sur les fonctions pures : conformité TOTP aux
vecteurs de la RFC 6238, détection de falsification du journal, limiteur de tentatives, règles métier (jours à
venir, périodes des bilans, fins de support, séries d'anomalies). **Tests de bout en bout** (8 suites,
220 vérifications) qui pilotent l'application réelle (client HTTP de test, vraie base, vrais fichiers PDF) :
dépôts et analyse, cycle de vie des rapports, bilans, pilotage, interventions, sécurité, service technique
(avec import des vrais rapports d'intervention historiques). Chaque suite nettoie ses
données, à l'exception du journal d'audit, par conception (voir 5.3). ⏳ Couverture de code.

---

## Chapitre 5 — Sécurité de la plateforme et de l'infrastructure 🔄
- 5.1 Modèle de menaces (STRIDE) ⏳
### 5.2 Authentification et sessions (S2)
Menaces visées (STRIDE) : usurpation d'identité par force brute ou vol de mot de passe, énumération des comptes,
détournement de session. Mesures :
- **Mots de passe** hachés par scrypt (sel aléatoire, n = 2^14, r = 8, p = 1), longueur minimale 10, mélange
  lettres et chiffres.
- **Force brute** : verrouillage du compte après 5 échecs consécutifs pendant 15 min (état en base) et
  limitation par adresse IP (20 échecs sur une fenêtre glissante de 15 min).
- **Énumération** : un message d'erreur unique, et un coût de vérification identique que le compte existe ou non
  (vérification contre une empreinte leurre précalculée) ; sans cela, l'écart de temps de réponse révèle les
  comptes existants.
- **Double authentification** TOTP (RFC 6238) implémentée sans dépendance ni service tiers, cohérent avec
  l'hébergement local : comparaison en temps constant, tolérance d'un pas de 30 s, **refus du rejeu** d'un code
  déjà accepté, activation confirmée par un premier code, réinitialisation par un administrateur, obligation
  paramétrable par rôle.
- **Sessions** : cookie signé, SameSite=Lax, Secure en HTTPS ; *version de session* stockée dans le cookie et en
  base, incrémentée à chaque événement sensible (mot de passe, 2FA, rôle, désactivation) : toute session
  antérieure est refusée. Déconnexion par POST protégé par CSRF.
- Validation : 25 tests unitaires et 27 vérifications de bout en bout. ⏳ Tableau menace / mesure / test.

### 5.3 Journal d'audit infalsifiable (S3)
Un journal modifiable par un administrateur de base de données n'apporte aucune garantie de non-répudiation.
Chaque ligne i porte h(i) = SHA-256( h(i-1) | id | date | acteur | action | détail ), avec h(0) = 64 zéros et un
séparateur absent des données. Toute modification d'une ligne invalide son empreinte ; toute suppression,
insertion ou permutation rompt le lien avec h(i-1). L'écriture est sérialisée par un verrou consultatif
PostgreSQL tenu jusqu'à la validation de la transaction, ce qui garantit une chaîne linéaire malgré les requêtes
concurrentes. L'acteur est figé dans la ligne et la suppression d'un compte ne modifie pas le journal
(clé étrangère SET NULL).
**Limite et parade** : tronquer la fin du journal reste indétectable par la seule chaîne ; il faut conserver
l'empreinte de tête (« ancre ») hors de la base, prévu par l'envoi périodique vers un collecteur syslog (R3).
⏳ Figure : schéma de la chaîne ; mesure du surcoût d'écriture.
- 5.4 Chiffrement au repos, pseudonymisation ⏳
- 5.5 Fichiers déposés et données personnelles (S7) 🔄 : contrôle par signature binaire, stockage sous empreinte,
  droits d'accès aux justificatifs ; conservation et droits des personnes ⏳
- 5.6 Architecture réseau segmentée et durcissement (R1, R4) ⏳
- 5.7 Évaluation outillée : bandit, pip-audit, ZAP, Lynis — avant / après ⏳

---

## Chapitre 6 — Analyse par apprentissage automatique ⏳
- 6.1 Données : télémétrie MDR (rare) et corpus des interventions (saisies + importées), générateur synthétique
- 6.2 ML1 — anomalies de télémétrie : méthodes comparées, protocole d'injection, résultats
- 6.3 ML4 — interventions similaires et suggestion d'actions : référence Jaccard (en place), TF-IDF, plongements
  locaux ; protocole par exclusion d'intervention, précision@k, rappel@k, avis des techniciens → H5
- 6.4 ML2 — priorisation des appareils (si réalisé) : caractéristiques, modèle, explications, résultats

## Chapitre 7 — Rédaction par modèle de langage et vérification des faits ⏳
- 7.1 Dossier de faits, rédaction, vérificateur
- 7.2 Généralisation au rapport d'activité du service (LLM6)
- 7.3 Robustesse à l'injection de prompt indirecte (S1) : données KSC et documents importés

## Chapitre 8 — Protocole expérimental et résultats ⏳
Corpus anonymisé, métriques, évaluateurs, tests statistiques ; réponse à H1–H5 ; limites (taille du corpus,
un seul éditeur de solutions de sécurité, subjectivité des notes).

## Chapitre 9 — Conclusion et perspectives ⏳

## Annexes ⏳
Guide d'installation, schéma de base, grilles d'évaluation, exemples de rapports anonymisés.

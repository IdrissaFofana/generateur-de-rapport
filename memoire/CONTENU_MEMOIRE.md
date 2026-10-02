# Contenu du mémoire (brouillon rédigé au fil du développement)

Texte de travail organisé **selon `PLAN_MEMOIRE.md`, qui fait foi**. En fin de projet, il ne restera que la mise en
forme (gabarit de l'établissement, figures, bibliographie normalisée). Les passages ⏳ indiquent ce qui reste à
produire ; ✅ signale une section dont le critère de fin est rempli.

> Confidentialité : clients désignés Client A, B, C, D ; noms d'appareils et adresses remplacés.

**Structure** : 3 parties de 3 chapitres (voir `PLAN_MEMOIRE.md`).

**Titre** : *Intelligence artificielle pour le reporting de cybersécurité : détection d'anomalies et génération
vérifiable de rapports par un grand modèle de langage (LLM) local dans un service MDR/EDR.*

*En anglais : Artificial Intelligence for Cybersecurity Reporting: Anomaly Detection and Verifiable Report Generation
with a Local Large Language Model (LLM) in an MDR/EDR Service.*

---

## Résumé ⏳
À rédiger en dernier (contexte, problème, approche, résultats chiffrés, conclusion), en français et en anglais.

---

---

## Introduction générale

### Contexte
Les prestataires de services de sécurité managée assurent pour leurs clients la supervision des postes et
serveurs (antivirus et EDR administrés depuis une console centrale, détection et réponse managées — MDR).
Au-delà de la supervision, ils doivent **rendre compte** : chaque mois, chaque client reçoit un rapport qui
présente l'état de protection de son parc, les menaces détectées, les vulnérabilités, les incidents et un plan
d'action. Ce rapport engage le prestataire : il fonde les décisions du client et sert de preuve du service rendu.

Chez ESAY Corporation, partenaire Kaspersky, ces rapports étaient produits à la main à partir de documents PDF
hétérogènes (rapports hebdomadaires du service MDR, exports de la console Kaspersky Security Center transmis
par chaque client). Ce travail est long, répétitif, sujet aux erreurs de recopie, et sa qualité dépend du rédacteur.

### Problématique
Automatiser ce reporting par l'intelligence artificielle soulève trois difficultés :
1. **Détecter** les situations anormales dans des données de supervision peu nombreuses et bruitées, là où des
   seuils fixes échouent (historique court, incidents rares, variations normales entre jours ouvrés et week-end) ;
2. **Rédiger** des textes utiles au client **sans erreur factuelle**, alors que les grands modèles de langage peuvent
   inventer des faits et que les données, confidentielles, ne peuvent pas quitter l'infrastructure : le modèle doit
   être exécuté **en local** ;
3. **Résister aux attaques** : le modèle lit des données dont une partie est contrôlable par un attaquant (noms
   d'appareils, de fichiers, d'objets détectés), ce qui ouvre la voie à l'injection de prompt indirecte.

### Questions de recherche
- **QR1** — Sur des données MDR/EDR peu nombreuses, une détection d'anomalies apprise repère-t-elle mieux qu'un
  seuil fixe les dégradations de la supervision ?
- **QR2** — Un LLM exécuté en local, encadré par un dossier de faits et un vérificateur, rédige-t-il des textes jugés
  au moins aussi utiles que la référence par règles, sans erreur factuelle ?
- **QR3** — Les données de sécurité permettent-elles une injection de prompt indirecte contre le LLM, et les
  protections proposées l'empêchent-elles ?

Hypothèses H1 à H6 : voir `PLAN_MEMOIRE.md`, section 1.

### Contributions ⏳ (à confirmer par les résultats de la partie III)
1. Une détection d'anomalies adaptée aux données rares de supervision MDR/EDR, évaluée par injection d'anomalies
   contre la référence par seuil (chapitres 6 et 7).
2. Une chaîne de génération de rapports par LLM local avec **vérification des faits**, évaluée automatiquement et
   par des experts à l'aveugle (chapitres 6 et 8).
3. Une évaluation de la robustesse à l'injection de prompt indirecte portée par les données de sécurité, et des
   protections associées (chapitres 6 et 9).
4. Une plateforme sécurisée, hébergée en local et en production, qui sert de terrain d'expérimentation (chapitres 4 et 5).

### Organisation du document
- **Partie I — Cadre de l'étude** : contexte, données et problématique (chapitre 1) ; état de l'art sur la
  supervision de sécurité et la détection d'anomalies (chapitre 2), puis sur les LLM, la génération vérifiable et la
  sécurité des LLM (chapitre 3).
- **Partie II — Conception et réalisation** : la plateforme support et sa référence par règles (chapitre 4), sa
  sécurité et son déploiement (chapitre 5), les modules d'intelligence artificielle (chapitre 6).
- **Partie III — Expérimentations et résultats** : détection d'anomalies (chapitre 7), génération vérifiable
  (chapitre 8), robustesse à l'injection de prompt, apport professionnel et discussion (chapitre 9).

---

---

# PARTIE I — CADRE DE L'ÉTUDE

*Introduction de partie ⏳ (½ page) : objectif — situer le problème dans son contexte réel et dans la littérature.*

## Chapitre 1 — Contexte, données et problématique

### 1.1 L'entreprise et le service
ESAY Corporation fournit à ses clients des solutions Kaspersky (protection des terminaux, EDR, service MDR) et
en assure l'administration et le suivi. Le portefeuille étudié compte quatre clients (A à D), tous au profil
« MDR + KSC ».

### 1.2 Les sources de données
| Source | Contenu | Fréquence | Particularités |
|---|---|---|---|
| Rapport hebdomadaire MDR | Postes transmettant leur télémétrie par jour et par tenant, incidents | Hebdomadaire, tous clients | Semaine du lundi au lundi, parution différée ; un même fichier couvre tous les clients (répartition par tenant) |
| Export KSC « État de la protection » | Appareils, état, **raison de l'état**, système, groupe | Mensuel, par client | Transmis par le client ; la raison combine souvent plusieurs causes |
| Export KSC « Menaces » | Détections, catégories, appareils touchés | Mensuel, par client | Détail parfois tronqué par la console |
| Export KSC « Vulnérabilités » | Vulnérabilités par application et gravité | Mensuel, par client | Détail limité à 1 000 lignes ; totaux fiables dans le récapitulatif |

**Limites** : séries courtes (quelques mois), quatre clients, un seul éditeur de solutions de sécurité.

### 1.3 Le processus manuel ⏳ (mesures à faire, critère de fin de H6)
Circuit : collecte des PDF, recopie, graphiques, rédaction, relecture, envoi. À mesurer sur au moins 3 rapports :
temps de production, nombre de corrections à la relecture, délai après la fin du mois.

### 1.4 Besoins et contraintes
- Rapport mensuel par client, à la charte, relu et validé ; suivi des actions d'un mois sur l'autre.
- **Hébergement local** : pas d'accès distant aux consoles des clients ; données confidentielles qui ne doivent pas
  quitter l'infrastructure (contrainte qui impose un LLM local).
- Traçabilité, rôles (lecteur, opérateur, validateur, administrateur), robustesse face aux données manquantes.

### 1.5 Problématique, questions de recherche et hypothèses
Reprise du tableau QR → chapitre → hypothèses de `PLAN_MEMOIRE.md`.

---

## Chapitre 2 — État de l'art : supervision de sécurité et détection d'anomalies ⏳
- 2.1 SOC, services MDR/EDR et reporting de sécurité
- 2.2 Détection d'anomalies : approches statistiques, Isolation Forest, séries temporelles
- 2.3 Données rares et évaluation par injection d'anomalies synthétiques
- 2.4 Synthèse : manque identifié pour QR1

## Chapitre 3 — État de l'art : LLM, génération vérifiable et sécurité des LLM ⏳
- 3.1 Génération de texte à partir de données (data-to-text) et LLM
- 3.2 Hallucinations et vérification des faits
- 3.3 LLM exécutés localement : modèles open-weight, quantification, confidentialité
- 3.4 Sécurité des applications à base de LLM : injection de prompt directe et indirecte, défenses
- 3.5 Positionnement : tableau comparatif

Fiches de lecture : `memoire/LECTURES.md`.

*Conclusion de partie ⏳ (½ page) : les trois manques de la littérature qui fondent QR1 à QR3.*

---

# PARTIE II — CONCEPTION ET RÉALISATION

*Introduction de partie ⏳ (½ page) : la plateforme comme terrain d'expérimentation, sa sécurité, puis les modules
d'IA qui répondent aux questions de recherche.*

## Chapitre 4 — Plateforme support et référence par règles

### 4.1 Architecture et chaîne de traitement
Application web Python (FastAPI) rendue côté serveur (Jinja2) avec interactions légères (HTMX), base
PostgreSQL, génération PDF par WeasyPrint. Les analyses de fichiers lourds s'exécutent dans des **processus
séparés** (lecture PDF non réentrante, serveur web réactif). ⏳ Schéma d'architecture (modèle C4).

**Justifications** : rendu serveur plutôt qu'application monopage — moins de surface d'attaque, pas de
chaîne de construction front, adapté à un outil interne ; WeasyPrint plutôt que Word — rendu reproductible,
versionnable, sans suite bureautique sur le serveur ; hébergement local — imposé par la confidentialité.

Chaîne d'un rapport mensuel :
1. Dépôt des hebdos MDR (une fois pour tous les clients) et des exports KSC (par client) ; empreinte SHA-256
   (dédoublonnage, nom de fichier non contrôlé par l'utilisateur).
2. Analyse en arrière-plan, reconnaissance automatique du type d'export, détection des exports hors période.
3. Consolidation : couverture MDR (jours à venir distingués des jours manquants), protection, menaces,
   vulnérabilités, niveau de risque par règles, plan d'action, suivi des actions du mois précédent.
4. Brouillon, relecture, validation → PDF archivé, version figée ; nouvelle version possible, y compris
   entièrement régénérée (« mettre à jour ») sans toucher à la version validée.

Les données consolidées et les textes d'un rapport sont stockés en JSONB et **figés à la validation** ; le schéma
évolue par migrations Alembic appliquées au démarrage. ⏳ Diagramme entité-association.

### 4.2 La référence par règles (base de comparaison des chapitres 7 et 8)
- **Jours à venir** : un jour n'est compté manquant que si l'hebdo qui le couvre aurait déjà dû paraître
  (lundi suivant + 3 jours).
- **Niveau de risque** : score par points (part d'appareils critiques, appareils sans protection, serveurs
  critiques, détections non neutralisées, vulnérabilités critiques, incidents MDR, couverture MDR).
- **Couverture MDR** : statut calculé sur la part du parc supervisée (≥ 95 % normal, 80 à 95 % à surveiller,
  50 à 80 % élevé, < 50 % critique), et non sur la seule présence de télémétrie. *Cas réel* : un indicateur binaire
  (« au moins un poste ») affichait « Normal » pour Client A à 55 % de couverture ; l'erreur n'a été vue qu'à la
  relecture par un expert — argument pour le vérificateur de faits et les règles de cohérence (6.2).
- **Diagnostic par raison** : la colonne « Raison » de l'export KSC est lue phrase par phrase et rapprochée d'une
  base de règles (16 raisons : cause probable, recommandation, responsable), une forme de système expert. Le rapport
  présente un diagnostic par raison et un classement des appareils par état et par combinaison de raisons ; une
  raison inconnue est signalée telle quelle plutôt qu'ignorée.
- **Alertes par seuils** : hausse des détections de plus de 50 %, serveur critique deux mois de suite, incident
  MDR, niveau critique. Ce sont les **seuils fixes** que le chapitre 7 compare à une détection apprise.
- **Textes par règles** : synthèse, commentaires et conclusion générés par gabarits à partir des chiffres ; ce sont
  les textes de référence du chapitre 8.

### 4.3 Qualité logicielle
**Qualité logicielle** : 46 tests unitaires et 9 suites de bout en bout (237 vérifications) qui pilotent
l'application réelle (vraie base, vrais fichiers PDF). ⏳ Couverture de code.

---

## Chapitre 5 — Sécurité et déploiement de la plateforme 🔄


### 5.1 Modèle de menaces ⏳ (STRIDE)

### 5.2 Authentification forte, sessions et journal d'audit

#### 5.2.1 Authentification et sessions
Menaces visées : usurpation d'identité par force brute ou vol de mot de passe, énumération des comptes,
détournement de session. Mesures :
- **Mots de passe** hachés par scrypt (sel aléatoire, n = 2^14, r = 8, p = 1), longueur minimale 10, mélange
  lettres et chiffres.
- **Force brute** : verrouillage du compte après 5 échecs consécutifs pendant 15 min (état en base) et
  limitation par adresse IP (20 échecs sur une fenêtre glissante de 15 min) ; bannissement réseau par fail2ban.
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
- Validation : tests unitaires (dont les vecteurs officiels de la RFC 6238) et 27 vérifications de bout en bout.
  ⏳ Tableau menace / mesure / test.

#### 5.2.2 Journal d'audit infalsifiable
Un journal modifiable par un administrateur de base de données n'apporte aucune garantie de non-répudiation.
Chaque ligne i porte h(i) = SHA-256( h(i-1) | id | date | acteur | action | détail ), avec h(0) = 64 zéros et un
séparateur absent des données. Toute modification d'une ligne invalide son empreinte ; toute suppression,
insertion ou permutation rompt le lien avec h(i-1). L'écriture est sérialisée par un verrou consultatif
PostgreSQL tenu jusqu'à la validation de la transaction, ce qui garantit une chaîne linéaire malgré les requêtes
concurrentes. L'acteur est figé dans la ligne et la suppression d'un compte ne modifie pas le journal.
**Troncature** : supprimer les dernières lignes reste indétectable par la seule chaîne. Parade : chaque ligne est
répliquée vers un collecteur syslog **après validation** de la transaction, avec son empreinte, et une ancre
quotidienne est émise ; la vérification par ancre détecte alors la troncature. ⏳ Figure de la chaîne.

### 5.3 Déploiement segmenté, durcissement et supervision
La plateforme est déployée en conteneurs répartis sur des réseaux distincts (schéma et matrice des flux :
`deploiement/LISEZMOI.md`). Seul le mandataire inverse Nginx publie des ports (443, et 80 redirigé). La base de
données, **le LLM** et la supervision sont placés sur des réseaux **internes**, sans aucune route vers l'extérieur :
une compromission de ces composants ne permet ni d'y accéder depuis le réseau, ni d'exfiltrer des données — c'est
aussi ce qui garantit qu'aucune donnée client ne sort vers un service d'IA externe. Chaque conteneur applique le
moindre privilège : système de fichiers en lecture seule, utilisateur non privilégié, capacités Linux retirées,
interdiction d'élévation de privilèges, limites de ressources.
Le proxy termine TLS (1.2 et 1.3 uniquement), ajoute les en-têtes de sécurité (HSTS, CSP, anti-cadrage) et limite
le débit sur la page de connexion. Il **remplace** l'en-tête X-Forwarded-For, et l'application n'accepte cet en-tête
que depuis l'adresse fixe du proxy : sans cela, soit tous les clients partageraient l'adresse du proxy (la
limitation par IP bloquerait tout le monde), soit un attaquant pourrait choisir l'adresse vue par l'application.
Serveur : SSH par clé uniquement, pare-feu nftables en refus par défaut, fail2ban, service systemd durci.
Supervision : métriques Prometheus (disponibilité, erreurs, latence par modèle de route, état métier, intégrité du
journal) et règles d'alerte. Limite : la CSP autorise encore les scripts en ligne des gabarits.

### 5.4 Évaluation de la sécurité (avant / après)
| Mesure | Avant | Après |
|---|---|---|
| bandit (analyse statique) — haute / moyenne / basse | 1 / 5 / 2 | 0 / 0 / 0 |
| pip-audit (dépendances vulnérables connues) | 0 | 0 |
| Vérification du déploiement (20 contrôles) | ⏳ | ⏳ |
| Lynis (indice de durcissement) | ⏳ | ⏳ |
| systemd-analyze security ou Docker Bench | ⏳ | ⏳ |
| testssl.sh | ⏳ | ⏳ |
| OWASP ZAP | ⏳ | ⏳ |

Analyse des 8 alertes bandit : aucune vulnérabilité réelle (4 faux positifs XSS — données échappées avant marquage
sûr —, un hachage SHA-1 utilisé comme clé de cache, un appel réseau et deux appels de processus sans risque).
*Enseignement* : un outil d'analyse statique sans lecture humaine produit ici 100 % d'alertes sans risque réel.

## Chapitre 6 — Conception des modules d'intelligence artificielle ⏳
- 6.1 Module de détection d'anomalies : caractéristiques, score statistique robuste, Isolation Forest, intégration
- 6.2 Chaîne de génération vérifiable : dossier de faits → LLM local → vérificateur de faits et règles de cohérence
  → correction, régénération ou repli sur les textes par règles
- 6.3 Protections contre l'injection de prompt : isolement des champs non fiables, sortie structurée, vérification
- 6.4 Choix et déploiement du modèle local (deux modèles open-weight comparés)

*Conclusion de partie ⏳ (½ page) : ce qui est construit et ce qu'il reste à démontrer.*

---

# PARTIE III — EXPÉRIMENTATIONS ET RÉSULTATS

*Introduction de partie ⏳ (½ page) : une question de recherche par chapitre, chaque fois contre la référence par
règles du chapitre 4.*

## Chapitre 7 — Évaluation de la détection d'anomalies ⏳ (QR1, H1)
- 7.1 Données et corpus : séries réelles et anomalies injectées
- 7.2 Protocole et métriques : précision, rappel, F1, délai de détection, fausses alertes
- 7.3 Résultats : seuil fixe, méthode statistique et Isolation Forest comparés ; épisodes réels
- 7.4 Discussion et test de H1

## Chapitre 8 — Évaluation de la génération vérifiable de rapports ⏳ (QR2, H2 à H4)
- 8.1 Corpus anonymisé et 3 versions par rapport (règles / LLM seul / LLM + vérification)
- 8.2 Métriques automatiques : exactitude factuelle, taux d'hallucination, couverture des points clés
- 8.3 Évaluation humaine à l'aveugle : 3 experts, accord inter-évaluateurs, test de Wilcoxon
- 8.4 Résultats, analyse des erreurs, test de H2 à H4

## Chapitre 9 — Robustesse à l'injection de prompt, apport professionnel et discussion ⏳ (QR3, H5, H6)
- 9.1 Jeu d'attaques et résultats sans / avec protections ; test de H5
- 9.2 Apport professionnel : temps de production avant / après ; test de H6
- 9.3 Synthèse des réponses à QR1 à QR3
- 9.4 Limites et menaces à la validité

*Conclusion de partie ⏳ (½ page).*

---

## Conclusion générale et perspectives ⏳
Perspectives : suggestion d'actions par similarité entre interventions (référence Jaccard déjà en place),
priorisation des appareils, génération du rapport d'activité du service, collecte automatique des exports,
chiffrement au repos. Prolongement doctoral : robustesse et vérifiabilité des LLM appliqués à l'analyse de données
de sécurité.

---

---

## Annexes
### A. Installation et déploiement
Voir `INSTALLATION.md` et `deploiement/LISEZMOI.md`.

### B. Fonctions de la plateforme hors sujet de recherche (≤ 3 pages)
- **Pilotage** : vue d'ensemble du portefeuille, suivi du parc, contrats et licences, alertes.
- **Service technique** : assistance mensuelle planifiée et rapprochée des rapports d'intervention ; rapports
  d'intervention assistés par une bibliothèque de 105 actions ; import d'anciens rapports (PDF, Word) avec
  reconnaissance du client, mise en attente des clients inconnus et détection des doublons probables (similarité
  de Jaccard : 0,99 pour un même rapport en Word et en PDF, 0,12 pour deux rapports différents) ; base de
  connaissances ; fiches des techniciens ; rapport d'activité du service.
- **Interface** : choix de conception (hiérarchie, typographie, couleurs validées pour la lisibilité et le
  daltonisme). ⏳ Captures.

### C. Grilles d'évaluation ⏳ · D. Exemples de rapports anonymisés ⏳ · E. Consignes (prompts) ⏳ · F. Jeu d'attaques ⏳

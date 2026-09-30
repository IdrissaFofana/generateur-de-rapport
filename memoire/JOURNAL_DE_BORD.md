# Journal de bord du projet

Historique daté du développement : ce qui a été fait, les décisions prises (et les alternatives écartées),
les problèmes rencontrés et les mesures obtenues. Sert de matière première au mémoire.

> Les clients sont désignés Client A, B, C, D. Correspondance conservée hors du dépôt.

---

## Avant le 28/09/2026 — Situation initiale

- Rapports mensuels produits **à la main** sous Word à partir des PDF Kaspersky (rapports hebdomadaires MDR,
  exports KSC transmis par chaque client), puis scripts Python de génération de documents Word.
- Première version de la plateforme web (FastAPI, Jinja2, HTMX, PostgreSQL, WeasyPrint) : dépôt des fichiers,
  analyse en arrière-plan, brouillon, relecture, validation, PDF, rôles, CSRF.
- À mesurer pour le mémoire : temps de production d'un rapport manuel (référence « avant »).

## 28/09/2026 — Refonte de l'interface

- **Constat** : interface générique (barre bleue, tableaux à en-tête plein, pastilles partout), sans hiérarchie ;
  les chiffres clés noyés dans des listes.
- **Décisions** : direction « salle de contrôle éditoriale » ; barre latérale ; typographies Schibsted Grotesk
  (texte) et IBM Plex Mono (chiffres) hébergées localement (plateforme sans dépendance externe) ; motif de
  l'hexagone du logo comme fil conducteur (états, chronologie) ; couleurs de la charte (marine #00507A,
  cyan #0099BA, vert #8DC21F).
- Vérification visuelle par captures (Chrome sans fenêtre) ; tests de bout en bout conservés.

## 28/09/2026 — Mise en production et transfert des données

- Script d'export SQL portable (`outils_dev/exporter_sql.py`) : `TRUNCATE` puis `INSERT`, transaction unique,
  réalignement des séquences ; archive des PDF déposés.
- **Problème** : chemins de fichiers enregistrés avec `\` sous Windows → convertis en `/` à l'export
  (corrigé ensuite à la source, voir 29/09).
- Rejoué sur une base d'essai avant livraison.

## 29/09/2026 — Migrations de schéma (Alembic)

- **Décision** : Alembic plutôt que des scripts SQL manuels. Migration de départ générée par comparaison avec
  une base vide ; une base existante sans suivi est **marquée** au niveau initial sans perte de données ;
  migrations appliquées automatiquement au démarrage.
- Migrations : 0001 schéma initial, 0002 index du journal, 0003 normalisation des chemins (migration de
  données). **Piège rencontré** : `LIKE '%\%'` — l'antislash est un caractère d'échappement de `LIKE` → `strpos`.

## 29/09/2026 — Règles métier et production

- **Fin de mois** : un hebdo MDR couvre une semaine du lundi au lundi et paraît quelques jours après ; les jours
  dont l'hebdo ne peut pas encore exister sont « à venir » et non « manquants » (disponible le lundi suivant
  + 3 jours). Effet : un client complet passe de « Partiel » à « Prêt ».
- Actions groupées (création et actualisation des brouillons, ZIP des PDF validés), journal filtrable et paginé
  avec export CSV.

## 29/09/2026 — Évolution multi-mois et bilans

- Historique des rapports **validés** figé dans chaque rapport ; petites courbes SVG (web) et petits multiples
  matplotlib (PDF).
- **Choix de couleur** validé par un outil de contrôle (lisibilité, daltonisme) : la marine de la charte se lit
  comme du gris pour une courbe → cyan #0099BA.
- Bilans trimestriels et semestriels consolidés à partir des mensuels validés (totaux, tendances, incidents,
  menaces cumulées, bilan des actions).

## 29/09/2026 — Pilotage

- Vue d'ensemble (accueil) : indicateurs du portefeuille avec écart, carte de chaleur client × mois, tendances,
  classement, applications vulnérables communes, couverture MDR (postes hors supervision), suivi des actions
  (ancienneté ≥ 2 mois, répartition prestataire / client / partagée), menaces par catégorie et leur évolution,
  délai de production par rapport ; filtres mois / client / profil.
- **Décision de visualisation** : les catégories de menaces ont des ordres de grandeur très différents
  (≈ 1 750 contre ≈ 30) → petits multiples à échelles séparées plutôt qu'un graphique multi-séries.
- Suivi du parc appareil par appareil (anomalies récurrentes, fins de support Microsoft), contrats et licences
  (dépassement, sous-utilisation, échéances), alertes (niveau critique, hausse des détections, incident MDR,
  serveur critique deux mois de suite, licences) avec notifications e-mail / Teams et résumé hebdomadaire.
- Migration 0004.

## 29-30/09/2026 — Rapports d'intervention

- Analyse du modèle Word existant : structure utile mais incohérences (titres), contexte non chiffré, points
  bloquants sans action corrective ni responsable, pas de numéro.
- Numérotation `RI-AAAA-CODE-NNN`, titre selon le type, contexte pré-rempli depuis le dernier export KSC,
  bibliothèque de 105 actions et recommandations (terminologie Kaspersky) filtrée par type, enrichissable,
  envoi par e-mail ou brouillon Outlook, historique chronologique, reprise facultative des points bloquants
  dans le plan d'action. Migration 0005.

## Mesures disponibles à ce stade

| Mesure | Valeur |
|---|---|
| Suites de tests de bout en bout | 6 (socle, dépôts, rapports, bilans, pilotage, interventions) |
| Vérifications automatiques | 147, toutes réussies |
| Migrations de schéma | 5 |

## 30/09/2026 — Orientation mémoire

- Mémoire de master professionnel avec contribution de type recherche ; autorisation d'ESAY obtenue.
- Quatre axes retenus : LLM, apprentissage automatique, sécurité, systèmes et réseaux (voir `AXES.md`).
- **Décision** : développer toutes les fonctionnalités avant la rédaction, en tenant ce journal et le contenu
  du mémoire à jour au fil de l'eau.
- Démarrage de la **phase 1 — socle sécurisé** (S2, S3, tests unitaires).

## 30/09/2026 — Phase 1 : socle sécurisé (S2, S3, tests) ✅

**Authentification (S2)**
- Verrouillage d'un compte après 5 échecs consécutifs pendant 15 minutes (compteur en base) et limitation par
  adresse IP (20 échecs / 15 min, fenêtre glissante en mémoire : un seul processus web).
- **Message d'erreur unique** (« identifiants incorrects, ou trop de tentatives ») : ne révèle ni l'existence du
  compte ni son verrouillage (énumération). Le mot de passe est vérifié même pour un compte inconnu, contre une
  empreinte « leurre » calculée une fois : **même coût scrypt** dans tous les cas (attaque par mesure du temps).
  *Erreur corrigée en cours de route* : la première version recalculait une empreinte pour les comptes inconnus,
  soit deux fois plus lent, écart mesurable.
- **Double authentification TOTP** implémentée sans bibliothèque (RFC 6238 / 4226, SHA-1, 6 chiffres, 30 s,
  tolérance ± 1 pas) ; QR code SVG local (segno) ; secret gardé en session tant que l'utilisateur n'a pas prouvé
  l'avoir enregistré ; **refus du rejeu** (dernier pas accepté mémorisé) ; connexion en deux étapes avec délai de
  5 min ; réinitialisation par un administrateur (téléphone perdu) ; obligation configurable par rôle.
- **Version de session** : incrémentée au changement de mot de passe, à l'activation / désactivation de la 2FA,
  à la réinitialisation par un administrateur, à la désactivation ou au changement de rôle : les sessions ouvertes
  ailleurs sont fermées.
- Déconnexion par formulaire POST avec jeton CSRF (un lien GET ne déconnecte plus : protection contre la
  déconnexion forcée depuis un autre site).
- *Défaut découvert par les tests* : visiter une page protégée pendant l'étape du code **vidait la session**
  (connexion en attente et jeton CSRF perdus). Correction : la session n'est vidée que si elle contenait un compte
  devenu invalide.

**Journal d'audit infalsifiable (S3)**
- Chaque ligne stocke l'empreinte de la précédente et sa propre empreinte SHA-256 calculée sur
  (précédente, identifiant, horodatage à la microseconde, acteur, action, détail), champs séparés par le caractère
  0x1F. Écriture sérialisée par un **verrou consultatif PostgreSQL** transactionnel (pg_advisory_xact_lock).
- Acteur (e-mail) figé dans la ligne ; clé étrangère vers l'utilisateur en ON DELETE SET NULL : supprimer un
  compte ne touche pas au journal. Conséquence : les scripts de test ne suppriment plus les lignes du journal
  (une suppression est précisément ce que la chaîne détecte).
- Vérification : gerer.py verifier-journal et bandeau sur la page Journal ; détecte modification, suppression,
  insertion et réordonnancement. **Limite** : la suppression des *dernières* lignes n'est détectable qu'avec une
  empreinte « ancre » conservée hors de la base (prévu en R3 : envoi vers syslog / SIEM).
- Migration 0006 : reprise de l'existant (acteur renseigné, lignes existantes chaînées).

**Tests**
- Mise en place de pytest (tests/, pytest.ini, requirements-dev.txt) : 25 tests unitaires, dont les
  **6 vecteurs officiels de la RFC 6238** (conformité de l'implémentation TOTP), rejeu, tolérance d'horloge,
  détection de falsification du journal, limiteur à horloge simulée, verrouillage, règles métier.
- Nouvelle suite de bout en bout essai_securite : 27 vérifications (verrouillage, message uniforme, invalidation
  de sessions, 2FA complète, rejeu, 2FA obligatoire, déconnexion, intégrité du journal).

**Mesures**

| Mesure | Valeur |
|---|---|
| Tests unitaires (pytest) | 25 / 25 |
| Suites de bout en bout | 7, 174 vérifications, toutes réussies |
| Journal après l'ensemble des tests | 110 lignes, chaîne intacte |
| Migrations de schéma | 6 |

## 30/09/2026 — Service technique et import d'anciens rapports ✅

**Besoin exprimé** : suivre une assistance au moins mensuelle par client, classer l'activité par client et par
technicien, produire un rapport d'activité du service (mensuel à annuel), gérer le parcours et les certifications
des techniciens, et importer les anciens rapports d'intervention pour constituer un historique exploitable.

**Décisions**
- L'assistance mensuelle est un attribut du client (avec date de début) ; chaque mois, une assistance « à planifier »
  est **créée automatiquement** (à l'affichage du planning et par la tâche quotidienne des alertes). États : à planifier,
  planifiée, réalisée, reportée (justification obligatoire, par un validateur), et « en retard » calculé.
- Une assistance devient **réalisée** dès qu'un rapport d'intervention validé du mois la couvre (type assistance ou
  maintenance, ou rapport rédigé depuis le planning). *Alternative écartée* : cocher « réalisée » à la main — non
  vérifiable ; le lien au rapport fournit la preuve.
- Heures calculées à partir des heures de passage (arrivée, départ, nombre de jours) : sert aux classements, pas à
  la facturation.
- Techniciens = utilisateurs de la plateforme. Justificatifs de certification stockés (PDF, PNG, JPEG, 10 Mo),
  contrôlés par extension **et signature binaire** ; accès limité au titulaire, aux validateurs et aux administrateurs.
- Rapport d'activité du service : sections calculées + textes relus, même cycle que les autres rapports
  (brouillon, validation, PDF archivé, versions). Remplace le rapport semestriel produit à la main.
- Import : lecture PDF (PyMuPDF) et Word (python-docx) ; extraction par indices (client connu le plus cité, dates
  « du … au … », heures, type d'après le titre, sections numérotées, puces). Chaque import passe par une
  **vérification humaine** avant d'être compté ; le document d'origine est conservé et fait foi ; doublons refusés
  par empreinte SHA-256.
- Nouvelles alertes : assistance non réalisée (à partir du 20 du mois, puis mois écoulé) et certification expirant
  sous 60 jours.

**Problèmes rencontrés**
- PDF : les puces sont extraites seules sur leur ligne et le texte d'une puce peut se poursuivre sur la ligne suivante
  (y compris après un saut de page, avec en-tête et pied de page intercalés) → recollage des puces, continuation tant
  que la puce ne se termine pas par une ponctuation, filtrage des lignes en majuscules. Résultat : les 8 actions du
  rapport réel sont extraites à l'identique.
- Regroupement des problèmes récurrents : « Port (135, 445, 139) fermé » et « Ports 135 445 139 fermés » n'étaient
  pas regroupés (signature exacte). Remplacé par une **racinisation légère** et une **similarité de Jaccard ≥ 0,6**
  (regroupement glouton). Base du futur ML4.
- Lecteur d'import sur 3 documents réels : modèle « R-I » (tous les champs trouvés), rapport global de migration
  en PDF et en Word (client, type, objet trouvés ; dates approximatives → vérification humaine).

**Mesures**

| Mesure | Valeur |
|---|---|
| Tests unitaires (pytest) | 32 / 32 |
| Suites de bout en bout | 8 — 209 vérifications, toutes réussies (dont essai_service : 35) |
| Journal après l'ensemble des tests | 271 lignes, chaîne intacte |
| Migrations de schéma | 7 |

## 30/09/2026 — Restructuration du mémoire

- Titre élargi : *Plateforme locale et sécurisée de pilotage d'un service de sécurité managée…* ; deux volets
  professionnels (A : reporting client, B : service technique).
- ML4 (interventions similaires et suggestion d'actions) devient une **contribution secondaire** avec son
  hypothèse H5 ; il passe en phase 4 avec ML1, ML2 devient optionnel.
- Nouveaux éléments : LLM6 (généralisation au rapport du service), S1 étendu aux documents importés, S7 (fichiers
  déposés et données personnelles).
- Règles contre la dispersion adoptées : une seule question principale ; sans métrique, pas de place aux
  chapitres 6 et 7.
- Limite relevée à l'import : un rapport d'un client **non enregistré** est refusé (sans client par défaut) ou
  rattaché au client par défaut choisi — risque de mauvais rattachement si le client par défaut est utilisé pour un
  lot mêlant plusieurs clients.

## 30/09/2026 — Import : clients non enregistrés et autres noms ✅

- **Autres noms** du client (sigle, nom complet, ancien nom) utilisés pour la reconnaissance, en plus du nom et des
  tenants MDR. Migration 0008.
- **Reconnaissance tolérante** : casse, accents et ponctuation entre les mots ignorés (« PAC CI » ≈ « pac-ci » ≈
  « PACCI »), toujours par mot entier (« HUDSON » ne reconnaît pas « hudsonville »).
- **Nom écrit dans le document** extrait (« Client : … » ou cellule « Client | … »), en ignorant les modèles vierges
  (« ...... »).
- **Imports en attente de client** : un rapport non reconnu n'est plus refusé ni rattaché d'office ; il est conservé
  avec le nom détecté jusqu'à ce qu'on le **rattache** à un client existant (option « retenir ce nom » → ajouté aux
  autres noms du client) ou qu'un administrateur **crée le client** (formulaire pré-rempli). À l'enregistrement d'un
  client, tous les imports en attente sont réanalysés et rattachés automatiquement s'ils sont reconnus.
- **Décision** : le client choisi à la main n'est appliqué qu'à un **fichier seul** ; dans un lot, il est ignoré.
  *Motif* : un choix global sur un lot mêlant plusieurs clients produisait des rattachements erronés, silencieux
  (cas constaté pendant les tests de la version précédente).
- *Défaut découvert par une capture d'écran* : le style des cases de la carte de chaleur (Vue d'ensemble) portait
  sur la classe générique `.case`, également utilisée par toutes les cases à cocher des formulaires, dont il masquait
  le libellé. Style limité à la carte de chaleur et à sa légende.

| Mesure | Valeur |
|---|---|
| Tests unitaires (pytest) | 41 / 41 |
| Suites de bout en bout | 8 — 216 vérifications, toutes réussies (essai_service : 42) |
| Migrations de schéma | 8 |

## 30/09/2026 — Import : doublons probables ✅

**Problème** : le contrôle par empreinte SHA-256 ne reconnaît que des fichiers identiques octet pour octet. Le même
rapport en Word puis en PDF, un PDF réexporté ou l'ancien PDF d'une intervention déjà saisie passaient sans alerte
et gonflaient les statistiques (et fausseraient le corpus de ML4).

**Solution** : détection de **doublon probable** sur le contenu, parmi les interventions du même client.
- Similarité de Jaccard sur les mots significatifs (racinisation légère) : du contenu structuré (objet + actions)
  et, lorsque les deux textes intégraux existent, du texte complet ; on retient la plus forte.
- Seuils : **0,6** si les dates sont à 7 jours ou moins (ou inconnues) ; **0,85** au-delà (seul un réexport quasi
  identique est alors signalé). *Motif* : deux assistances mensuelles de mois consécutifs se ressemblent (0,71) sans
  être des doublons.
- **Décision de l'utilisateur** : un doublon probable n'est ni refusé ni importé ; il est mis en attente avec le
  rapport auquel il ressemble et le score, et l'utilisateur choisit **« Importer quand même »** ou **« Annuler
  l'import »** (fichier supprimé). Le contrôle s'applique aussi quand un import en attente de client est rattaché.

**Mesures sur documents réels**

| Paire comparée | Similarité | Résultat |
|---|---|---|
| Même rapport de migration, Word et PDF | 0,99 | doublon signalé |
| Rapport de migration et rapport de déploiement (clients différents) | 0,12 | — |
| Rapport importé et même contenu saisi (sans texte intégral) | 1,00 | doublon signalé |
| Deux assistances mensuelles de mois consécutifs (dates éloignées) | 0,71 | non signalé (< 0,85) |

Tests : 43 unitaires ; 8 suites, 220 vérifications (essai_service : 46). Migration 0009.

## 30/09/2026 — Modale de confirmation ✅

- Les 26 confirmations avant action (suppressions, validations, envois, réinitialisations, import) utilisaient la boîte
  native du navigateur (`confirm()`), hors charte et impossible à mettre en forme. Remplacées par une **modale** unique
  (élément `<dialog>` natif : focus piégé, touche Échap, fond assombri) déclenchée par un attribut déclaratif
  `data-confirmer="message"` sur le formulaire ou le bouton ; aucun `console.log` dans le code du projet.
- Ergonomie : variante « Action irréversible » (rouge) pour les suppressions et réinitialisations, avec le **focus
  sur « Annuler »** (une validation au clavier ne détruit rien) ; libellé du bouton repris du verbe de l'action
  (« Supprimer », « Valider », « Envoyer »…).
- Vérifié dans Chrome sans fenêtre sur une page d'essai : annuler (rien n'est envoyé), confirmer (envoi), bouton avec
  sa propre action (`formaction` conservée), aucune erreur JavaScript. *Écueils rencontrés* : l'envoi intercepté
  restait visible des autres scripts (→ arrêt de sa propagation) ; l'événement de fermeture de la modale se déclenche
  mal en navigation automatisée (→ réaction directe au clic sur les boutons, plus robuste).
- Un test de bout en bout supposait l'absence de client « KSC seul » ; un client réel de ce profil ayant été créé,
  le test compte désormais les clients concernés au lieu de présumer la composition du portefeuille.

## 30/09/2026 — Couverture MDR : un indicateur trompeur corrigé ✅

**Constat (relevé par l'utilisateur sur un rapport réel)** : Client A affichait « Postes supervisés par le MDR :
25,4 — **Normal** » alors que 27 appareils au plus sur 49 transmettaient leur télémétrie (55,1 %). Le statut ne
vérifiait que la présence d'au moins un poste ; le niveau de risque ne pénalisait que l'absence totale de télémétrie.
Le plan d'action proposait pourtant déjà « Étendre la supervision MDR » sous 80 % : incohérence entre sections.

**Correction** : une règle unique `couverture_mdr` (maximum supervisé / appareils administrés), utilisée par le
tableau des indicateurs (PDF et Word), le texte de la section MDR et le calcul du risque.

| Couverture | Statut | Effet sur le risque |
|---|---|---|
| ≥ 95 % | Normal | — |
| 80 à 95 % | À surveiller | — |
| 50 à 80 % | Élevé | +1 point, motif affiché |
| < 50 % ou aucun poste | Critique | +2 points, motif affiché |
| parc KSC inconnu (pas d'export) | Non mesurée | — |

- Nouvelle ligne « Couverture MDR du parc » (27 / 49, 55,1 %) ; le texte nomme les appareils hors supervision et les
  causes à vérifier (déploiement de l'agent, licences, appareils disparus encore présents dans la console).
- *Choix* : sans export KSC, afficher « Normal » serait une affirmation non vérifiée → « Non mesurée ».
- Client A : risque 10 → 11 points (reste Critique), motif « 22 appareils sur 49 hors de la supervision MDR ».
- Portée : statuts et tableau recalculés à l'affichage (brouillons et nouveaux PDF) ; textes d'un brouillon existant
  mis à jour par « Régénérer les textes » ; rapports déjà validés inchangés (PDF archivé).
- **Enseignement pour le mémoire** : un indicateur binaire (« au moins un poste ») masque une dégradation partielle ;
  l'erreur n'a été détectée que par la relecture d'un expert — argument en faveur du vérificateur de faits (axe 1)
  et de règles de cohérence entre sections.

## 30/09/2026 — Raisons d'état KSC : diagnostic, recommandations et classement ✅

**Besoin** : l'export « État de la protection » fourni par le client contient, pour chaque appareil, une colonne
**Raison** (ex. « L'appareil n'est plus administré. L'appareil ne s'est pas connecté au Serveur d'administration
depuis longtemps ») et un « état défini par l'application » (ex. « Serveurs de KSN indisponibles »). Le rapport n'en
tirait qu'un comptage par anomalie.

**Réalisation**
- **Lecture phrase par phrase** de la raison (16 raisons reconnues au lieu de 10 : licence, applications
  incompatibles, menaces non traitées, chiffrement, espace disque…). Une phrase inconnue n'est plus ignorée : elle
  devient « autre » et son texte exact est affiché dans le rapport. Les raisons sont réanalysées à chaque
  consolidation : une amélioration du lecteur profite aux exports déjà déposés.
- **Base de diagnostic** : pour chaque raison, cause probable, recommandation opérationnelle (terminologie
  Kaspersky : Agent d'administration, klmover, proxy KSN, stratégie verrouillée…) et responsable.
- Rapport, section « État de la protection » : **3.1 Diagnostic par raison et recommandations** (raison, appareils
  critiques / avertissement / serveurs, impact, cause, recommandation, responsable) ; **3.2 Appareils par état et par
  raison** (groupes état × combinaison de raisons, avec les noms des appareils : un groupe = une action) ; annexe
  triée par état puis par gravité de la raison. Même contenu dans l'export Word.
- **Plan d'action** : actions ajoutées pour les raisons jusque-là sans action ; noms des appareils cités quand ils
  sont cinq au plus.
- Vérification : lecture identique à l'ancienne sur les 49 appareils réels de Client A (0 différence) ; 46 tests
  unitaires, 8 suites de bout en bout.

**Mesure (Client A, septembre)** : 5 raisons distinctes, 7 groupes état × raison ; la raison la plus fréquente (KSN
inaccessible) touche 34 appareils dont 11 serveurs — une seule action réseau traite 69 % du parc en anomalie.

**Intérêt pour le mémoire** : c'est une forme de **système expert** (base de règles cause → recommandation) ; elle
fournit (1) une référence de base pour la génération de recommandations par LLM (axe 1) et (2) les « faits » que le
vérificateur devra retrouver dans le texte généré.

## 30/09/2026 — Mise à jour des rapports déjà validés ✅

- **Besoin** : des rapports ont été validés avant les dernières améliorations (diagnostic par raison, couverture
  MDR) ; « Nouvelle version » recalculait les chiffres mais recopiait les textes et le plan d'action de la version
  validée, sans les nouvelles recommandations.
- **Solution** : bouton **« Mettre à jour »** sur un rapport ou un bilan validé (validateurs) : nouvelle version en
  brouillon **entièrement régénérée** (chiffres, textes, plan d'action) ; la version validée et son PDF restent
  archivés (principe d'immuabilité des documents envoyés). « Nouvelle version (garder mes textes) » reste disponible.
  Action groupée sur la page Production : « Mettre à jour les rapports validés » du mois. Bandeau sur un rapport
  validé produit avant les améliorations.
- **Défaut de test découvert** : le nettoyage de `essai_rapports` supprimait *tous* les rapports d'un client réel
  (et non ceux créés par le test) ; sans conséquence (aucun rapport réel en base locale), corrigé : suppression
  limitée aux rapports créés par les comptes d'essai.
- **Observation à traiter** : écart de 2 h entre les horodatages posés par PostgreSQL (`now()`, fuseau du serveur de
  base) et ceux posés par l'application (`datetime.now()`) : fuseaux horaires à aligner (serveur en UTC+0).
- Tests : essai_rapports 23 vérifications (+5).

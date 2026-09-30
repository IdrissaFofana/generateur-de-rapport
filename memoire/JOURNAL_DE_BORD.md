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

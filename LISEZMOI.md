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
```

## Organisation du code

```
app/
  moteur/      lecture des PDF (hebdos MDR, exports KSC), analyse, textes par défaut
  rendu/       rapport HTML/CSS -> PDF (WeasyPrint), graphiques, export Word
  web/         pages : connexion, tableau de bord, dépôts, relecture, administration
  templates/   gabarits des pages     static/   style, logo, polices, htmx
  modeles.py   tables PostgreSQL       services.py   données d'un client pour un mois, cycle des rapports
  analyses.py  analyse des fichiers en arrière-plan (processus séparés)
gerer.py       commandes : init, creer-admin, importer-clients
```

Voir **INSTALLATION.md** pour le déploiement sur le serveur.

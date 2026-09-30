# Installation sur le serveur Linux

Application Python (FastAPI) servie par **uvicorn** sur `127.0.0.1`, derrière **Nginx**.
Base **PostgreSQL**. Le PDF est produit par **WeasyPrint** (aucune suite bureautique nécessaire).

## 1. Dépendances système

WeasyPrint a besoin de Pango.

```bash
# Debian / Ubuntu
sudo apt install python3 python3-venv libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
# RHEL / Rocky / Alma
sudo dnf install python3 pango
```

La police du rapport (Carlito) est fournie avec l'application : rien à installer.

## 2. Application

```bash
sudo mkdir -p /srv/rapports-esay && sudo chown $USER /srv/rapports-esay
# copier le contenu du dossier « plateforme » dans /srv/rapports-esay
# (inutile de copier : outils_dev/, exemples/, donnees/, app/moteur/.cache/, __pycache__/)
cd /srv/rapports-esay
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Base de données

```bash
sudo -u postgres psql -c "CREATE DATABASE rapports_esay ENCODING 'UTF8' TEMPLATE template0;"
```

Utilisez de préférence un utilisateur PostgreSQL dédié plutôt que `postgres`.

## 4. Configuration : fichier `.env`

Partir de `.env.example` :

```ini
DATABASE_URL="postgresql://UTILISATEUR:MOT_DE_PASSE@localhost:5432/rapports_esay?schema=public"
PORT=8010
SECRET_KEY="<générer : python3 -c 'import secrets; print(secrets.token_urlsafe(48))'>"
STOCKAGE_DIR="/srv/rapports-esay/donnees"
COOKIE_SECURISE=1          # si la plateforme est servie en HTTPS (recommandé)
TAILLE_MAX_DEPOT_MO=50
```

Protéger le fichier : `chmod 600 .env`.

## 5. Premier démarrage

```bash
.venv/bin/python gerer.py init
.venv/bin/python gerer.py creer-admin prenom.nom@esay.ci "Prénom Nom"   # affiche un mot de passe provisoire
```

Les clients se créent ensuite dans l'interface (menu **Clients**).

## 6. Service systemd

`/etc/systemd/system/rapports-esay.service` :

```ini
[Unit]
Description=Rapports de sécurité ESAY
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/srv/rapports-esay
ExecStart=/srv/rapports-esay/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --workers 1 --proxy-headers
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

> **Un seul worker uvicorn** (`--workers 1`) : les analyses de fichiers tournent dans des processus
> d'arrière-plan gérés par l'application ; plusieurs workers les lanceraient en double.

```bash
sudo chown -R www-data /srv/rapports-esay/donnees
sudo systemctl daemon-reload && sudo systemctl enable --now rapports-esay
```

### Tâches planifiées : alertes quotidiennes et résumé hebdomadaire

`/etc/systemd/system/rapports-esay-alertes.service` et `.timer` (chaque jour à 7 h) :

```ini
# rapports-esay-alertes.service
[Unit]
Description=Rapports ESAY : évaluation des alertes
[Service]
Type=oneshot
User=www-data
WorkingDirectory=/srv/rapports-esay
ExecStart=/srv/rapports-esay/.venv/bin/python gerer.py alertes

# rapports-esay-alertes.timer
[Unit]
Description=Rapports ESAY : alertes chaque jour
[Timer]
OnCalendar=*-*-* 07:00
Persistent=true
[Install]
WantedBy=timers.target
```

Même principe pour le résumé du lundi : `rapports-esay-resume.service` avec
`ExecStart=… gerer.py resume-hebdo` et un timer `OnCalendar=Mon *-*-* 08:00`.
Le résumé n'est envoyé qu'une fois par semaine, même si la tâche est relancée.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rapports-esay-alertes.timer rapports-esay-resume.timer
systemctl list-timers | grep rapports     # prochaine exécution
```

### Notifications (facultatif)

Dans `.env` (voir `.env.example`) : `SMTP_HOTE`, `SMTP_PORT`, `SMTP_SECURITE`, `SMTP_UTILISATEUR`, `SMTP_MOT_DE_PASSE`,
`SMTP_EXPEDITEUR`, `ALERTES_EMAILS`, `RESUME_EMAILS`, et `URL_PLATEFORME` pour les liens des messages.
Teams : `TEAMS_WEBHOOK` = URL d'un workflow Teams « Lorsqu'une requête webhook est reçue » (le serveur doit pouvoir
sortir sur internet). Vérifier ensuite dans la page **Alertes** → « Envoyer un message d'essai ».

## 7. Nginx

```nginx
server {
    listen 443 ssl;
    server_name rapports.esay.local;
    # ssl_certificate ... ; ssl_certificate_key ... ;

    client_max_body_size 60M;          # dépôt de gros exports KSC

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;       # génération d'un PDF
    }
}
```

## 8. Sauvegardes

Deux éléments à sauvegarder ensemble :

- la base : `pg_dump rapports_esay > rapports_esay_$(date +%F).sql`
- le dossier `STOCKAGE_DIR` (fichiers déposés et PDF validés)

## 9. Mise à jour de l'application

Remplacer les fichiers (sans toucher à `.env` ni à `donnees/`), puis :

```bash
.venv/bin/pip install -r requirements.txt
sudo systemctl restart rapports-esay
```

Les **migrations de la base sont appliquées automatiquement au démarrage** (Alembic, dossier `migrations/`) :
aucune commande SQL à passer. Pour les appliquer ou vérifier sans redémarrer :

```bash
.venv/bin/python gerer.py init              # applique les migrations en attente
.venv/bin/python -m alembic current         # révision actuelle de la base
```

Comme toujours, sauvegarder la base avant une mise à jour (voir § 8).

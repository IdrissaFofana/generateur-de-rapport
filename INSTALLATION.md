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

Les tables sont créées automatiquement au démarrage. En cas de changement de structure d'une
table existante, une instruction de migration sera fournie avec la mise à jour.

# Image de l'application « Rapports de sécurité ESAY » (axe R1 du mémoire).
# Principes : image minimale, utilisateur non privilégié, code en lecture seule, données sur un volume dédié.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Bibliothèques de rendu PDF (WeasyPrint : Pango, HarfBuzz) ; aucun outil de compilation conservé
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
 && rm -rf /var/lib/apt/lists/*

# Utilisateur système dédié, sans shell ni répertoire personnel accessible en écriture
RUN groupadd --system --gid 10001 rapports \
 && useradd --system --uid 10001 --gid rapports --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin rapports

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code appartenant à root : le processus (utilisateur « rapports ») ne peut pas le modifier
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini gerer.py ./
RUN mkdir -p /donnees && chown rapports:rapports /donnees

USER rapports
ENV STOCKAGE_DIR=/donnees \
    CACHE_KSC_DIR=/donnees/.cache-ksc \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp \
    PORT=8010 \
    COOKIE_SECURISE=1
EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/connexion', timeout=4).status == 200 else 1)"

# --proxy-headers : l'adresse IP réelle du client (limitation des tentatives) vient de X-Forwarded-For,
# accepté uniquement depuis le proxy (FORWARDED_ALLOW_IPS = adresse fixe du conteneur Nginx).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8010 --workers 1 --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-172.30.10.10}\" --no-server-header"]

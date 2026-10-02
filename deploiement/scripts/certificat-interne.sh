#!/bin/sh
# Certificat TLS auto-signé pour un premier démarrage ou un essai (à remplacer par un certificat de l'autorité
# interne de l'entreprise). Usage : sh deploiement/scripts/certificat-interne.sh rapports.esay.local
set -eu
NOM="${1:-rapports.esay.local}"
DOSSIER="$(dirname "$0")/../certificats"
mkdir -p "$DOSSIER"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 825 \
  -subj "/O=ESAY Corporation/CN=$NOM" -addext "subjectAltName=DNS:$NOM" \
  -keyout "$DOSSIER/rapports.key" -out "$DOSSIER/rapports.crt"
chmod 600 "$DOSSIER/rapports.key"
echo "Certificat créé pour $NOM dans $DOSSIER (valable 825 jours)."

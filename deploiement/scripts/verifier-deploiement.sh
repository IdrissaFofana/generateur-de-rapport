#!/bin/sh
# Vérification « boîte noire » du déploiement segmenté (axes R1 / R4). À lancer sur le serveur, à la racine du projet.
# Usage : sh deploiement/scripts/verifier-deploiement.sh [https://rapports.esay.local]
# Chaque contrôle affiche OK ou ÉCHEC ; code de sortie = nombre d'échecs.
URL="${1:-https://127.0.0.1}"
ECHECS=0
ok()    { echo "  OK     $1"; }
echec() { echo "  ÉCHEC  $1"; ECHECS=$((ECHECS + 1)); }
teste() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else echec "$1"; fi; }
teste_non() { if eval "$2" >/dev/null 2>&1; then echec "$1"; else ok "$1"; fi; }
DC="docker compose --env-file deploiement/.env"

echo "== Exposition réseau"
teste     "le proxy répond en HTTPS"                         "curl -skf -o /dev/null $URL/connexion"
teste     "HTTP redirigé vers HTTPS (301)"                   "curl -s -o /dev/null -w '%{http_code}' http://${URL#https://}/ | grep -q 301"
teste_non "PostgreSQL non joignable depuis l'hôte (5432)"    "nc -z -w 2 127.0.0.1 5432"
teste_non "application non joignable directement (8010)"     "nc -z -w 2 127.0.0.1 8010"
teste_non "modèle de langage non joignable (11434)"          "nc -z -w 2 127.0.0.1 11434"
teste     "/metrics non exposé par le proxy (404)"           "curl -sk -o /dev/null -w '%{http_code}' $URL/metrics | grep -q 404"

echo "== TLS"
teste_non "TLS 1.0 refusé"                                   "echo | openssl s_client -connect ${URL#https://}:443 -tls1 2>/dev/null | grep -q 'Cipher is'"
teste_non "TLS 1.1 refusé"                                   "echo | openssl s_client -connect ${URL#https://}:443 -tls1_1 2>/dev/null | grep -q 'Cipher is'"
teste     "TLS 1.3 accepté"                                  "echo | openssl s_client -connect ${URL#https://}:443 -tls1_3 2>/dev/null | grep -q 'TLSv1.3'"

echo "== En-têtes de sécurité"
EN_TETES="$(curl -skI $URL/connexion)"
for h in Strict-Transport-Security Content-Security-Policy X-Content-Type-Options X-Frame-Options Referrer-Policy; do
  teste "en-tête $h présent" "echo \"\$EN_TETES\" | grep -qi '^$h:'"
done
teste_non "version du serveur masquée"                       "echo \"\$EN_TETES\" | grep -qi '^server:.*[0-9]'"

echo "== Isolement des conteneurs"
teste     "application exécutée sans privilèges (uid ≠ 0)"   "[ \"\$($DC exec -T app id -u)\" != 0 ]"
teste_non "système de fichiers de l'application en lecture seule" "$DC exec -T app sh -c 'touch /app/essai'"
teste     "volume de données accessible en écriture"         "$DC exec -T app sh -c 'touch /donnees/.essai && rm /donnees/.essai'"
teste_non "la base n'a aucune sortie réseau"                 "$DC exec -T db sh -c 'wget -q -T 3 -O /dev/null http://example.com'"
teste     "l'application joint la base"                      "$DC exec -T app python -c \"import socket; socket.create_connection(('db', 5432), 3)\""

echo "== Journal d'audit"
teste     "chaîne d'empreintes intacte"                      "$DC exec -T app python gerer.py verifier-journal"

echo
[ "$ECHECS" -eq 0 ] && echo "Tous les contrôles sont réussis." || echo "$ECHECS contrôle(s) en échec."
exit "$ECHECS"

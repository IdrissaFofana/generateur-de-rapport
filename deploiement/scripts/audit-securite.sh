#!/bin/sh
# Mesures d'audit pour le mémoire (axes R4 et S6), à lancer AVANT puis APRÈS durcissement.
# Les résultats sont rangés dans audits/<date>-<étiquette>/ pour comparaison.
# Usage : sudo sh deploiement/scripts/audit-securite.sh avant   |   sudo sh deploiement/scripts/audit-securite.sh apres
# Outils : lynis (apt install lynis), testssl.sh (facultatif), docker (facultatif), python3 -m pip install bandit pip-audit
set -u
ETIQUETTE="${1:-mesure}"
URL="${2:-https://127.0.0.1}"
DOSSIER="audits/$(date +%Y%m%d-%H%M)-$ETIQUETTE"
mkdir -p "$DOSSIER"
echo "Résultats dans $DOSSIER"

# 1. Système : Lynis (indice de durcissement 0-100)
if command -v lynis >/dev/null; then
  lynis audit system --quick --no-colors > "$DOSSIER/lynis.txt" 2>&1
  grep -i "hardening index" "$DOSSIER/lynis.txt" | tee "$DOSSIER/resume.txt"
fi

# 2. Service systemd (déploiement sans conteneurs) : exposition 0 (sûr) à 10 (exposé)
if systemctl list-unit-files rapports-esay.service >/dev/null 2>&1; then
  systemd-analyze security rapports-esay.service --no-pager > "$DOSSIER/systemd-analyze.txt" 2>&1
  tail -1 "$DOSSIER/systemd-analyze.txt" | tee -a "$DOSSIER/resume.txt"
fi

# 3. Conteneurs : Docker Bench for Security
if command -v docker >/dev/null; then
  docker run --rm --net host --pid host --userns host --cap-add audit_control \
    -v /etc:/etc:ro -v /var/lib:/var/lib:ro -v /var/run/docker.sock:/var/run/docker.sock:ro \
    docker/docker-bench-security > "$DOSSIER/docker-bench.txt" 2>&1
  grep -E "^\[INFO\] Checks|Score" "$DOSSIER/docker-bench.txt" | tee -a "$DOSSIER/resume.txt"
fi

# 4. TLS : testssl.sh
if command -v testssl.sh >/dev/null; then
  testssl.sh --quiet --color 0 "$URL" > "$DOSSIER/testssl.txt" 2>&1
  grep -E "Overall Grade|Grade cap" "$DOSSIER/testssl.txt" | tee -a "$DOSSIER/resume.txt"
fi

# 5. Code : analyse statique (bandit) et dépendances vulnérables (pip-audit)
if python3 -m bandit --version >/dev/null 2>&1; then
  python3 -m bandit -r app -q -f txt > "$DOSSIER/bandit.txt" 2>&1
  grep -E "Total issues|High:|Medium:" "$DOSSIER/bandit.txt" | tee -a "$DOSSIER/resume.txt"
fi
if python3 -m pip_audit --version >/dev/null 2>&1; then
  python3 -m pip_audit -r requirements.txt > "$DOSSIER/pip-audit.txt" 2>&1
  tail -3 "$DOSSIER/pip-audit.txt" | tee -a "$DOSSIER/resume.txt"
fi

# 6. Vérification fonctionnelle du déploiement segmenté
sh "$(dirname "$0")/verifier-deploiement.sh" "$URL" > "$DOSSIER/verification.txt" 2>&1
tail -1 "$DOSSIER/verification.txt" | tee -a "$DOSSIER/resume.txt"
echo "Terminé. Résumé : $DOSSIER/resume.txt"

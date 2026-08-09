#!/usr/bin/env bash
#
# sync-to-kimsufi.sh — RÉPLICATION Dedibox (principal) → Kimsufi (secours).
# À exécuter SUR LE DEDIBOX (sudo). En une commande :
#   1. Upgrade du code sur le Kimsufi (son propre upgrade.sh, adapté à SON CPU)
#   2. Copie des fichiers runtime : .env, firebase-admin.json, proxies.json, storm_data.json
#   3. Réplication MongoDB (dump → restore, collections remplacées)
#   4. Restart + sonde santé du service Kimsufi
#
# PRÉREQUIS (une seule fois) — clé SSH du Dedibox vers le Kimsufi :
#   sudo ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519   # si pas déjà fait
#   sudo ssh-copy-id root@<IP_KIMSUFI>
#
# USAGE :
#   sudo bash sync-to-kimsufi.sh              # tout (code + fichiers + base)
#   sudo bash sync-to-kimsufi.sh --db-only    # base Mongo uniquement (pour cron horaire)
#   sudo bash sync-to-kimsufi.sh --files-only # fichiers runtime uniquement
#
# CRON HORAIRE OPTIONNEL (base à ≤ 1 h près sur le secours) :
#   echo '15 * * * * root bash /opt/storm-monitor/scripts/sync-to-kimsufi.sh --db-only >> /var/log/storm-sync.log 2>&1' > /etc/cron.d/storm-sync
#
set -euo pipefail

# ------------------------- CONFIG (à ajuster) --------------------------------
KIMSUFI_HOST="${KIMSUFI_HOST:-5.135.160.56}"   # IP ou hostname du Kimsufi (ns3020148.ip-5-135-160.eu)
KIMSUFI_USER="${KIMSUFI_USER:-root}"
APP_DIR="/var/www/storm-monitor"
REMOTE_APP_DIR="/var/www/storm-monitor"
REMOTE_WORK_DIR="/opt/storm-monitor"
SSH_OPTS="-o ConnectTimeout=15 -o BatchMode=yes"
# -----------------------------------------------------------------------------

MODE="full"
[[ "${1:-}" == "--db-only" ]] && MODE="db"
[[ "${1:-}" == "--files-only" ]] && MODE="files"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: sudo requis (sudo bash sync-to-kimsufi.sh)" >&2
  exit 1
fi

R="$KIMSUFI_USER@$KIMSUFI_HOST"
DB_NAME="$(grep -m1 '^DB_NAME=' "$APP_DIR/backend/.env" | cut -d= -f2- | tr -d '"' )"
if [[ -z "$DB_NAME" ]]; then
  echo "ERROR: DB_NAME introuvable dans $APP_DIR/backend/.env" >&2
  exit 1
fi

echo "==> Réplication Dedibox → Kimsufi ($R) · mode=$MODE · base=$DB_NAME"

if ! ssh $SSH_OPTS "$R" "echo ok" >/dev/null 2>&1; then
  echo "ERROR: connexion SSH vers $R impossible." >&2
  echo "       Installe la clé : sudo ssh-copy-id $R" >&2
  exit 1
fi

if [[ "$MODE" == "full" ]]; then
  echo "==> [1/4] Upgrade du code sur le Kimsufi (adapté à SON processeur)..."
  ssh $SSH_OPTS "$R" "bash $REMOTE_WORK_DIR/upgrade.sh --with-deps" || {
    echo "ERROR: upgrade.sh a échoué sur le Kimsufi — réplication interrompue (le secours reste sur son ancienne version fonctionnelle)." >&2
    exit 1
  }
fi

if [[ "$MODE" == "full" || "$MODE" == "files" ]]; then
  echo "==> [2/4] Copie des fichiers runtime..."
  for f in .env firebase-admin.json proxies.json storm_data.json; do
    if [[ -f "$APP_DIR/backend/$f" ]]; then
      scp $SSH_OPTS -q "$APP_DIR/backend/$f" "$R:$REMOTE_APP_DIR/backend/$f"
      echo "    ✓ $f"
    else
      echo "    ( $f absent en local — ignoré )"
    fi
  done
fi

if [[ "$MODE" == "full" || "$MODE" == "db" ]]; then
  echo "==> [3/4] Réplication MongoDB ($DB_NAME) — dump → restore (--drop)..."
  mongodump --db "$DB_NAME" --archive 2>/dev/null | \
    ssh $SSH_OPTS "$R" "mongorestore --archive --drop --nsInclude='$DB_NAME.*'" \
    >/dev/null 2>&1 || {
      echo "ERROR: réplication Mongo échouée." >&2
      exit 1
    }
  echo "    ✓ Base répliquée"
fi

if [[ "$MODE" != "db" ]]; then
  echo "==> [4/4] Restart + sonde santé sur le Kimsufi..."
  ssh $SSH_OPTS "$R" '
    systemctl restart storm-monitor
    PORT="$(grep -oP -- "--port \K[0-9]+" /etc/systemd/system/storm-monitor.service 2>/dev/null | head -1)"
    PORT="${PORT:-8001}"
    for i in $(seq 1 12); do
      sleep 2
      curl -fsS -m 4 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1 && { echo "    ✓ Kimsufi : /api/health répond"; exit 0; }
    done
    echo "ERROR: le Kimsufi ne répond pas sur /api/health après restart" >&2
    tail -n 15 /var/log/storm-monitor.err.log >&2 || true
    exit 1
  '
fi

echo "==> Réplication terminée — le Kimsufi est prêt à prendre le relais."

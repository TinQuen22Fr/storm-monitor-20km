#!/usr/bin/env bash
#
# Storm Monitor — installation script for Kimsufi (Ubuntu/Debian)
# Usage:  bash install.sh
#
# Note Kimsufi/OVH : la machine est déjà root par défaut — pas de `sudo` requis.
#
# Architecture deux étages (depuis 2026-06-19) :
#   /opt/storm-monitor       (WORK_DIR)  — Clone Git, source of truth pour pull
#   /var/www/storm-monitor   (APP_DIR)   — Runtime : venv, build, .env, data
#
# What it does (idempotent, sûr à relancer) :
#   1. Installe Python 3.11+, Node.js 20, Yarn, MongoDB, Nginx 1.30+
#   2. Clone le repo dans /opt/storm-monitor (ou pull si déjà présent)
#   3. Synchronise /opt → /var/www en PRÉSERVANT : .env, venv/, cache/,
#      storm_data.json, frontend/build/ (rebuildés ensuite)
#   4. Met à jour le venv Python (pip install -r requirements.txt)
#   5. Génère /var/www/storm-monitor/backend/.env si manquant (premier install)
#      OU ajoute les variables manquantes à un .env existant (mise à jour)
#   6. Rebuild le frontend
#   7. Écrit le vhost Nginx + le service systemd
#   8. Restart everything
#
# Branche cible (FIGÉE) : Version_With_Detector
#   C'est la seule branche supportée en production sur le Kimsufi.
#
# SSL/HTTPS (Certbot) est volontairement NON installé — voir DEPLOY.md.

set -euo pipefail

REPO_URL="https://github.com/TinQuen22Fr/storm-monitor-20km.git"
# Branche cible figée — Version_With_Detector est LA branche prod du Kimsufi.
BRANCH="Version_With_Detector"

# Architecture deux étages :
#   WORK_DIR  = clone Git, où l'utilisateur fait ses git pull (source of truth)
#   APP_DIR   = répertoire d'exécution (venv, frontend/build, .env, storm_data.json)
#               Le script synchronise WORK_DIR → APP_DIR sans toucher aux runtime
#               files (.env, venv/, cache/, *.json), pour qu'une mise à jour ne
#               casse rien.
WORK_DIR="/opt/storm-monitor"
APP_DIR="/var/www/storm-monitor"
DOMAIN="storm-monitor.quentin-astro.fr"
BACKEND_PORT="8003"
RUN_USER="root"

# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: privilèges root requis." >&2
  echo "       Kimsufi (root direct) : bash install.sh" >&2
  echo "       Dedibox (compte quentin) : sudo bash install.sh" >&2
  exit 1
fi

if ! id "$RUN_USER" &>/dev/null; then
  echo "ERROR: user '$RUN_USER' does not exist on this system" >&2
  exit 1
fi

echo "==> Storm Monitor — installation on $(hostname)"
echo "    Domain   : $DOMAIN"
echo "    Work dir : $WORK_DIR  (git source of truth)"
echo "    App dir  : $APP_DIR   (runtime)"
echo "    Backend  : 127.0.0.1:$BACKEND_PORT"
echo "    Branch   : $BRANCH"

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
echo "==> Installing system packages..."
export DEBIAN_FRONTEND=noninteractive

# Clean any broken/stale MongoDB repo entries from previous attempts
# (MongoDB 7.0 has no release for Ubuntu Noble — this would block apt update)
rm -f /etc/apt/sources.list.d/mongodb-org-7.0.list
rm -f /etc/apt/sources.list.d/mongodb-org-7.0.list.save
rm -f /usr/share/keyrings/mongodb-server-7.0.gpg

apt-get update -y
apt-get install -y \
    git curl ca-certificates gnupg2 lsb-release ubuntu-keyring \
    build-essential ffmpeg \
    python3 python3-venv python3-pip python3-dev \
    fonts-dejavu

# ---------------------------------------------------------------------------
# Nginx — install from the official nginx.org stable repo.
# Ubuntu's own nginx package is frozen on old versions (1.24) which lack the
# modern `http2 on;` directive and HTTP/3 support. The upstream repo ships
# 1.30+ which is the recommended baseline for this app.
# ---------------------------------------------------------------------------
if ! command -v nginx >/dev/null || ! nginx -v 2>&1 | grep -qE 'nginx/1\.(2[6-9]|[3-9][0-9])'; then
  echo "==> Installing nginx from nginx.org (stable)..."
  # Purge any pre-existing Ubuntu-distributed nginx (< 1.26) to avoid conflicts
  apt-get purge -y 'nginx*' || true
  apt-get autoremove -y || true

  # Signing key
  curl -fsSL https://nginx.org/keys/nginx_signing.key | \
      gpg --dearmor -o /usr/share/keyrings/nginx-archive-keyring.gpg

  # Stable channel for current Ubuntu codename
  CODENAME="$(lsb_release -cs)"
  echo "deb [signed-by=/usr/share/keyrings/nginx-archive-keyring.gpg] http://nginx.org/packages/ubuntu ${CODENAME} nginx" \
      > /etc/apt/sources.list.d/nginx.list

  # Pin upstream over distro packages
  cat > /etc/apt/preferences.d/99nginx <<'EOF'
Package: *
Pin: origin nginx.org
Pin: origin packages.nginx.org
Pin-Priority: 900
EOF

  apt-get update -y
  apt-get install -y nginx
fi

# The nginx.org package ships a minimal nginx.conf that only loads
# /etc/nginx/conf.d/*.conf. Ensure sites-enabled/ is also loaded so the
# Debian-style vhost layout keeps working.
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/snippets
if ! grep -q "sites-enabled" /etc/nginx/nginx.conf; then
  sed -i '/include \/etc\/nginx\/conf.d\/\*.conf;/a\    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
fi

# Node.js — on GARDE le node existant s'il est >= 18 (ex: v26.5.0 déjà en place
# sur le Kimsufi, prouvé fonctionnel sur l'Atom). JAMAIS de downgrade forcé.
# On n'installe Node 20 QUE si node est absent ou < 18.
NODE_OK=0
if command -v node >/dev/null; then
  NV="$(node -v 2>/dev/null || echo v0)"; NM="${NV#v}"; NM="${NM%%.*}"
  [[ "$NM" =~ ^[0-9]+$ ]] && (( NM >= 18 )) && NODE_OK=1 && echo "==> Node.js $NV déjà présent — conservé tel quel"
fi
if [[ $NODE_OK -eq 0 ]]; then
  echo "==> Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

# Yarn
if ! command -v yarn >/dev/null; then
  npm install -g yarn
fi

# MongoDB — version selected based on CPU AVX support.
# - AVX present → MongoDB 8.0 (latest stable)
# - AVX missing → MongoDB 4.4 (last release without AVX requirement)
# Old Atom CPUs typical of low-cost Kimsufi do NOT have AVX → MongoDB 8 crashes
# at startup with "Illegal instruction (core dumped)". 4.4 is the fallback.
HAS_AVX=0
if grep -qo '\bavx\b' /proc/cpuinfo 2>/dev/null; then
  HAS_AVX=1
fi

# ---------------------------------------------------------------------------
# curl with HTTP/3 support (via snap)
# ---------------------------------------------------------------------------
# Ubuntu/Debian ship libcurl WITHOUT HTTP/3 support, so `curl --http3` fails
# with "the installed libcurl version doesn't support this".
# We install a recent curl from snap and expose it as `curl3` (system-wide
# symlink) plus a profile.d alias `curl` for interactive root shells.
# /usr/bin/curl stays untouched so system scripts/cron keep working.
if ! command -v snap >/dev/null; then
  apt-get install -y snapd
fi
if ! snap list curl >/dev/null 2>&1; then
  echo "==> Installing curl with HTTP/3 support via snap..."
  snap install curl || echo "    WARN: snap install curl failed — HTTP/3 testing CLI won't be available"
fi
# Acknowledge the snap-curl banner once (silences it on every call)
if [[ -x /snap/bin/curl.snap-acked ]]; then
  /snap/bin/curl.snap-acked >/dev/null 2>&1 || true
fi
# System-wide `curl3` shortcut: works for scripts and humans.
# IMPORTANT: must be a wrapper script, NOT a symlink — snap launchers in
# /snap/bin/* dispatch based on argv[0], so renaming via symlink would make
# snap think `curl3` is a different app and fail with "unknown flag".
if [[ -x /snap/bin/curl ]]; then
  cat > /usr/local/bin/curl3 <<'EOF'
#!/usr/bin/env bash
# Storm Monitoring — wrapper that forwards to the snap curl (HTTP/3 capable).
exec /snap/bin/curl "$@"
EOF
  chmod +x /usr/local/bin/curl3
fi
# Make plain `curl` resolve to the snap build in interactive root shells.
if [[ -d /etc/profile.d ]] && [[ ! -f /etc/profile.d/storm-monitor-curl3.sh ]]; then
  cat > /etc/profile.d/storm-monitor-curl3.sh <<'EOF'
# Storm Monitoring — alias `curl` to the snap build (HTTP/3 support).
# Drop this file to undo: rm /etc/profile.d/storm-monitor-curl3.sh
if [ -x /snap/bin/curl ]; then
  alias curl='/snap/bin/curl'
fi
EOF
fi

if ! command -v mongod >/dev/null; then
  CODENAME="$(lsb_release -sc)"
  # Strip stale repo entries (any older version installed previously)
  rm -f /etc/apt/sources.list.d/mongodb-org-*.list
  rm -f /usr/share/keyrings/mongodb-server-*.gpg

  if [[ $HAS_AVX -eq 1 ]]; then
    echo "==> CPU has AVX → installing MongoDB 8.0..."
    curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
        gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
    echo "deb [signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg] https://repo.mongodb.org/apt/ubuntu ${CODENAME}/mongodb-org/8.0 multiverse" \
        > /etc/apt/sources.list.d/mongodb-org-8.0.list
  else
    echo "==> CPU has NO AVX → falling back to MongoDB 4.4 (last AVX-free release)"
    # 4.4 has packages for Focal (20.04). They run fine on Noble/Jammy too —
    # MongoDB 4.4 is a self-contained server, not affected by libssl3.
    curl -fsSL https://www.mongodb.org/static/pgp/server-4.4.asc | \
        gpg -o /usr/share/keyrings/mongodb-server-4.4.gpg --dearmor
    echo "deb [signed-by=/usr/share/keyrings/mongodb-server-4.4.gpg] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/4.4 multiverse" \
        > /etc/apt/sources.list.d/mongodb-org-4.4.list
    # Hostide install: MongoDB 4.4 needs libssl1.1 which Noble doesn't ship.
    # On Noble we install the focal libssl1.1 package directly.
    if [[ "$CODENAME" == "noble" || "$CODENAME" == "bookworm" ]]; then
      if ! ldconfig -p | grep -q 'libssl.so.1.1'; then
        echo "    Installing libssl1.1 from focal-security (required by mongo 4.4)..."
        TMPDEB="/tmp/libssl1.1.deb"
        curl -fsSL -o "$TMPDEB" \
          http://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_$(dpkg --print-architecture).deb || \
          curl -fsSL -o "$TMPDEB" \
          http://launchpadlibrarian.net/648013231/libssl1.1_1.1.1f-1ubuntu2.20_$(dpkg --print-architecture).deb
        dpkg -i "$TMPDEB" || apt-get install -fy
        rm -f "$TMPDEB"
      fi
    fi
  fi
  apt-get update -y
  apt-get install -y mongodb-org
fi
# Ensure mongo dirs are owned by the mongodb user (the package is supposed to
# do this but a manual `mkdir` before the install can leave them root-owned,
# making mongod crash with "Failed to open /var/log/mongodb/mongod.log").
if id mongodb &>/dev/null; then
  mkdir -p /var/lib/mongodb /var/log/mongodb
  chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb
fi
systemctl enable --now mongod

# ---------------------------------------------------------------------------
# 2. Repository — clone into WORK_DIR=/opt, then sync to APP_DIR=/var/www
# ---------------------------------------------------------------------------
mkdir -p /opt /var/www

# --- 2a. WORK_DIR: clone OR pull ---
# Dedibox : si le clone /opt a été fait par l'utilisateur (ex: quentin) et que
# le script tourne en sudo/root, git refuse d'opérer ("dubious ownership").
if ! git config --global --get-all safe.directory 2>/dev/null | grep -qx "$WORK_DIR"; then
  git config --global --add safe.directory "$WORK_DIR"
fi
if [[ -d "$WORK_DIR/.git" ]]; then
  echo "==> Existing clone detected at $WORK_DIR — pulling latest..."

  CURRENT_BRANCH="$(git -C "$WORK_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
  CURRENT_COMMIT="$(git -C "$WORK_DIR" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
  echo "    Branch   : $CURRENT_BRANCH"
  echo "    Commit   : $CURRENT_COMMIT"

  # Discard local runtime junk that should never be tracked (cache pickles, etc.)
  rm -f "$WORK_DIR/backend/.stale_cache.pkl"

  # Stash other uncommitted changes
  STASH_CREATED=0
  if ! git -C "$WORK_DIR" diff --quiet || ! git -C "$WORK_DIR" diff --cached --quiet; then
    echo "    Local changes detected — stashing..."
    if git -C "$WORK_DIR" -c user.name="install.sh" -c user.email="install@storm-monitor.local" stash push -u -m "install.sh auto-stash $(date -u +%FT%TZ)" >/dev/null 2>&1; then
      STASH_CREATED=1
    fi
  fi

  git -C "$WORK_DIR" remote set-url origin "$REPO_URL"
  git -C "$WORK_DIR" fetch --prune origin

  if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    echo "==> Switching branch: $CURRENT_BRANCH → $BRANCH"
    git -C "$WORK_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
  else
    if ! git -C "$WORK_DIR" pull --ff-only origin "$BRANCH"; then
      echo "    Fast-forward failed — forcing reset to origin/$BRANCH"
      git -C "$WORK_DIR" reset --hard "origin/$BRANCH"
    fi
  fi

  NEW_COMMIT="$(git -C "$WORK_DIR" rev-parse --short HEAD)"
  if [[ "$CURRENT_COMMIT" == "$NEW_COMMIT" ]]; then
    echo "    Already up-to-date at $NEW_COMMIT"
  else
    echo "    Updated $CURRENT_COMMIT → $NEW_COMMIT"
    git -C "$WORK_DIR" log --pretty=format:'      - %h %s' "$CURRENT_COMMIT..$NEW_COMMIT" 2>/dev/null | head -20 || true
    echo ""
  fi

  if [[ $STASH_CREATED -eq 1 ]]; then
    if ! git -C "$WORK_DIR" stash pop >/dev/null 2>&1; then
      echo "    WARN: conflits au stash pop — abandon des modifs locales (reset origin/$BRANCH)"
      git -C "$WORK_DIR" reset --hard "origin/$BRANCH"
      git -C "$WORK_DIR" stash drop >/dev/null 2>&1 || true
    fi
  fi

  # Si install.sh lui-même a changé dans ce pull, on RELANCE immédiatement la
  # nouvelle version : bash lit le script au fil de l'exécution — continuer
  # avec l'ancienne version en mémoire après un pull = comportement imprévisible.
  if [[ "${STORM_INSTALL_REEXEC:-0}" != "1" && "$CURRENT_COMMIT" != "$NEW_COMMIT" ]]; then
    if git -C "$WORK_DIR" diff --name-only "$CURRENT_COMMIT" "$NEW_COMMIT" 2>/dev/null | grep -qx 'install.sh'; then
      echo "    install.sh mis à jour dans ce pull — relance avec la NOUVELLE version..."
      exec env STORM_INSTALL_REEXEC=1 bash "$WORK_DIR/install.sh" "$@"
    fi
  fi
else
  if [[ -d "$WORK_DIR" ]]; then
    echo "==> $WORK_DIR exists but is not a git repo. Removing..."
    rm -rf "$WORK_DIR"
  fi
  echo "==> First install — cloning '$BRANCH' into $WORK_DIR..."
  git clone -b "$BRANCH" "$REPO_URL" "$WORK_DIR"
fi

# Sanity check
if [[ ! -d "$WORK_DIR/backend" || ! -d "$WORK_DIR/frontend" ]]; then
  echo "ERROR: $WORK_DIR does not contain backend/ and frontend/ — bad branch?" >&2
  exit 1
fi

# --- 2b. Sync WORK_DIR → APP_DIR (preserve runtime files) ---
echo "==> Syncing $WORK_DIR → $APP_DIR (preserving .env, venv, data)..."
mkdir -p "$APP_DIR"
# Install rsync if missing
command -v rsync >/dev/null || apt-get install -y rsync

# Files/dirs we MUST NOT overwrite when syncing:
#   - backend/.env              (secrets, regenerated only on first install)
#   - backend/venv/             (Python virtual env, expensive to rebuild)
#   - backend/storm_data.json   (live data uploaded by detector)
#   - backend/.stale_cache.pkl  (runtime cache)
#   - frontend/build/           (rebuilt explicitly below)
#   - frontend/node_modules/    (regenerated by yarn install)
#   - cache/                    (video export TTL cache)
#   - .git                      (APP_DIR has no .git, source is in WORK_DIR)
rsync -a --delete \
  --exclude='.git' \
  --exclude='backend/.env' \
  --exclude='backend/.env.backups' \
  --exclude='backend/venv' \
  --exclude='backend/storm_data.json' \
  --exclude='backend/firebase-admin.json' \
  --exclude='backend/.stale_cache.pkl' \
  --exclude='backend/cache' \
  --exclude='backend/__pycache__' \
  --exclude='backend/**/__pycache__' \
  --exclude='frontend/build' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/.env' \
  --exclude='cache' \
  "$WORK_DIR/" "$APP_DIR/"

chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

# Bulk forecast cache directory (severe.py grid_bulk.json — 80 points × 48h)
# Must be writable by the service user without root. Mode 755 is enough.
BULK_CACHE_DIR="$APP_DIR/backend/cache"
mkdir -p "$BULK_CACHE_DIR"
chown -R "$RUN_USER":"$RUN_USER" "$BULK_CACHE_DIR"
chmod 755 "$BULK_CACHE_DIR"

# Video export cache directory (Pillow frames + MP4 output, TTL 24h)
VIDEO_CACHE_DIR="$APP_DIR/cache/videos"
mkdir -p "$VIDEO_CACHE_DIR"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR/cache"

# ---------------------------------------------------------------------------
# 3. Backend — Python venv, dependencies, .env
# ---------------------------------------------------------------------------
echo "==> Setting up backend..."

# --- Sélection de l'interpréteur Python pour le venv -----------------------
# Les versions pinnées (éprouvées sur le Kimsufi Atom) ont des wheels
# cp311/cp312 UNIQUEMENT. Python 3.13/3.14 : pas de wheel pour pydantic-core
# 2.16.3 / pymongo 4.5 / pillow 10.4 → compilation source vouée à l'échec
# (PyO3 de cette génération ne supporte pas ces ABI). On impose 3.11 ou 3.12.
select_python() {
  local cand ver
  for cand in python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      ver="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0)"
      case "$ver" in
        3.11|3.12) command -v "$cand"; return 0 ;;
      esac
    fi
  done
  return 1
}
PYTHON_BIN="$(select_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "==> Aucun Python 3.11/3.12 trouvé — tentative d'installation apt..."
  apt-get install -y python3.12 python3.12-venv python3.12-dev >/dev/null 2>&1 || \
    apt-get install -y python3.11 python3.11-venv python3.11-dev >/dev/null 2>&1 || true
  PYTHON_BIN="$(select_python || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: Python 3.11 ou 3.12 requis pour le venv (le python3 système est $(python3 --version 2>/dev/null))." >&2
  echo "       Les dépendances pinnées n'ont pas de wheels pour Python >= 3.13." >&2
  echo "       Installe python3.12 (paquet distro, ou deadsnakes PPA sur Ubuntu) puis relance." >&2
  exit 1
fi
echo "    Venv Python : $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

cd "$APP_DIR/backend"
# Un venv existant créé avec un python incompatible (ex: 3.14) est recréé.
if [[ -x venv/bin/python ]]; then
  VENV_VER="$(venv/bin/python -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0)"
  case "$VENV_VER" in
    3.11|3.12) : ;;
    *)
      echo "    venv existant en Python $VENV_VER (incompatible) — recréation avec $PYTHON_BIN"
      rm -rf venv
      ;;
  esac
fi
if [ ! -d venv ]; then
  "$PYTHON_BIN" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install --prefer-binary -r requirements.txt
deactivate
cd -

# Generate .env only if missing
ENV_FILE="$APP_DIR/backend/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Generating $ENV_FILE with fresh secrets..."
  cd "$APP_DIR/backend"
  # shellcheck disable=SC1091
  source venv/bin/activate
  python3 - <<'PY' > .env
import secrets
from py_vapid import Vapid01
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import base64

v = Vapid01()
v.generate_keys()
pub_raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
public_b64 = base64.urlsafe_b64encode(pub_raw).decode().rstrip('=')
private_pem = v.private_pem().decode().replace('\n', '\\n')

print('MONGO_URL="mongodb://localhost:27017"')
print('DB_NAME="storm_lourdes"')
print('CORS_ORIGINS="*"')
print(f'JWT_SECRET="{secrets.token_urlsafe(48)}"')
print(f'UPLOAD_API_KEY="lourdes-{secrets.token_urlsafe(32)}"')
print('VAPID_SUBJECT="mailto:quentin@quentin-astro.fr"')
print(f'VAPID_PUBLIC_KEY="{public_b64}"')
print(f'VAPID_PRIVATE_KEY_PEM="{private_pem}"')
print('STORM_DATA_FILE="/var/www/storm-monitor/backend/storm_data.json"')
# --- Webhooks (optional — fill to enable Discord / Telegram notifications) ---
print('DISCORD_WEBHOOK_URL=""')
print('TELEGRAM_BOT_TOKEN=""')
print('TELEGRAM_CHAT_ID=""')
print('WEBHOOK_APP_URL="https://storm-monitor.quentin-astro.fr"')
print('WEBHOOK_COOLDOWN_S="900"')
# --- Email service (Resend) — REMPLIR APRES INSTALL ---
print('RESEND_API_KEY=""')
print('SENDER_EMAIL="Storm Monitoring <noreply@quentin-astro.fr>"')
print('PUBLIC_APP_URL="https://storm-monitor.quentin-astro.fr"')
print('ADMIN_EMAIL=""')
# --- Xweather (Vaisala) — fallback météo si Open-Meteo est en panne/429 ---
# Format : "<client_id>_<client_secret>" (token combiné, splitté au runtime)
print('XWEATHER_COMBINED_TOKEN=""')
PY
  chmod 600 .env
  deactivate
  cd -
  echo ""
  echo "    ⚠️  ACTION REQUISE — Édite $ENV_FILE et renseigne :"
  echo "       RESEND_API_KEY=\"re_xxx\"     (clé API Resend)"
  echo "       ADMIN_EMAIL=\"ton@email.com\"  (compte super-admin)"
  echo ""
else
  echo "==> $ENV_FILE existe — backup + vérification des variables requises..."
  # --- Backup automatique du .env avant toute modification ---
  # On garde les 10 derniers backups (rotation FIFO) pour pouvoir restaurer
  # rapidement si une mise à jour casse quelque chose.
  BACKUP_DIR="$APP_DIR/backend/.env.backups"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/.env.$(date -u +%Y%m%dT%H%M%SZ)"
  cp -a "$ENV_FILE" "$BACKUP_FILE"
  chmod 600 "$BACKUP_FILE"
  echo "    backup créé : $BACKUP_FILE"
  # Rotation : on ne garde que les 10 plus récents
  ls -1t "$BACKUP_DIR"/.env.* 2>/dev/null | tail -n +11 | xargs -r rm -f

  # Add any missing variable WITHOUT overwriting existing values.
  ensure_env_var() {
    local key="$1"
    local default_value="$2"
    if ! grep -qE "^${key}=" "$ENV_FILE"; then
      echo "${key}=${default_value}" >> "$ENV_FILE"
      echo "    + ajouté : ${key}"
    fi
  }
  ensure_env_var "RESEND_API_KEY"  '""'
  ensure_env_var "SENDER_EMAIL"    '"Storm Monitoring <noreply@quentin-astro.fr>"'
  ensure_env_var "PUBLIC_APP_URL"  '"https://storm-monitor.quentin-astro.fr"'
  ensure_env_var "ADMIN_EMAIL"     '""'
  ensure_env_var "DISCORD_WEBHOOK_URL"  '""'
  ensure_env_var "TELEGRAM_BOT_TOKEN"   '""'
  ensure_env_var "TELEGRAM_CHAT_ID"     '""'
  ensure_env_var "WEBHOOK_APP_URL"      '"https://storm-monitor.quentin-astro.fr"'
  ensure_env_var "WEBHOOK_COOLDOWN_S"   '"900"'
  ensure_env_var "XWEATHER_COMBINED_TOKEN" '""'
  chmod 600 "$ENV_FILE"
fi

# ---------------------------------------------------------------------------
# 4. Frontend — yarn install + production build
# ---------------------------------------------------------------------------
echo "==> Building frontend..."
cat > "$APP_DIR/frontend/.env" <<EOF
REACT_APP_BACKEND_URL=https://storm-monitor.quentin-astro.fr
EOF

cd "$APP_DIR/frontend"

# Filter yarn install output: keep errors visible, archive the noisy
# "warning ... is deprecated / no longer supported" lines inherited from
# react-scripts (CRA EOL) to /var/log so the install output stays readable.
# The `resolutions` block in package.json already pins safe CVE-fixes for
# the most critical sub-deps (nth-check, postcss, cookie, semver,
# serialize-javascript). The remaining warnings are cosmetic noise from
# packages baked into CRA that we cannot upgrade without migrating to Vite.
YARN_LOG="/var/log/storm-monitor-yarn-install.log"
: > "$YARN_LOG"
set +e
yarn install 2>&1 | tee "$YARN_LOG" | grep -vE '^warning |^$'
YARN_RC=${PIPESTATUS[0]}
set -e
if [[ $YARN_RC -ne 0 ]]; then
  echo "ERROR: yarn install failed (rc=$YARN_RC). See $YARN_LOG for details." >&2
  exit $YARN_RC
fi
WARN_COUNT=$(grep -cE '^warning ' "$YARN_LOG" 2>/dev/null || true)
WARN_COUNT=${WARN_COUNT:-0}
echo "    [yarn] ${WARN_COUNT} warnings cosmétiques filtrés (héritage react-scripts EOL) — log: $YARN_LOG"

yarn build
cd -

# ---------------------------------------------------------------------------
# 5. Nginx vhost
# ---------------------------------------------------------------------------
# We define the full HTTP+HTTPS config in one block. Initially only the HTTP
# server is active because the SSL certs don't exist yet — we comment-out the
# 443 block. After running certbot, we'll uncomment it (or certbot does it).
echo "==> Writing Nginx vhost..."

mkdir -p /etc/nginx/snippets

# Idempotent: always rewrite the snippet from scratch (no append, no duplicates)
rm -f /etc/nginx/snippets/storm-monitor-app.conf

# Define a reusable config snippet with all the application routes.
#
# IMPORTANT — Alt-Svc header repetition:
# nginx's `add_header` directives are NOT inherited from outer scopes if the
# inner block defines its own add_header. Since several location blocks set
# Cache-Control headers, we must repeat `add_header Alt-Svc` in EACH block,
# otherwise tools like http3check.net that probe specific paths (e.g.
# /index.html) won't see the HTTP/3 advertisement. This is required for
# external HTTP/3 detection to work.
cat > /etc/nginx/snippets/storm-monitor-app.conf <<EOF
root ${APP_DIR}/frontend/build;
index index.html;

client_max_body_size 25m;

# Backend API proxy
location /api/ {
    proxy_pass http://127.0.0.1:${BACKEND_PORT};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
}

# GeoJSON / static data assets
location /geo/ {
    try_files \$uri =404;
    add_header Cache-Control "public, max-age=86400";
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
}

# Service worker — never cache, must update instantly
location = /sw.js {
    try_files \$uri =404;
    add_header Cache-Control "no-cache, no-store, must-revalidate" always;
    add_header Pragma "no-cache" always;
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
    expires off;
}

# index.html — never cache (SPA shell must always pull latest hashed assets)
location = /index.html {
    add_header Cache-Control "no-cache, no-store, must-revalidate" always;
    add_header Pragma "no-cache" always;
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
    expires off;
    try_files \$uri =404;
}

# Hashed static assets (CRA build output) — cache aggressively
location /static/ {
    try_files \$uri =404;
    add_header Cache-Control "public, max-age=31536000, immutable";
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
}

# Self-hosted webfonts (immutable, served via HTTP/3)
location /fonts/ {
    try_files \$uri =404;
    add_header Cache-Control "public, max-age=31536000, immutable";
    add_header Access-Control-Allow-Origin "*";
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
}

# SPA fallback
location / {
    try_files \$uri /index.html;
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
}

gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types text/plain text/css application/javascript application/json image/svg+xml;
EOF

# Catch-all default vhost — prevents Host-header bleed between sibling vhosts
# (e.g. Android Chrome HTTP/2 connection coalescing landing on the wrong app).
# Any request whose Host header doesn't match a declared server_name is dropped.
#
# Step 1: strip every existing "default_server" declaration on port 80 from
#         other vhosts, otherwise Nginx will refuse with "duplicate default
#         server for 0.0.0.0:80". We touch only sibling configs, never our own.
echo "==> Stripping legacy default_server declarations on port 80..."
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [[ -e "$f" ]] || continue
  case "$f" in
    */00-default-catchall.conf|*/storm-monitor.conf) continue ;;
  esac
  if grep -qE 'listen[[:space:]]+(\[::\]:)?80[[:space:]]+default_server' "$f"; then
    echo "    - cleaning $f"
    sed -i -E 's/(listen[[:space:]]+(\[::\]:)?80)[[:space:]]+default_server/\1/g' "$f"
  fi
done

# Step 2: write the strict catch-all. Any unknown Host header → connection closed.
cat > /etc/nginx/conf.d/00-default-catchall.conf <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}
EOF

# HTTP vhost — always active. If SSL certs exist (post-certbot), redirect to HTTPS.
SSL_CERT="/etc/letsencrypt/live/storm-monitor.quentin-astro.fr/fullchain.pem"
SSL_KEY="/etc/letsencrypt/live/storm-monitor.quentin-astro.fr/privkey.pem"

if [[ -f "$SSL_CERT" && -f "$SSL_KEY" ]]; then
  echo "==> SSL certs found — writing HTTPS vhost"
  cat > /etc/nginx/sites-available/storm-monitor.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name storm-monitor.quentin-astro.fr;

    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    # HTTP/3 (QUIC) — nginx 1.25+. Make sure UDP 443 is open in your firewall:
    #   ufw allow 443/udp
    listen 443 quic reuseport;
    listen [::]:443 quic reuseport;
    http2 on;
    http3 on;
    quic_retry on;
    server_name storm-monitor.quentin-astro.fr;

    ssl_certificate     $SSL_CERT;
    ssl_certificate_key $SSL_KEY;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Advertise HTTP/3 to clients so they upgrade on the next visit
    add_header Alt-Svc 'h3=":443"; ma=86400' always;

    include /etc/nginx/snippets/storm-monitor-app.conf;
}
EOF
else
  echo "==> No SSL certs yet — writing HTTP-only vhost (run certbot afterwards)"
  cat > /etc/nginx/sites-available/storm-monitor.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name storm-monitor.quentin-astro.fr;

    include /etc/nginx/snippets/storm-monitor-app.conf;
}
EOF
fi

ln -sf /etc/nginx/sites-available/storm-monitor.conf /etc/nginx/sites-enabled/storm-monitor.conf
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx

# ---------------------------------------------------------------------------
# 6. systemd unit
# ---------------------------------------------------------------------------
echo "==> Writing systemd unit..."
cat > /etc/systemd/system/storm-monitor.service <<EOF
[Unit]
Description=Storm Monitor backend (FastAPI + uvicorn)
After=network-online.target mongod.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/var/www/storm-monitor/backend
EnvironmentFile=/var/www/storm-monitor/backend/.env
Environment=VIDEO_CACHE_DIR=/var/www/storm-monitor/cache/videos
ExecStart=/var/www/storm-monitor/backend/venv/bin/uvicorn server:app --host 127.0.0.1 --port ${BACKEND_PORT} --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/var/log/storm-monitor.log
StandardError=append:/var/log/storm-monitor.err.log

# Hardening (relaxed for root user). PrivateTmp=false so MP4 cache survives restart.
NoNewPrivileges=true
PrivateTmp=false

[Install]
WantedBy=multi-user.target
EOF

# Pre-create log files
touch /var/log/storm-monitor.log /var/log/storm-monitor.err.log
chown "$RUN_USER":"$RUN_USER" /var/log/storm-monitor.log /var/log/storm-monitor.err.log

systemctl daemon-reload
# `enable --now` only START the service if it's NOT running; it does NOT
# pick up freshly rsync'd Python files when it's already up. We must force
# a hard restart so uvicorn re-imports the new server.py / severe.py.
systemctl enable storm-monitor.service
# Contrôle CPU EMPIRIQUE avant de lancer le service : import de la chaîne
# COMPLÈTE de l'application avec le python du venv. Un paquet binaire compilé
# avec des instructions absentes de CE processeur (SSE4/AVX sur vieux Atom)
# meurt en 'Illegal instruction' — on refuse de démarrer un service cassé.
echo "==> Contrôle CPU : import complet de l'application sur ce processeur..."
set +e
IMPORT_OUT="$(cd "$APP_DIR/backend" && timeout 180 venv/bin/python -c 'import server' 2>&1)"
IMPORT_RC=$?
set -e
if [[ $IMPORT_RC -ne 0 ]]; then
  if [[ $IMPORT_RC -eq 132 || $IMPORT_RC -eq 139 || "$IMPORT_OUT" == *"Illegal instruction"* ]]; then
    echo "ERROR: 'import server' meurt en Illegal instruction sur ce CPU." >&2
  else
    echo "ERROR: 'import server' échoue (rc=$IMPORT_RC) :" >&2
  fi
  echo "$IMPORT_OUT" | tail -n 15 >&2
  echo "ERROR: INSTALLATION INTERROMPUE avant le démarrage du service." >&2
  exit 1
fi
echo "    ✓ Chaîne d'import complète compatible avec ce CPU"

systemctl restart storm-monitor.service
echo "    Restarted storm-monitor service to pick up new code."

# Sonde santé réelle : une vraie réponse HTTP, pas juste un status systemd.
echo "==> Sonde santé : attente d'une réponse de l'API (127.0.0.1:${BACKEND_PORT}/api/health)..."
HEALTH_OK=0
for _ in $(seq 1 12); do
  sleep 2
  if curl -fsS -m 4 "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    HEALTH_OK=1
    break
  fi
done
if [[ $HEALTH_OK -eq 1 ]]; then
  echo "    ✓ Le backend répond RÉELLEMENT sur /api/health"
else
  echo "ERROR: le backend ne répond pas sur /api/health après 24 s." >&2
  echo "       Dernières lignes de /var/log/storm-monitor.err.log :" >&2
  tail -n 25 /var/log/storm-monitor.err.log >&2 || true
  exit 1
fi

# ---------------------------------------------------------------------------
# 7. Final report
# ---------------------------------------------------------------------------
echo ""
echo "==> Done."
echo ""
echo "    Status        : systemctl status storm-monitor"
echo "    Backend logs  : journalctl -u storm-monitor -f"
echo "                    tail -f /var/log/storm-monitor.err.log"
echo "    Nginx logs    : tail -f /var/log/nginx/error.log"
echo ""
echo "    Test URL      : https://storm-monitor.quentin-astro.fr (after Certbot)"
echo "                    http://storm-monitor.quentin-astro.fr (HTTP fallback)"
echo "    Test API      : curl http://127.0.0.1:${BACKEND_PORT}/api/weather/current?lat=43.0951\&lon=-0.0434"
echo ""
echo "    NEXT — enable HTTPS (required, frontend is built for HTTPS):"
echo "        apt install -y certbot python3-certbot-nginx"
echo "        certbot --nginx -d storm-monitor.quentin-astro.fr"
echo ""
echo "    NEXT — enable HTTP/3 (QUIC):"
echo "        ufw allow 443/udp       # if you use ufw"
echo "        # or for iptables:"
echo "        # iptables -I INPUT -p udp --dport 443 -j ACCEPT"
echo "        # Verify with the snap-installed curl that supports HTTP/3:"
echo "        curl3 --http3-only -sI https://storm-monitor.quentin-astro.fr/ | head -3"
echo "        # (open a NEW shell first if you also want plain 'curl' to use HTTP/3 via the alias)"
echo ""
echo "    NEXT — enable webhooks (optional — Discord / Telegram):"
echo "        edit /var/www/storm-monitor/backend/.env"
echo "        set DISCORD_WEBHOOK_URL=\"https://discord.com/api/webhooks/...\""
echo "        and/or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"
echo "        systemctl restart storm-monitor"
echo "        # test (auth token required):"
echo "        curl -X POST https://storm-monitor.quentin-astro.fr/api/webhooks/test -H \"Authorization: Bearer \$TOKEN\""
echo ""
echo "    To deploy a new version (update mode — clone is preserved):"
echo "        bash install.sh                # auto-detect existing install → git pull"
echo "        # OR manually:"
echo "        cd /var/www/storm-monitor && git pull"
echo "        cd frontend && yarn install && yarn build"
echo "        systemctl restart storm-monitor && systemctl reload nginx"
echo ""

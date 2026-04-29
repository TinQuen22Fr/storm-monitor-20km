#!/usr/bin/env bash
#
# Storm Monitor — installation script for Kimsufi (Ubuntu/Debian)
# Usage:  sudo bash install.sh
#
# What it does:
#   1. Installs Python 3.11+, Node.js 20, Yarn, MongoDB 7, Nginx
#   2. Clones https://github.com/TinQuen22Fr/storm-monitor-20km.git into /var/www/storm-monitor
#   3. Configures git remote for future pushes
#   4. Creates Python venv + installs backend dependencies
#   5. Generates /var/www/storm-monitor/backend/.env (random secrets + VAPID)
#   6. Builds frontend with REACT_APP_BACKEND_URL=http://storm-monitor.quentin-astro.fr
#   7. Creates Nginx vhost /etc/nginx/sites-available/storm-monitor.conf (HTTP only)
#   8. Creates systemd unit /etc/systemd/system/storm-monitor.service (port 8001)
#   9. Starts everything
#
# SSL/HTTPS (Certbot) is intentionally NOT installed — do it manually after.

set -euo pipefail

REPO_URL="https://github.com/TinQuen22Fr/storm-monitor-20km.git"
APP_DIR="/var/www/storm-monitor"
DOMAIN="storm-monitor.quentin-astro.fr"
BACKEND_PORT="8001"
RUN_USER="root"

# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: this script must be run as root (sudo bash install.sh)" >&2
  exit 1
fi

if ! id "$RUN_USER" &>/dev/null; then
  echo "ERROR: user '$RUN_USER' does not exist on this system" >&2
  exit 1
fi

echo "==> Storm Monitor — installation on $(hostname)"
echo "    Domain  : $DOMAIN"
echo "    Dir     : $APP_DIR"
echo "    Backend : 127.0.0.1:$BACKEND_PORT"
echo "    User    : $RUN_USER"

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
echo "==> Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    git curl ca-certificates gnupg lsb-release \
    build-essential nginx \
    python3 python3-venv python3-pip python3-dev \
    fonts-dejavu

# Node.js 20
if ! command -v node >/dev/null || [[ "$(node -v)" != v20* ]]; then
  echo "==> Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

# Yarn
if ! command -v yarn >/dev/null; then
  npm install -g yarn
fi

# MongoDB 8.0 (supports Ubuntu 22.04 jammy + 24.04 noble + Debian 12 bookworm)
if ! command -v mongod >/dev/null; then
  echo "==> Installing MongoDB 8.0..."
  CODENAME="$(lsb_release -sc)"
  # Strip stale 7.0 repo if it exists (it has no Noble release file)
  rm -f /etc/apt/sources.list.d/mongodb-org-7.0.list
  rm -f /usr/share/keyrings/mongodb-server-7.0.gpg

  curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
      gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
  echo "deb [signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg] https://repo.mongodb.org/apt/ubuntu ${CODENAME}/mongodb-org/8.0 multiverse" \
      > /etc/apt/sources.list.d/mongodb-org-8.0.list
  apt-get update -y
  apt-get install -y mongodb-org
fi
systemctl enable --now mongod

# ---------------------------------------------------------------------------
# 2. Clone repository
# ---------------------------------------------------------------------------
mkdir -p /var/www
if [[ -d "$APP_DIR/.git" ]]; then
  echo "==> Repository already cloned, pulling latest..."
  sudo -u "$RUN_USER" -H git -C "$APP_DIR" pull --ff-only
else
  echo "==> Cloning repository..."
  sudo -u "$RUN_USER" -H git clone "$REPO_URL" "$APP_DIR"
fi

# Configure remote so future `git push` works (origin already set by clone)
sudo -u "$RUN_USER" -H git -C "$APP_DIR" remote set-url origin "$REPO_URL"

chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

# ---------------------------------------------------------------------------
# 3. Backend — Python venv, dependencies, .env
# ---------------------------------------------------------------------------
echo "==> Setting up backend..."
sudo -u "$RUN_USER" -H bash -c "
  set -euo pipefail
  cd '$APP_DIR/backend'
  if [ ! -d venv ]; then
    python3 -m venv venv
  fi
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ || true
"

# Generate .env only if missing
if [[ ! -f "$APP_DIR/backend/.env" ]]; then
  echo "==> Generating backend/.env with fresh secrets..."
  sudo -u "$RUN_USER" -H bash -c "
    set -euo pipefail
    cd '$APP_DIR/backend'
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
private_pem = v.private_pem().decode().replace('\n', '\\\\n')

print('MONGO_URL=\"mongodb://localhost:27017\"')
print('DB_NAME=\"storm_lourdes\"')
print('CORS_ORIGINS=\"*\"')
print(f'JWT_SECRET=\"{secrets.token_urlsafe(48)}\"')
print(f'UPLOAD_API_KEY=\"lourdes-{secrets.token_urlsafe(32)}\"')
print('VAPID_SUBJECT=\"mailto:quentin@quentin-astro.fr\"')
print(f'VAPID_PUBLIC_KEY=\"{public_b64}\"')
print(f'VAPID_PRIVATE_KEY_PEM=\"{private_pem}\"')
print('STORM_DATA_FILE=\"/var/www/storm-monitor/backend/storm_data.json\"')
PY
    chmod 600 .env
  "
else
  echo "==> backend/.env already exists, skipping secrets generation"
fi

# ---------------------------------------------------------------------------
# 4. Frontend — yarn install + production build
# ---------------------------------------------------------------------------
echo "==> Building frontend..."
cat > "$APP_DIR/frontend/.env" <<EOF
REACT_APP_BACKEND_URL=http://storm-monitor.quentin-astro.fr
EOF
chown "$RUN_USER":"$RUN_USER" "$APP_DIR/frontend/.env"

sudo -u "$RUN_USER" -H bash -c "
  set -euo pipefail
  cd '$APP_DIR/frontend'
  yarn install --frozen-lockfile
  yarn build
"

# ---------------------------------------------------------------------------
# 5. Nginx vhost (HTTP only — SSL to be added manually with certbot)
# ---------------------------------------------------------------------------
echo "==> Writing Nginx vhost..."
cat > /etc/nginx/sites-available/storm-monitor.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name storm-monitor.quentin-astro.fr;

    root /var/www/storm-monitor/frontend/build;
    index index.html;

    client_max_body_size 25m;

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    # GeoJSON / static data assets
    location /geo/ {
        try_files \$uri =404;
        add_header Cache-Control "public, max-age=86400";
    }

    # Service worker (push notifications)
    location = /sw.js {
        try_files \$uri =404;
        add_header Cache-Control "no-cache";
    }

    # SPA fallback
    location / {
        try_files \$uri /index.html;
    }

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/javascript application/json image/svg+xml;
}
EOF

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
ExecStart=/var/www/storm-monitor/backend/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/var/log/storm-monitor.log
StandardError=append:/var/log/storm-monitor.err.log

# Hardening (relaxed for root user)
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Pre-create log files
touch /var/log/storm-monitor.log /var/log/storm-monitor.err.log
chown "$RUN_USER":"$RUN_USER" /var/log/storm-monitor.log /var/log/storm-monitor.err.log

systemctl daemon-reload
systemctl enable --now storm-monitor.service

# ---------------------------------------------------------------------------
# 7. Final report
# ---------------------------------------------------------------------------
sleep 3
echo ""
echo "==> Done."
echo ""
echo "    Status        : systemctl status storm-monitor"
echo "    Backend logs  : journalctl -u storm-monitor -f"
echo "                    tail -f /var/log/storm-monitor.err.log"
echo "    Nginx logs    : tail -f /var/log/nginx/error.log"
echo ""
echo "    Test URL      : http://storm-monitor.quentin-astro.fr"
echo "    Test API      : curl http://127.0.0.1:8001/api/weather/current?lat=43.0951\&lon=-0.0434"
echo ""
echo "    To enable HTTPS later (when DNS points to this IP):"
echo "        sudo apt install -y certbot python3-certbot-nginx"
echo "        sudo certbot --nginx -d storm-monitor.quentin-astro.fr"
echo ""
echo "    To deploy a new version:"
echo "        cd /var/www/storm-monitor && git pull"
echo "        cd frontend && yarn install --frozen-lockfile && yarn build"
echo "        systemctl restart storm-monitor && systemctl reload nginx"
echo ""

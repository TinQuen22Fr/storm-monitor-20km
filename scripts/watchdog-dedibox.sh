#!/usr/bin/env bash
#
# watchdog-dedibox.sh — SURVEILLANCE + BASCULE AUTOMATIQUE.
# À installer SUR LE KIMSUFI (le secours surveille le principal).
#
# Toutes les minutes : sonde https://<domaine>/api/health DIRECTEMENT sur l'IP
# du Dedibox (via --resolve, indépendant du DNS courant).
#   - 3 échecs consécutifs  → PANNE : email d'alerte + bascule DNS vers le Kimsufi
#   - 5 succès consécutifs (en mode panne) → RETOUR : email + DNS vers le Dedibox
# La bascule DNS est déléguée à dns-switch.sh (API Ionos si configurée, sinon
# l'email indique de basculer manuellement).
#
# INSTALLATION (une fois, sur le Kimsufi) :
#   bash /opt/storm-monitor/scripts/watchdog-dedibox.sh --install
# STATUT :
#   bash /opt/storm-monitor/scripts/watchdog-dedibox.sh --status
#
set -euo pipefail

# ------------------------- CONFIG --------------------------------------------
DEDIBOX_IP="${DEDIBOX_IP:-51.158.154.131}"
DOMAIN="${DOMAIN:-storm-monitor.quentin-astro.fr}"
FAIL_THRESHOLD=3
OK_THRESHOLD=5
ENV_FILE="/var/www/storm-monitor/backend/.env"
STATE_DIR="/var/lib/storm-watchdog"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DNS_SWITCH="$SCRIPT_DIR/dns-switch.sh"
LOG="/var/log/storm-watchdog.log"
# -----------------------------------------------------------------------------

mkdir -p "$STATE_DIR"
MODE_F="$STATE_DIR/mode"; FAILS_F="$STATE_DIR/fails"; OKS_F="$STATE_DIR/oks"
[[ -f "$MODE_F" ]] || echo "normal" > "$MODE_F"
[[ -f "$FAILS_F" ]] || echo 0 > "$FAILS_F"
[[ -f "$OKS_F" ]] || echo 0 > "$OKS_F"

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

env_get() { grep -m1 "^$1=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"'; }

send_email() {
  local subject="$1" body="$2"
  local key sender admin
  key="$(env_get RESEND_API_KEY)"; sender="$(env_get SENDER_EMAIL)"; admin="$(env_get ADMIN_EMAIL)"
  if [[ -z "$key" || -z "$admin" ]]; then
    log "WARN: RESEND_API_KEY/ADMIN_EMAIL absents de $ENV_FILE — pas d'email envoyé"
    return 0
  fi
  curl -fsS -m 15 https://api.resend.com/emails \
    -H "Authorization: Bearer $key" -H "Content-Type: application/json" \
    -d "$(python3 -c "import json,sys;print(json.dumps({'from':'$sender','to':['$admin'],'subject':'$subject','text':sys.argv[1]}))" "$body")" \
    >/dev/null 2>&1 || log "WARN: envoi email Resend échoué"
}

# --- Installation du timer systemd -------------------------------------------
if [[ "${1:-}" == "--install" ]]; then
  [[ $EUID -eq 0 ]] || { echo "ERROR: root requis pour --install" >&2; exit 1; }
  cat > /etc/systemd/system/storm-watchdog.service <<EOF
[Unit]
Description=Storm Monitor — watchdog du Dedibox (bascule DNS auto)
[Service]
Type=oneshot
ExecStart=/usr/bin/bash $SCRIPT_DIR/watchdog-dedibox.sh
EOF
  cat > /etc/systemd/system/storm-watchdog.timer <<EOF
[Unit]
Description=Storm Monitor — sonde du Dedibox toutes les minutes
[Timer]
OnCalendar=*-*-* *:*:00
Persistent=false
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now storm-watchdog.timer
  echo "✓ Watchdog installé — sonde toutes les minutes (journal : $LOG)"
  echo "  Statut : bash $SCRIPT_DIR/watchdog-dedibox.sh --status"
  exit 0
fi

if [[ "${1:-}" == "--status" ]]; then
  echo "Mode        : $(cat "$MODE_F")"
  echo "Échecs consécutifs : $(cat "$FAILS_F")  ·  Succès consécutifs : $(cat "$OKS_F")"
  systemctl is-active storm-watchdog.timer 2>/dev/null | sed 's/^/Timer       : /'
  tail -n 8 "$LOG" 2>/dev/null || true
  exit 0
fi

# --- Sonde --------------------------------------------------------------------
MODE="$(cat "$MODE_F")"
if curl -fsS -m 8 -k "https://$DOMAIN/api/health" --resolve "$DOMAIN:443:$DEDIBOX_IP" >/dev/null 2>&1; then
  PROBE="ok"
else
  PROBE="fail"
fi

if [[ "$PROBE" == "ok" ]]; then
  echo 0 > "$FAILS_F"
  OKS=$(( $(cat "$OKS_F") + 1 )); echo "$OKS" > "$OKS_F"
  if [[ "$MODE" == "failover" && $OKS -ge $OK_THRESHOLD ]]; then
    log "RETOUR : Dedibox rétabli ($OKS succès) — DNS → Dedibox"
    echo "normal" > "$MODE_F"; echo 0 > "$OKS_F"
    SWITCH_MSG="$("$DNS_SWITCH" to-dedibox 2>&1 || true)"
    log "$SWITCH_MSG"
    send_email "✅ Storm Monitor — Dedibox rétabli, retour au principal" \
"Le Dedibox ($DEDIBOX_IP) répond de nouveau sur /api/health ($OKS succès consécutifs).

Bascule DNS retour : $SWITCH_MSG

— watchdog Kimsufi"
  fi
else
  echo 0 > "$OKS_F"
  FAILS=$(( $(cat "$FAILS_F") + 1 )); echo "$FAILS" > "$FAILS_F"
  log "sonde KO ($FAILS/$FAIL_THRESHOLD) — mode=$MODE"
  if [[ "$MODE" == "normal" && $FAILS -ge $FAIL_THRESHOLD ]]; then
    log "PANNE : Dedibox injoignable ($FAILS échecs) — DNS → Kimsufi"
    echo "failover" > "$MODE_F"; echo 0 > "$FAILS_F"
    SWITCH_MSG="$("$DNS_SWITCH" to-kimsufi 2>&1 || true)"
    log "$SWITCH_MSG"
    send_email "🚨 Storm Monitor — PANNE Dedibox, bascule sur le Kimsufi" \
"Le Dedibox ($DEDIBOX_IP) ne répond plus sur /api/health ($FAILS échecs consécutifs).

Bascule DNS : $SWITCH_MSG

Le Kimsufi assure le relais. Retour automatique dès que le Dedibox répondra à nouveau ($OK_THRESHOLD succès consécutifs).

— watchdog Kimsufi"
  fi
fi

#!/usr/bin/env bash
#
# dns-switch.sh — bascule l'enregistrement A du domaine via l'API DNS Ionos.
# Appelé par watchdog-dedibox.sh (to-kimsufi / to-dedibox), utilisable à la main.
#
# CONFIGURATION (une fois) : créer /etc/storm-monitor/dns.env :
#   IONOS_API_KEY="publicprefix.secret"     ← https://developer.hosting.ionos.fr (menu API Keys)
#   DNS_ZONE="quentin-astro.fr"
#   DNS_RECORD="storm-monitor.quentin-astro.fr"
#   DEDIBOX_IP="51.158.154.131"
#   KIMSUFI_IP="91.121.77.xxx"              ← IP publique du Kimsufi
#   DNS_TTL="300"
#
# Sans ce fichier ou sans clé : le script n'échoue pas, il indique la bascule
# MANUELLE à faire chez Ionos (l'email du watchdog contient ce message).
#
# USAGE : bash dns-switch.sh to-kimsufi | to-dedibox | status
#
set -euo pipefail

CONF="/etc/storm-monitor/dns.env"
[[ -f "$CONF" ]] && source "$CONF"

TARGET="${1:-status}"
API="https://api.hosting.ionos.com/dns/v1"

manual_msg() {
  echo "BASCULE MANUELLE REQUISE : chez Ionos, pointer l'enregistrement A de ${DNS_RECORD:-storm-monitor.quentin-astro.fr} vers $1 (API Ionos non configurée — voir /etc/storm-monitor/dns.env)"
}

case "$TARGET" in
  to-kimsufi)  WANT_IP="${KIMSUFI_IP:-}";  LABEL="Kimsufi" ;;
  to-dedibox)  WANT_IP="${DEDIBOX_IP:-}";  LABEL="Dedibox" ;;
  status)      WANT_IP="" ;;
  *) echo "usage: dns-switch.sh to-kimsufi|to-dedibox|status" >&2; exit 1 ;;
esac

if [[ -z "${IONOS_API_KEY:-}" ]]; then
  if [[ "$TARGET" == "status" ]]; then
    echo "API Ionos non configurée ($CONF absent ou incomplet)"
  else
    manual_msg "$WANT_IP ($LABEL)"
  fi
  exit 0
fi

api() { curl -fsS -m 20 -H "X-API-Key: $IONOS_API_KEY" -H "Content-Type: application/json" "$@"; }

ZONE_ID="$(api "$API/zones" | python3 -c "
import json,sys
zones=json.load(sys.stdin)
print(next((z['id'] for z in zones if z['name']=='$DNS_ZONE'),''))" )"
[[ -n "$ZONE_ID" ]] || { echo "ERROR: zone $DNS_ZONE introuvable via l'API Ionos"; exit 1; }

REC_JSON="$(api "$API/zones/$ZONE_ID?recordName=$DNS_RECORD&recordType=A")"
read -r REC_ID CUR_IP <<< "$(echo "$REC_JSON" | python3 -c "
import json,sys
z=json.load(sys.stdin)
recs=[r for r in z.get('records',[]) if r['type']=='A']
print((recs[0]['id']+' '+recs[0]['content']) if recs else ' ')" )"
[[ -n "${REC_ID:-}" ]] || { echo "ERROR: enregistrement A $DNS_RECORD introuvable"; exit 1; }

if [[ "$TARGET" == "status" ]]; then
  echo "DNS $DNS_RECORD → $CUR_IP (Dedibox=$DEDIBOX_IP · Kimsufi=$KIMSUFI_IP)"
  exit 0
fi

if [[ "$CUR_IP" == "$WANT_IP" ]]; then
  echo "DNS déjà sur $LABEL ($WANT_IP) — rien à faire"
  exit 0
fi

api -X PUT "$API/zones/$ZONE_ID/records/$REC_ID" \
  -d "{\"content\":\"$WANT_IP\",\"ttl\":${DNS_TTL:-300},\"disabled\":false}" >/dev/null
echo "DNS basculé automatiquement : $DNS_RECORD → $WANT_IP ($LABEL, TTL ${DNS_TTL:-300}s)"

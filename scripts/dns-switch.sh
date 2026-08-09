#!/usr/bin/env bash
#
# dns-switch.sh — bascule les enregistrements A (+ AAAA) du domaine via l'API DNS Ionos.
# Appelé par watchdog-dedibox.sh (to-kimsufi / to-dedibox), utilisable à la main.
#
# CONFIGURATION (une fois) : créer /etc/storm-monitor/dns.env :
#   IONOS_API_KEY="publicprefix.secret"   ← https://developer.hosting.ionos.fr (menu API Keys)
#   DNS_ZONE="quentin-astro.fr"
#   DNS_RECORD="storm-monitor.quentin-astro.fr"
#   DEDIBOX_IP="51.158.154.131"
#   KIMSUFI_IP="5.135.160.56"
#   DEDIBOX_IP6="2001:0bc8:1600:0004:0208:a2ff:fe0c:6708"   ← IPv6 du Dedibox (champ AAAA)
#   KIMSUFI_IP6="2001:41d0:8:e338::1"     ← IPv6 du Kimsufi ; si VIDE, le AAAA est DÉSACTIVÉ
#                                           pendant la bascule (trafic 100% IPv4) puis
#                                           RÉACTIVÉ vers le Dedibox au retour.
#   DNS_TTL="60"
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

case "$TARGET" in
  to-kimsufi)  WANT_IP="${KIMSUFI_IP:-}";  WANT_IP6="${KIMSUFI_IP6:-}";  LABEL="Kimsufi" ;;
  to-dedibox)  WANT_IP="${DEDIBOX_IP:-}";  WANT_IP6="${DEDIBOX_IP6:-}";  LABEL="Dedibox" ;;
  status)      WANT_IP=""; WANT_IP6="" ;;
  *) echo "usage: dns-switch.sh to-kimsufi|to-dedibox|status" >&2; exit 1 ;;
esac

if [[ -z "${IONOS_API_KEY:-}" ]]; then
  if [[ "$TARGET" == "status" ]]; then
    echo "API Ionos non configurée ($CONF absent ou incomplet)"
  else
    echo "BASCULE MANUELLE REQUISE : chez Ionos, pointer A (et AAAA) de ${DNS_RECORD:-storm-monitor.quentin-astro.fr} vers le $TARGET (API Ionos non configurée — voir $CONF)"
  fi
  exit 0
fi

api() { curl -fsS -m 20 -H "X-API-Key: $IONOS_API_KEY" -H "Content-Type: application/json" "$@"; }

ZONE_ID="$(api "$API/zones" | python3 -c "
import json,sys
zones=json.load(sys.stdin)
print(next((z['id'] for z in zones if z['name']=='$DNS_ZONE'),''))" )"
[[ -n "$ZONE_ID" ]] || { echo "ERROR: zone $DNS_ZONE introuvable via l'API Ionos"; exit 1; }

# Récupère les enregistrements A et AAAA du sous-domaine : "id type content disabled"
RECORDS="$(api "$API/zones/$ZONE_ID?recordName=$DNS_RECORD" | python3 -c "
import json,sys
z=json.load(sys.stdin)
for r in z.get('records',[]):
    if r['type'] in ('A','AAAA'):
        print(r['id'], r['type'], r['content'], str(r.get('disabled', False)).lower())" )"

A_ID=""; A_CUR=""; AAAA_ID=""; AAAA_CUR=""; AAAA_DIS=""
while read -r rid rtype rcontent rdis; do
  [[ "$rtype" == "A" ]] && { A_ID="$rid"; A_CUR="$rcontent"; }
  [[ "$rtype" == "AAAA" ]] && { AAAA_ID="$rid"; AAAA_CUR="$rcontent"; AAAA_DIS="$rdis"; }
done <<< "$RECORDS"
[[ -n "$A_ID" ]] || { echo "ERROR: enregistrement A $DNS_RECORD introuvable"; exit 1; }

if [[ "$TARGET" == "status" ]]; then
  echo "A    $DNS_RECORD → $A_CUR (Dedibox=$DEDIBOX_IP · Kimsufi=$KIMSUFI_IP)"
  if [[ -n "$AAAA_ID" ]]; then
    echo "AAAA $DNS_RECORD → $AAAA_CUR (disabled=$AAAA_DIS)"
  else
    echo "AAAA absent"
  fi
  exit 0
fi

put_record() { # id content disabled
  api -X PUT "$API/zones/$ZONE_ID/records/$1" \
    -d "{\"content\":\"$2\",\"ttl\":${DNS_TTL:-60},\"disabled\":$3}" >/dev/null
}

MSG=""
# --- Champ A -----------------------------------------------------------------
if [[ "$A_CUR" == "$WANT_IP" ]]; then
  MSG="A déjà sur $LABEL ($WANT_IP)"
else
  put_record "$A_ID" "$WANT_IP" false
  MSG="A → $WANT_IP ($LABEL)"
fi

# --- Champ AAAA (IPv6) ---------------------------------------------------------
if [[ -n "$AAAA_ID" ]]; then
  if [[ -n "$WANT_IP6" ]]; then
    put_record "$AAAA_ID" "$WANT_IP6" false
    MSG="$MSG ; AAAA → $WANT_IP6 (actif)"
  else
    # Pas d'IPv6 sur la cible : on DÉSACTIVE le AAAA pour ne pas envoyer le
    # trafic IPv6 vers un serveur mort (il sera réactivé au retour Dedibox).
    put_record "$AAAA_ID" "$AAAA_CUR" true
    MSG="$MSG ; AAAA désactivé (pas d'IPv6 sur $LABEL — trafic 100% IPv4)"
  fi
fi

echo "DNS basculé automatiquement : $MSG (TTL ${DNS_TTL:-60}s)"

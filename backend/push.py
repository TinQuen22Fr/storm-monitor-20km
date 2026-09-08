"""Web Push subscriptions + sender using VAPID."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pywebpush import WebPushException, webpush

import fcm as fcm_mod

logger = logging.getLogger(__name__)


def vapid_public_key() -> str:
    return os.environ["VAPID_PUBLIC_KEY"]


def _vapid_claims() -> Dict[str, str]:
    return {"sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")}


def _private_key_pem() -> str:
    raw = os.environ["VAPID_PRIVATE_KEY_PEM"]
    # .env stores literal "\n" — convert to real newlines
    return raw.replace("\\n", "\n")


async def save_subscription(db, subscription: Dict, user_id: Optional[str] = None) -> Dict:
    """Store a push subscription keyed by endpoint (idempotent)."""
    endpoint = subscription.get("endpoint")
    if not endpoint:
        raise ValueError("missing endpoint")
    doc = {
        "id": str(uuid.uuid4()),
        "endpoint": endpoint,
        "keys": subscription.get("keys", {}),
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.push_subscriptions.update_one(
        {"endpoint": endpoint},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def remove_subscription(db, endpoint: str) -> int:
    res = await db.push_subscriptions.delete_one({"endpoint": endpoint})
    return res.deleted_count


async def all_subscriptions(db) -> List[Dict]:
    return await db.push_subscriptions.find({}, {"_id": 0}).to_list(2000)


async def send_to_all(db, title: str, body: str, url: str = "/", tag: str = "storm") -> Dict:
    """Broadcast (alertes orage) : toutes les subscriptions web + tous les FCM.
    Removes expired subscriptions (410/404).
    """
    subs = await all_subscriptions(db)
    return await _dispatch(db, subs, None, title, body, url, tag)


async def send_to_user(db, user_id: str, title: str, body: str, url: str = "/", tag: str = "storm") -> Dict:
    """Unicast (bouton test) : uniquement les appareils liés à cet utilisateur."""
    subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(2000)
    return await _dispatch(db, subs, user_id, title, body, url, tag)


async def _dispatch(db, subs: List[Dict], fcm_user_id: Optional[str], title: str, body: str, url: str, tag: str) -> Dict:
    sent = 0
    removed = 0
    errors = 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    for s in subs:
        sub_info = {"endpoint": s["endpoint"], "keys": s.get("keys", {})}
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=_private_key_pem(),
                vapid_claims=_vapid_claims(),
            )
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                await remove_subscription(db, s["endpoint"])
                removed += 1
            else:
                errors += 1
                logger.warning("WebPush error (%s): %s", code, e)
        except Exception as e:
            errors += 1
            logger.warning("WebPush generic error: %s", e)
    result = {"sent": sent, "removed": removed, "errors": errors, "total": len(subs)}
    # Relais vers les appareils Android natifs (FCM), no-op si non configuré
    try:
        if fcm_user_id is None:
            fcm_res = await fcm_mod.send_to_all(db, title=title, body=body, url=url, tag=tag)
        else:
            fcm_res = await fcm_mod.send_to_user(db, fcm_user_id, title=title, body=body, url=url, tag=tag)
        result["fcm"] = fcm_res
        result["sent"] += fcm_res.get("sent", 0)
        result["total"] += fcm_res.get("total", 0)
    except Exception as e:
        logger.warning("FCM relay error: %s", e)
    return result


def _is_in_quiet_hours(start_str: str, end_str: str) -> bool:
    try:
        now_hm = datetime.now().strftime("%H:%M")
        if start_str <= end_str:
            return start_str <= now_hm <= end_str
        else:
            return now_hm >= start_str or now_hm <= end_str
    except Exception:
        return False


async def send_personalized_storm_alert(
    db,
    recent_strikes: List[Dict],
    title: str,
    base_url: str = "/",
    tag: str = "storm",
    default_radius_km: float = 20.0,
) -> Dict:
    """Dispatche l'alerte orage selon les préférences de chaque utilisateur enregistré."""
    res = {"sent": 0, "skipped_quiet": 0, "skipped_threshold": 0, "skipped_disabled": 0}
    if not recent_strikes:
        return res

    # 1. Traiter les utilisateurs enregistrés
    users = await db.users.find({}, {"_id": 0, "id": 1, "alert_settings": 1}).to_list(5000)
    notified_user_ids = set()

    for u in users:
        uid = u.get("id")
        if not uid:
            continue

        st = u.get("alert_settings") or {}
        if not st.get("enabled", True):
            res["skipped_disabled"] += 1
            continue

        if st.get("quiet_hours_enabled", False):
            start = st.get("quiet_hours_start", "23:00")
            end = st.get("quiet_hours_end", "07:00")
            if _is_in_quiet_hours(start, end):
                res["skipped_quiet"] += 1
                continue

        user_radius = float(st.get("radius_km", default_radius_km))
        min_strikes = int(st.get("min_strikes", 1))

        # Impacts dans le rayon configuré par cet utilisateur
        user_strikes = [s for s in recent_strikes if float(s.get("distance_km", 999.0)) <= user_radius]
        if len(user_strikes) < min_strikes:
            res["skipped_threshold"] += 1
            continue

        closest_km = min(float(s.get("distance_km", 999.0)) for s in user_strikes)
        body = f"{len(user_strikes)} impact(s) détecté(s) dans votre rayon (le plus proche à {closest_km:.1f} km)."

        send_res = await send_to_user(db, uid, title=title, body=body, url=base_url, tag=tag)
        if send_res.get("sent", 0) > 0:
            res["sent"] += send_res["sent"]
            notified_user_ids.add(uid)

    # 2. Traiter les souscriptions anonymes (visiteurs web sans compte)
    anon_subs = await db.push_subscriptions.find({"user_id": None}, {"_id": 0}).to_list(2000)
    if anon_subs:
        default_strikes = [s for s in recent_strikes if float(s.get("distance_km", 999.0)) <= default_radius_km]
        if default_strikes:
            closest_km = min(float(s.get("distance_km", 999.0)) for s in default_strikes)
            body = f"{len(default_strikes)} impact(s) détecté(s) (le plus proche à {closest_km:.1f} km)."
            anon_res = await _dispatch(db, anon_subs, None, title, body, base_url, tag)
            res["sent"] += anon_res.get("sent", 0)

    return res

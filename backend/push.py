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
    """Send a push notification to every saved subscription.
    Removes expired subscriptions (410/404).
    """
    subs = await all_subscriptions(db)
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
        fcm_res = await fcm_mod.send_to_all(db, title=title, body=body, url=url, tag=tag)
        result["fcm"] = fcm_res
        result["sent"] += fcm_res.get("sent", 0)
        result["total"] += fcm_res.get("total", 0)
    except Exception as e:
        logger.warning("FCM relay error: %s", e)
    return result

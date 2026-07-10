"""Push natif Android via Firebase Cloud Messaging (FCM).

Désactivé silencieusement si backend/firebase-admin.json est absent
(ou si FIREBASE_CREDENTIALS ne pointe pas vers un fichier valide).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_app = None
_init_tried = False


def _credentials_path() -> Path:
    env = os.environ.get("FIREBASE_CREDENTIALS")
    if env:
        return Path(env)
    return Path(__file__).parent / "firebase-admin.json"


def _get_app():
    global _app, _init_tried
    if _app is not None:
        return _app
    if _init_tried:
        return None
    _init_tried = True
    path = _credentials_path()
    if not path.exists():
        logger.info("FCM désactivé : credentials absents (%s)", path)
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials

        _app = firebase_admin.initialize_app(credentials.Certificate(str(path)))
        logger.info("FCM initialisé (projet %s)", _app.project_id)
    except Exception as e:
        logger.warning("FCM init échoué : %s", e)
        _app = None
    return _app


def available() -> bool:
    return _get_app() is not None


async def save_token(db, token: str, user_id: Optional[str] = None) -> Dict:
    doc = {
        "id": str(uuid.uuid4()),
        "token": token,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fcm_tokens.update_one({"token": token}, {"$set": doc}, upsert=True)
    logger.info("FCM token enregistré (user_id=%s, token=%s…)", user_id, token[:16])
    return doc


async def remove_token(db, token: str) -> int:
    res = await db.fcm_tokens.delete_one({"token": token})
    return res.deleted_count


async def send_to_all(db, title: str, body: str, url: str = "/", tag: str = "storm") -> Dict:
    """Envoie une notification FCM à tous les tokens Android enregistrés.
    Purge les tokens invalides/expirés. Envoi non bloquant (to_thread).
    """
    app = _get_app()
    if app is None:
        logger.info("FCM send_to_all ignoré : SDK non initialisé")
        return {"sent": 0, "total": 0, "disabled": True}
    docs = await db.fcm_tokens.find({}, {"_id": 0, "token": 1}).to_list(2000)
    tokens = [d["token"] for d in docs]
    if not tokens:
        logger.info("FCM send_to_all : aucun token Android enregistré")
        return {"sent": 0, "total": 0}
    logger.info("FCM envoi vers %d appareils · titre=%r", len(tokens), title)

    from firebase_admin import messaging

    def _send():
        msg = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="storm_alerts",
                    sound="default",
                    tag=tag,
                ),
            ),
            data={"url": url, "tag": tag},
        )
        return messaging.send_each_for_multicast(msg)

    resp = await asyncio.to_thread(_send)

    removed = 0
    errors = 0
    for tok, r in zip(tokens, resp.responses):
        if r.success:
            continue
        err = str(r.exception).lower()
        if "not-registered" in err or "not registered" in err or "not a valid" in err or "invalid" in err:
            await db.fcm_tokens.delete_one({"token": tok})
            removed += 1
        else:
            errors += 1
            logger.warning("FCM erreur d'envoi : %s", r.exception)
    logger.info(
        "FCM résultat · envoyés=%d purgés=%d erreurs=%d total=%d",
        resp.success_count, removed, errors, len(tokens),
    )
    return {"sent": resp.success_count, "removed": removed, "errors": errors, "total": len(tokens)}

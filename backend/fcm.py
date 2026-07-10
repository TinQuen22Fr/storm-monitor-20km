"""Push natif Android via Firebase Cloud Messaging (FCM).

Désactivé si backend/firebase-admin.json est absent (ou si FIREBASE_CREDENTIALS
ne pointe pas vers un fichier valide). L'init est retentée à chaque appel tant
qu'elle n'a pas réussi : déposer la clé PUIS restart n'est plus obligatoire,
le fichier est pris en compte dès qu'il apparaît.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_app = None
_last_error: Optional[str] = None
_last_missing_logged = False


def _credentials_path() -> Path:
    env = os.environ.get("FIREBASE_CREDENTIALS")
    if env:
        return Path(env)
    return Path(__file__).parent / "firebase-admin.json"


def _get_app():
    """Init Firebase Admin. Retente à chaque appel tant que non initialisé."""
    global _app, _last_error, _last_missing_logged
    if _app is not None:
        return _app
    path = _credentials_path()
    if not path.exists():
        _last_error = f"credentials absents ({path})"
        if not _last_missing_logged:
            logger.info("FCM désactivé : credentials absents (%s)", path)
            _last_missing_logged = True
        return None
    _last_missing_logged = False
    try:
        import firebase_admin
        from firebase_admin import credentials

        _app = firebase_admin.initialize_app(credentials.Certificate(str(path)))
        _last_error = None
        logger.info("FCM initialisé (projet %s)", _app.project_id)
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        logger.warning("FCM init échoué : %s", _last_error)
        _app = None
    return _app


def available() -> bool:
    return _get_app() is not None


def diagnose() -> Dict:
    """État complet de la chaîne FCM côté serveur (aucun secret exposé)."""
    path = _credentials_path()
    d: Dict = {
        "credentials_path": str(path),
        "file_exists": path.exists(),
        "file_readable": False,
        "valid_json": False,
        "project_id": None,
        "sdk_installed": False,
        "sdk_version": None,
        "initialized": False,
        "last_error": None,
    }
    if d["file_exists"]:
        try:
            raw = path.read_text()
            d["file_readable"] = True
            data = json.loads(raw)
            d["valid_json"] = True
            d["project_id"] = data.get("project_id")
            if not data.get("private_key"):
                d["last_error"] = "champ private_key absent du JSON"
        except PermissionError:
            d["last_error"] = "fichier illisible (droits)"
        except json.JSONDecodeError as e:
            d["last_error"] = f"JSON invalide : {e}"
        except Exception as e:
            d["last_error"] = str(e)
    else:
        d["last_error"] = "fichier credentials absent"
    try:
        import firebase_admin

        d["sdk_installed"] = True
        d["sdk_version"] = getattr(firebase_admin, "__version__", "?")
    except ImportError:
        d["last_error"] = "module python firebase_admin non installé (pip)"
    d["initialized"] = available()
    if d["initialized"]:
        d["last_error"] = None
    elif _last_error and not d["last_error"]:
        d["last_error"] = _last_error
    return d


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
        logger.info("FCM send_to_all ignoré : SDK non initialisé (%s)", _last_error)
        return {"sent": 0, "total": 0, "disabled": True, "reason": _last_error}
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

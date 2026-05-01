"""Discord + Telegram webhook dispatcher for storm alerts.

Configuration via environment variables (all optional — if missing, the
corresponding channel is simply disabled silently):

    DISCORD_WEBHOOK_URL     — https://discord.com/api/webhooks/<id>/<token>
    TELEGRAM_BOT_TOKEN      — bot token from @BotFather
    TELEGRAM_CHAT_ID        — numeric chat id (channel, group, or DM id)
    WEBHOOK_APP_URL         — public URL inserted in every message (default:
                              https://storm-monitor.quentin-astro.fr)

Anti-spam: per-tag cooldown in memory so the same event category (e.g.
"storm-approach") can't flood more than once per WEBHOOK_COOLDOWN_S (default
900 s = 15 min). Cooldown is reset automatically, no persistence needed.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# In-memory cooldown state: tag → last_sent_epoch
_cooldowns: Dict[str, float] = {}
_cooldown_lock = asyncio.Lock()


def _app_url() -> str:
    return os.environ.get("WEBHOOK_APP_URL", "https://storm-monitor.quentin-astro.fr")


def _cooldown_s() -> int:
    try:
        return int(os.environ.get("WEBHOOK_COOLDOWN_S", "900"))
    except ValueError:
        return 900


def _discord_url() -> Optional[str]:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    return url if url.startswith("https://discord.com/api/webhooks/") else None


def _telegram_config() -> Optional[tuple[str, str]]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        return token, chat
    return None


# -- Per-tag color & emoji used for Discord embeds / Telegram icons --
TAG_STYLE = {
    "storm-active": {"emoji": "🌩️", "color": 0xDC2626, "title_prefix": "Alerte orage"},
    "storm-approach": {"emoji": "⚠️", "color": 0xEA580C, "title_prefix": "Orage en approche"},
    "lightning-strike": {"emoji": "⚡", "color": 0xF59E0B, "title_prefix": "Impacts de foudre"},
    "vigilance-orange": {"emoji": "🟠", "color": 0xEA580C, "title_prefix": "Vigilance orange"},
    "vigilance-rouge": {"emoji": "🔴", "color": 0x991B1B, "title_prefix": "Vigilance rouge"},
    "test": {"emoji": "✅", "color": 0x0F172A, "title_prefix": "Test webhook"},
}


def _style_for(tag: str) -> Dict[str, Any]:
    return TAG_STYLE.get(tag, {
        "emoji": "⚡",
        "color": 0x0F172A,
        "title_prefix": "Storm Monitoring",
    })


async def _check_cooldown(tag: str) -> bool:
    """Return True if the tag is currently throttled (skip send)."""
    now = time.time()
    async with _cooldown_lock:
        last = _cooldowns.get(tag, 0)
        if now - last < _cooldown_s():
            return True
        _cooldowns[tag] = now
    return False


async def _send_discord(title: str, body: str, tag: str) -> Optional[Dict[str, Any]]:
    url = _discord_url()
    if not url:
        return None
    style = _style_for(tag)
    payload = {
        "username": "Storm Monitoring",
        "embeds": [{
            "title": f"{style['emoji']} {title}",
            "description": body,
            "color": style["color"],
            "url": _app_url(),
            "footer": {"text": "storm-monitor.quentin-astro.fr · Quentin Dumont"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, json=payload)
            if r.status_code >= 400:
                logger.warning("Discord webhook %s returned %s: %s", tag, r.status_code, r.text[:200])
                return {"ok": False, "status": r.status_code, "body": r.text[:200]}
            return {"ok": True, "status": r.status_code}
    except Exception as e:
        logger.exception("Discord webhook failed for tag=%s", tag)
        return {"ok": False, "error": str(e)}


async def _send_telegram(title: str, body: str, tag: str) -> Optional[Dict[str, Any]]:
    conf = _telegram_config()
    if not conf:
        return None
    token, chat = conf
    style = _style_for(tag)
    # Telegram supports basic HTML: <b>, <i>, <a href>, <code>
    text = (
        f"{style['emoji']} <b>{title}</b>\n"
        f"{body}\n"
        f'<a href="{_app_url()}">Ouvrir Storm Monitoring</a>'
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, json=payload)
            if r.status_code >= 400:
                logger.warning("Telegram webhook %s returned %s: %s", tag, r.status_code, r.text[:200])
                return {"ok": False, "status": r.status_code, "body": r.text[:200]}
            return {"ok": True, "status": r.status_code}
    except Exception as e:
        logger.exception("Telegram webhook failed for tag=%s", tag)
        return {"ok": False, "error": str(e)}


async def dispatch(title: str, body: str, tag: str, force: bool = False) -> Dict[str, Any]:
    """Fire a webhook notification on all configured channels.

    Respects per-tag cooldown unless `force=True`. Returns a dict with per-channel
    status (or None for disabled channels).
    """
    if not force and await _check_cooldown(tag):
        return {"skipped": "cooldown", "tag": tag}

    discord_res, telegram_res = await asyncio.gather(
        _send_discord(title, body, tag),
        _send_telegram(title, body, tag),
    )
    return {"discord": discord_res, "telegram": telegram_res, "tag": tag}


def status() -> Dict[str, Any]:
    """Return which channels are configured (no secrets leaked)."""
    return {
        "discord_enabled": _discord_url() is not None,
        "telegram_enabled": _telegram_config() is not None,
        "cooldown_s": _cooldown_s(),
        "app_url": _app_url(),
        "active_cooldowns": {
            tag: round(max(0.0, _cooldown_s() - (time.time() - ts)), 0)
            for tag, ts in _cooldowns.items()
            if time.time() - ts < _cooldown_s()
        },
    }

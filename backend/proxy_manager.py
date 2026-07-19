"""Gestion dynamique de proxies pour contourner le rate-limit Open-Meteo (429).

Logique de failover :
  1. Priorité 1 : requête directe avec l'IP réelle du serveur (Kimsufi).
  2. Sur 429 : bascule immédiate vers le proxy le plus rapide/valide de
     `proxies.json` (health-check préalable de tous les candidats).
  3. Rotation : le proxy choisi reste actif STICKY_DURATION_S (30 min),
     puis retour à l'IP principale.
  4. Auto-maintenance : un proxy en erreur (hors 429) est marqué « suspect »
     et écarté de la sélection pendant SUSPECT_COOLDOWN_S.

Format de `proxies.json` (voir proxies.example.json) :
  [ { "ip": "x.x.x.x", "port": 8080, "type": "http" }, ... ]
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

PROXIES_FILE = Path(__file__).parent / "proxies.json"

# Requête légère pour le health-check : 1 point, 1 variable current.
# Passer par Open-Meteo valide à la fois le proxy ET son quota propre.
HEALTH_URL = "https://api.open-meteo.com/v1/forecast"
HEALTH_PARAMS = {"latitude": 43.1, "longitude": -0.04, "current": "temperature_2m"}

STICKY_DURATION_S = 30 * 60      # durée d'utilisation d'un proxy avant retest IP principale
SUSPECT_COOLDOWN_S = 15 * 60     # mise à l'écart d'un proxy en erreur
HEALTH_TIMEOUT_S = 5.0           # au-delà = proxy trop lent → ignoré

_proxies: List[Dict[str, Any]] = []
_file_mtime: float = 0.0
_state: Dict[str, Dict[str, float]] = {}   # url → {suspect_until, latency, last_ok}
_active: Dict[str, Any] = {"url": None, "until": 0.0}
_failover_lock = asyncio.Lock()


def _proxy_url(p: Dict[str, Any]) -> str:
    return f"{p['type']}://{p['ip']}:{p['port']}"


def _load_proxies() -> List[Dict[str, Any]]:
    """(Re)charge proxies.json si le fichier a changé — éditable à chaud."""
    global _proxies, _file_mtime
    try:
        mtime = PROXIES_FILE.stat().st_mtime if PROXIES_FILE.exists() else 0.0
        if mtime != _file_mtime:
            _file_mtime = mtime
            raw = json.loads(PROXIES_FILE.read_text(encoding="utf-8")) if PROXIES_FILE.exists() else []
            _proxies = [
                p for p in raw
                if isinstance(p, dict) and p.get("ip") and p.get("port")
                and str(p.get("type", "http")).lower() in ("http", "https", "socks5")
            ]
            for p in _proxies:
                p["type"] = str(p.get("type", "http")).lower()
            logger.info("Proxies : %d entrée(s) chargée(s) depuis %s", len(_proxies), PROXIES_FILE.name)
    except Exception as e:
        logger.warning("Proxies : lecture de %s impossible (%s)", PROXIES_FILE.name, e)
    return _proxies


def current_proxy_url() -> Optional[str]:
    """URL du proxy sticky en cours, ou None = IP principale (Kimsufi)."""
    if _active["url"] and time.time() < _active["until"]:
        return _active["url"]
    if _active["url"]:
        logger.info("Proxies : fin de rotation — retour à l'IP principale")
        _active["url"] = None
    return None


def mark_suspect(url: str, reason: str = "erreur") -> None:
    """Auto-maintenance : écarte un proxy défaillant de la sélection."""
    st = _state.setdefault(url, {})
    st["suspect_until"] = time.time() + SUSPECT_COOLDOWN_S
    if _active["url"] == url:
        _active["url"] = None
    logger.warning("Proxies : %s marqué suspect (%s) — écarté %d min",
                   url, reason, SUSPECT_COOLDOWN_S // 60)


async def _health_check(url: str) -> Optional[float]:
    """Ping léger via le proxy. Retourne la latence (s) ou None si mort/lent."""
    t0 = time.time()
    try:
        async with httpx.AsyncClient(proxy=url, timeout=HEALTH_TIMEOUT_S) as client:
            r = await client.get(HEALTH_URL, params=HEALTH_PARAMS)
        if r.status_code == 200:
            return time.time() - t0
        if r.status_code == 429:
            mark_suspect(url, "429 sur health-check")
        return None
    except Exception:
        return None


async def on_rate_limited(exclude_url: Optional[str] = None) -> Optional[str]:
    """Appelé sur un 429 : health-check des candidats, sélection du plus rapide,
    activation sticky 30 min. Retourne l'URL choisie ou None (aucun proxy valide)."""
    if exclude_url:
        mark_suspect(exclude_url, "429")
    async with _failover_lock:
        # Un autre appel concurrent a peut-être déjà basculé
        cur = current_proxy_url()
        if cur and cur != exclude_url:
            return cur
        now = time.time()
        candidates = [
            _proxy_url(p) for p in _load_proxies()
            if _proxy_url(p) != exclude_url
            and _state.get(_proxy_url(p), {}).get("suspect_until", 0) < now
        ]
        if not candidates:
            return None
        results = await asyncio.gather(*(_health_check(u) for u in candidates))
        alive = [(lat, u) for lat, u in zip(results, candidates) if lat is not None]
        if not alive:
            logger.warning("Proxies : aucun proxy valide parmi %d candidat(s)", len(candidates))
            return None
        latency, best = min(alive)
        _state.setdefault(best, {})["latency"] = round(latency, 2)
        _state[best]["last_ok"] = now
        _active["url"] = best
        _active["until"] = now + STICKY_DURATION_S
        logger.info("Proxies : bascule sur %s (latence %.2fs) pour %d min",
                    best, latency, STICKY_DURATION_S // 60)
        return best


def _mask(ip: str) -> str:
    parts = str(ip).split(".")
    return ".".join(parts[:2] + ["x", "x"]) if len(parts) == 4 else ip[:6] + "…"


def status() -> Dict[str, Any]:
    """Diagnostic (IP masquées) pour /api/proxy/status."""
    now = time.time()
    proxies = _load_proxies()
    active = current_proxy_url()
    return {
        "proxies_configured": len(proxies),
        "active_proxy": _mask(active.split("://")[1].split(":")[0]) if active else None,
        "using_main_ip": active is None,
        "sticky_remaining_s": max(0, int(_active["until"] - now)) if active else 0,
        "proxies": [
            {
                "ip": _mask(p["ip"]),
                "port": p["port"],
                "type": p["type"],
                "suspect": _state.get(_proxy_url(p), {}).get("suspect_until", 0) > now,
                "latency_s": _state.get(_proxy_url(p), {}).get("latency"),
            }
            for p in proxies
        ],
    }

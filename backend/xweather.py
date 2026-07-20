"""Xweather (Vaisala) fallback client for storm zones + wind grid.

Activé uniquement quand Open-Meteo échoue (429/timeout/erreur réseau).
Retourne exactement le même schéma JSON que weather.fetch_storm_zones /
weather.fetch_wind_grid pour rester transparent côté frontend.

Notes:
- La clé fournie est au format combiné `<client_id>_<client_secret>`
  (documenté pour MCP / Raster Maps) mais l'API Weather (/forecasts)
  attend les 2 paramètres SÉPARÉS en query string. On splitte au load.
- Pas de CAPE ni de lightning_potential dans /forecasts Xweather : on
  laisse 0.0 et on dérive `severity` uniquement depuis pluie/vent/orage.

Futures capacités possibles (non implémentées ici, à voir plus tard) :
- /airquality/    → indice AQI (pollution air)
- Raster tiles    → cartes vent/radar animées (MapsGL SDK côté front)
- /lightning/     → redondance possible avec Blitzortung
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import httpx

logger = logging.getLogger(__name__)

XWEATHER_BASE = "https://data.api.xweather.com"

# Weather Primary Coded fragments indicating thunderstorm activity
# Xweather utilise un code sous la forme "intensity:descriptor:type"
# ex: "L:T" (light thunderstorms), ":T" (thunderstorm), "H:T:R" ...
_THUNDER_TOKENS = (":T", ":TS", ":TSRA")


def _load_credentials() -> Tuple[str, str] | None:
    """Retourne (client_id, client_secret) ou None si non configuré."""
    combined = os.environ.get("XWEATHER_COMBINED_TOKEN", "").strip()
    if not combined or "_" not in combined:
        return None
    cid, secret = combined.split("_", 1)
    if not cid or not secret:
        return None
    return cid, secret


def is_configured() -> bool:
    return _load_credentials() is not None


def _is_thunder(period: Dict[str, Any]) -> bool:
    code = str(period.get("weatherPrimaryCoded") or "")
    if any(tok in code for tok in _THUNDER_TOKENS):
        return True
    primary = str(period.get("weatherPrimary") or "").lower()
    return "thunder" in primary


async def _fetch_point_hour(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    cid: str,
    secret: str,
) -> Dict[str, Any] | None:
    """Récupère UNE prévision horaire (l'heure courante) pour un point."""
    url = f"{XWEATHER_BASE}/forecasts/{lat},{lon}"
    params = {
        "client_id": cid,
        "client_secret": secret,
        "filter": "1hr",
        "limit": 1,
    }
    try:
        r = await client.get(url, params=params, timeout=10.0)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("Xweather point %.3f,%.3f failed: %s", lat, lon, exc)
        return None
    if not data.get("success"):
        logger.warning("Xweather point %.3f,%.3f non-success: %s", lat, lon, data.get("error"))
        return None
    responses = data.get("response") or []
    if not responses:
        return None
    periods = responses[0].get("periods") or []
    if not periods:
        return None
    return periods[0]


async def _fetch_all_points(points: List[Dict[str, float]]) -> List[Dict[str, Any] | None]:
    creds = _load_credentials()
    if creds is None:
        raise RuntimeError("Xweather credentials not configured (XWEATHER_COMBINED_TOKEN missing)")
    cid, secret = creds
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_point_hour(client, p["lat"], p["lon"], cid, secret) for p in points]
        return await asyncio.gather(*tasks)


async def fetch_zones_xweather(
    points: List[Dict[str, float]],
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> Dict[str, Any]:
    """Fallback zones — même format que weather.fetch_storm_zones."""
    results = await _fetch_all_points(points)
    zones: List[Dict[str, Any]] = []
    for p, period in zip(points, results):
        if period is None:
            zones.append({
                "lat": p["lat"], "lon": p["lon"], "weather_code": 0,
                "precipitation": 0.0, "wind_gust": 0.0, "cape": 0.0,
                "lightning_potential": 0.0, "is_thunder": False, "severity": 0,
            })
            continue
        precip = float(period.get("precipMM") or 0)
        gust = float(period.get("windGustKPH") or 0) / 3.6  # kph -> m/s
        is_thunder = _is_thunder(period)
        # Severity dérivée sans CAPE : pluie x8 + rafale x2 + bonus orage
        severity = min(100, int(precip * 8 + gust * 2 + (30 if is_thunder else 0)))
        # Mapping approx code Open-Meteo pour compat frontend
        wcode = 95 if is_thunder else (61 if precip > 0.5 else 0)
        zones.append({
            "lat": p["lat"], "lon": p["lon"], "weather_code": wcode,
            "precipitation": round(precip, 2),
            "wind_gust": round(gust, 1),
            "cape": 0.0,
            "lightning_potential": 0.0,
            "is_thunder": is_thunder,
            "severity": severity,
        })
    return {
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_km": radius_km,
        "zones": zones,
        "storm_active": any(z["is_thunder"] or z["severity"] >= 40 for z in zones),
        "max_cape": 0.0,
        "max_lightning_potential": 0.0,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "xweather-fallback",
    }


async def fetch_wind_xweather(
    points: List[Dict[str, float]],
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> Dict[str, Any]:
    """Fallback flèches de vent — même format que weather.fetch_wind_grid."""
    results = await _fetch_all_points(points)
    arrows: List[Dict[str, Any]] = []
    max_speed = 0.0
    for p, period in zip(points, results):
        if period is None:
            arrows.append({"lat": p["lat"], "lon": p["lon"], "speed": 0.0, "direction": 0.0, "gust": 0.0})
            continue
        speed_kph = float(period.get("windSpeedKPH") or 0)
        gust_kph = float(period.get("windGustKPH") or 0)
        direction = float(period.get("windDirDEG") or 0)
        speed_ms = speed_kph / 3.6
        gust_ms = gust_kph / 3.6
        arrows.append({
            "lat": p["lat"], "lon": p["lon"],
            "speed": round(speed_ms, 1),
            "direction": round(direction, 0),
            "gust": round(gust_ms, 1),
        })
        if speed_ms > max_speed:
            max_speed = speed_ms
    return {
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_km": radius_km,
        "arrows": arrows,
        "max_speed": round(max_speed, 1),
        "source": "xweather-fallback",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

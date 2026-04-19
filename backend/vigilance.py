"""Official vigilance from Météo-France via MeteoAlarm feed.

MeteoAlarm is the official European consortium aggregator of national weather
services, including Météo-France. The feed at
https://feeds.meteoalarm.org/api/v1/warnings/feeds-france returns the SAME
vigilance data shown on https://vigilance.meteofrance.fr — fully open-data,
no key required.

If MeteoAlarm is unavailable, we fall back to a locally-computed Open-Meteo
assessment so the banner is never empty.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import httpx

from weather import _cached, OPEN_METEO_BASE, get_with_retry

logger = logging.getLogger(__name__)

METEOALARM_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-france"

LEVELS_FR = {1: "vert", 2: "jaune", 3: "orange", 4: "rouge"}
LEVEL_COLORS = {
    1: "#10B981",
    2: "#F59E0B",
    3: "#EA580C",
    4: "#DC2626",
}
LEVEL_LABELS = {
    1: "Pas de vigilance particulière",
    2: "Soyez attentif",
    3: "Soyez très vigilant",
    4: "Vigilance absolue",
}

# MeteoAlarm awareness_type code → our phenomenon key
AWARENESS_TYPE_MAP = {
    "1": "vent",             # Wind
    "2": "neige",            # Snow/Ice
    "3": "orage",            # Thunderstorm
    "4": "brouillard",       # Fog
    "5": "grand-froid",      # Extreme low temp
    "6": "canicule",         # Extreme high temp
    "7": "neige",            # Coastal event (partial)
    "8": "pluie",             # Rain/flood
    "9": "pluie",             # Flood
    "10": "pluie",            # Rain
    "11": "avalanche",       # Avalanche
    "12": "vent",             # Strong wind on sea
}

PHENOMENA_META = [
    ("orage", "Orages", "⚡"),
    ("vent", "Vent violent", "🌬"),
    ("pluie", "Pluie-inondation", "🌧"),
    ("canicule", "Canicule", "🔥"),
    ("grand-froid", "Grand froid", "❄"),
    ("neige", "Neige-verglas", "🌨"),
    ("brouillard", "Brouillard", "🌫"),
    ("avalanche", "Avalanches", "🗻"),
]

# Lourdes dept (65) + neighbours. NUTS3 codes come from MeteoAlarm (FRxxx).
LOURDES_DEPTS = [
    {"id": "65", "name": "Hautes-Pyrénées", "nuts3": "FR626", "lat": 43.0951, "lon": 0.15},
    {"id": "64", "name": "Pyrénées-Atlantiques", "nuts3": "FR615", "lat": 43.30, "lon": -0.75},
    {"id": "32", "name": "Gers", "nuts3": "FR624", "lat": 43.65, "lon": 0.58},
    {"id": "31", "name": "Haute-Garonne", "nuts3": "FR623", "lat": 43.48, "lon": 1.2},
    {"id": "09", "name": "Ariège", "nuts3": "FR621", "lat": 42.95, "lon": 1.48},
    {"id": "66", "name": "Pyrénées-Orientales", "nuts3": "FR815", "lat": 42.60, "lon": 2.55},
    {"id": "40", "name": "Landes", "nuts3": "FR613", "lat": 43.95, "lon": -0.80},
]

# Awareness_level: "1; green", "2; yellow", "3; orange", "4; red"
def _parse_awareness_level(val: str) -> int:
    if not val:
        return 1
    first = val.split(";")[0].strip()
    try:
        return max(1, min(4, int(first)))
    except ValueError:
        return 1


def _now_epoch() -> float:
    return time.time()


def _parse_iso(s: str) -> float:
    """Parse ISO 8601 with timezone → epoch seconds."""
    from datetime import datetime
    try:
        # Python 3.11+ accepts +02:00 directly
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


async def _fetch_meteoalarm() -> Dict[str, Any]:
    """Fetch and cache the MeteoAlarm France feed (TTL 15 min)."""
    async def _do() -> Dict[str, Any]:
        r = await get_with_retry(
            METEOALARM_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Lourdes-Storm-Tracker)",
                "Accept": "application/json",
            },
            timeout=12.0,
        )
        return r.json()

    return await _cached("vigilance:meteoalarm", ttl=900.0, fn=_do)


def _extract_dept_alerts(data: Dict[str, Any], nuts3: str) -> List[Dict[str, Any]]:
    """Return per-phenomenon max level for a given NUTS3 dept, valid NOW or NEXT 24H."""
    now = _now_epoch()
    horizon = now + 24 * 3600

    per_phen: Dict[str, Dict[str, Any]] = {}

    for w in data.get("warnings", []):
        alert = w.get("alert", {})
        for info in alert.get("info", []):
            # Only fr-FR to avoid duplicates
            if info.get("language") != "fr-FR":
                continue
            # Check if this area applies
            areas = info.get("area", [])
            matches = False
            for area in areas:
                for g in area.get("geocode", []):
                    if g.get("valueName") == "NUTS3" and g.get("value") == nuts3:
                        matches = True
                        break
                if matches:
                    break
            if not matches:
                continue

            effective = _parse_iso(info.get("effective", ""))
            expires = _parse_iso(info.get("expires", ""))
            # Only keep alerts currently active or starting within 24h
            if expires and expires < now:
                continue
            if effective and effective > horizon:
                continue

            params = {p["valueName"]: p["value"] for p in info.get("parameter", [])}
            lvl = _parse_awareness_level(params.get("awareness_level", ""))
            awareness_type = params.get("awareness_type", "").split(";")[0].strip()
            phen_key = AWARENESS_TYPE_MAP.get(awareness_type)
            if not phen_key:
                continue

            # Keep max level for this phenomenon
            cur = per_phen.get(phen_key)
            if not cur or lvl > cur["level"]:
                per_phen[phen_key] = {
                    "level": lvl,
                    "event": info.get("event", ""),
                    "description": info.get("description", ""),
                    "effective": info.get("effective", ""),
                    "expires": info.get("expires", ""),
                }

    return per_phen


def _build_phenomena(per_phen: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for key, label, icon in PHENOMENA_META:
        data = per_phen.get(key, {"level": 1})
        lvl = data.get("level", 1)
        items.append({
            "key": key,
            "label": label,
            "icon": icon,
            "level": lvl,
            "level_fr": LEVELS_FR[lvl],
            "color": LEVEL_COLORS[lvl],
            "today": lvl,  # MeteoAlarm active-now
            "tomorrow": lvl,  # Same horizon window
            "event": data.get("event"),
            "description": data.get("description"),
        })
    return items


async def _compute_from_meteoalarm() -> Dict[str, Any]:
    data = await _fetch_meteoalarm()

    results: List[Dict[str, Any]] = []
    for dept in LOURDES_DEPTS:
        per_phen = _extract_dept_alerts(data, dept["nuts3"])
        phenomena = _build_phenomena(per_phen)
        max_level = max((p["level"] for p in phenomena), default=1)
        results.append({
            "id": dept["id"],
            "name": dept["name"],
            "nuts3": dept["nuts3"],
            "lat": dept["lat"],
            "lon": dept["lon"],
            "phenomena": phenomena,
            "max_level": max_level,
            "max_level_fr": LEVELS_FR[max_level],
            "max_color": LEVEL_COLORS[max_level],
            "max_label": LEVEL_LABELS[max_level],
        })

    overall = max((r["max_level"] for r in results), default=1)
    return {
        "updated_at": int(time.time()),
        "source": "meteoalarm",
        "source_label": "Météo-France (via MeteoAlarm)",
        "source_url": "https://vigilance.meteofrance.fr/",
        "disclaimer": "Vigilance officielle Météo-France agrégée par MeteoAlarm (EUMETNET).",
        "phenomena_meta": [{"key": k, "label": label, "icon": icon} for k, label, icon in PHENOMENA_META],
        "levels_meta": [
            {"level": lv, "name": LEVELS_FR[lv], "color": LEVEL_COLORS[lv], "label": LEVEL_LABELS[lv]}
            for lv in (1, 2, 3, 4)
        ],
        "departements": results,
        "overall_level": overall,
        "overall_level_fr": LEVELS_FR[overall],
        "overall_color": LEVEL_COLORS[overall],
        "overall_label": LEVEL_LABELS[overall],
    }


# ---------- Open-Meteo fallback (used only if MeteoAlarm fails) ----------

def _thunder_level(weather_codes, cape_max, gust_max):
    thunder_hours = sum(1 for c in weather_codes if c in {95, 96, 99})
    if thunder_hours >= 3 and cape_max >= 2500:
        return 4
    if thunder_hours >= 2 or (cape_max >= 2000 and thunder_hours >= 1):
        return 3
    if thunder_hours >= 1 or cape_max >= 1500:
        return 2
    return 1


async def _compute_from_openmeteo_fallback() -> Dict[str, Any]:
    """Very simplified fallback; used only if MeteoAlarm is unreachable."""
    async def _do():
        lats = ",".join(f"{d['lat']}" for d in LOURDES_DEPTS)
        lons = ",".join(f"{d['lon']}" for d in LOURDES_DEPTS)
        params = {
            "latitude": lats, "longitude": lons,
            "hourly": "weather_code,cape",
            "daily": "weather_code,wind_gusts_10m_max,cape_max",
            "forecast_days": 1, "timezone": "auto",
        }
        r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15.0)
        payload = r.json()
        return payload if isinstance(payload, list) else [payload]

    data_list = await _do()
    if isinstance(data_list, dict):
        data_list = [data_list]

    results = []
    for i, dept in enumerate(LOURDES_DEPTS):
        data = data_list[i] if i < len(data_list) else {}
        hourly = data.get("hourly", {}).get("weather_code", [])[:24]
        cape_h = data.get("hourly", {}).get("cape", [])[:24]
        cape_max = max([float(c or 0) for c in cape_h], default=0)
        gust_max = float((data.get("daily", {}).get("wind_gusts_10m_max") or [0])[0] or 0)
        orage_lvl = _thunder_level(hourly, cape_max, gust_max)
        phenomena = [
            {
                "key": k, "label": label, "icon": icon,
                "level": orage_lvl if k == "orage" else 1,
                "level_fr": LEVELS_FR[orage_lvl if k == "orage" else 1],
                "color": LEVEL_COLORS[orage_lvl if k == "orage" else 1],
                "today": orage_lvl if k == "orage" else 1,
                "tomorrow": orage_lvl if k == "orage" else 1,
            }
            for k, label, icon in PHENOMENA_META
        ]
        max_level = max((p["level"] for p in phenomena), default=1)
        results.append({
            "id": dept["id"], "name": dept["name"], "nuts3": dept["nuts3"],
            "lat": dept["lat"], "lon": dept["lon"],
            "phenomena": phenomena,
            "max_level": max_level,
            "max_level_fr": LEVELS_FR[max_level],
            "max_color": LEVEL_COLORS[max_level],
            "max_label": LEVEL_LABELS[max_level],
        })

    overall = max((r["max_level"] for r in results), default=1)
    return {
        "updated_at": int(time.time()),
        "source": "open-meteo-fallback",
        "source_label": "Estimation locale Open-Meteo (fallback)",
        "source_url": "https://vigilance.meteofrance.fr/",
        "disclaimer": "Source officielle MeteoAlarm temporairement indisponible — estimation locale.",
        "phenomena_meta": [{"key": k, "label": label, "icon": icon} for k, label, icon in PHENOMENA_META],
        "levels_meta": [
            {"level": lv, "name": LEVELS_FR[lv], "color": LEVEL_COLORS[lv], "label": LEVEL_LABELS[lv]}
            for lv in (1, 2, 3, 4)
        ],
        "departements": results,
        "overall_level": overall,
        "overall_level_fr": LEVELS_FR[overall],
        "overall_color": LEVEL_COLORS[overall],
        "overall_label": LEVEL_LABELS[overall],
    }


async def compute_vigilance() -> Dict[str, Any]:
    """Primary: MeteoAlarm (official MF). Fallback: Open-Meteo estimation."""
    try:
        return await _compute_from_meteoalarm()
    except Exception as e:
        logger.warning("MeteoAlarm fetch failed, falling back to Open-Meteo: %s", e)
        try:
            return await _compute_from_openmeteo_fallback()
        except Exception as e2:
            logger.error("Both vigilance sources failed: %s / %s", e, e2)
            raise

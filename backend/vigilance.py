"""Compute a Météo-France-style "Vigilance" bulletin from Open-Meteo data.

We cannot hit Météo-France public API from this sandbox (Akamai bot-wall +
token required). So we compute our own 4-level color assessment for the
standard Météo-France phenomena around Lourdes (dept 65 + neighbours):

  - Orages              (thunderstorm)
  - Vent violent        (wind)
  - Pluie-inondation    (rain-flood)
  - Canicule            (heatwave)
  - Grand froid         (extreme cold)
  - Neige-verglas       (snow/ice)

Levels match Météo-France colours:
  1 = vert (no vigilance)
  2 = jaune (be aware)
  3 = orange (be very vigilant)
  4 = rouge (absolute vigilance)
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

import httpx

from weather import _cached, OPEN_METEO_BASE

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


def _thunder_level(weather_codes: List[int], cape_max: float, wind_gusts: float) -> int:
    thunder_hours = sum(1 for c in weather_codes if c in {95, 96, 99})
    if thunder_hours >= 3 and cape_max >= 2500:
        return 4
    if thunder_hours >= 2 or (cape_max >= 2000 and thunder_hours >= 1):
        return 3
    if thunder_hours >= 1 or cape_max >= 1500:
        return 2
    return 1


def _wind_level(gust_max: float) -> int:
    if gust_max >= 130:
        return 4
    if gust_max >= 100:
        return 3
    if gust_max >= 70:
        return 2
    return 1


def _rain_level(precip_sum_mm: float, precip_hours: int) -> int:
    # Based on Météo-France broad criteria (cumulatives)
    if precip_sum_mm >= 100 or (precip_sum_mm >= 60 and precip_hours >= 6):
        return 4
    if precip_sum_mm >= 50:
        return 3
    if precip_sum_mm >= 25:
        return 2
    return 1


def _heat_level(t_max: float) -> int:
    if t_max >= 40:
        return 4
    if t_max >= 36:
        return 3
    if t_max >= 32:
        return 2
    return 1


def _cold_level(t_min: float) -> int:
    if t_min <= -15:
        return 4
    if t_min <= -10:
        return 3
    if t_min <= -5:
        return 2
    return 1


def _snow_level(snow_cm: float, weather_codes: List[int]) -> int:
    ice_codes = {56, 57, 66, 67}
    ice_hours = sum(1 for c in weather_codes if c in ice_codes)
    if snow_cm >= 20 or ice_hours >= 4:
        return 4
    if snow_cm >= 10 or ice_hours >= 2:
        return 3
    if snow_cm >= 3 or ice_hours >= 1:
        return 2
    return 1


PHENOMENA_META = [
    ("orage", "Orages", "⚡"),
    ("vent", "Vent violent", "🌬"),
    ("pluie", "Pluie-inondation", "🌧"),
    ("canicule", "Canicule", "🔥"),
    ("grand-froid", "Grand froid", "❄"),
    ("neige", "Neige-verglas", "🌨"),
]


async def _fetch_open_meteo(lat: float, lon: float) -> Dict[str, Any]:
    async def _do() -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "weather_code,cape",
            "daily": "weather_code,wind_gusts_10m_max,precipitation_sum,precipitation_hours,"
                     "temperature_2m_max,temperature_2m_min,cape_max,snowfall_sum",
            "forecast_days": 2,
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(OPEN_METEO_BASE, params=params)
            r.raise_for_status()
            return r.json()

    return await _cached(f"vigilance:{lat:.3f}:{lon:.3f}", ttl=900.0, fn=_do)


def _day_levels(day_idx: int, data: Dict[str, Any]) -> Dict[str, int]:
    """Compute per-phenomenon level for day day_idx (0 or 1)."""
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})

    # Extract the hourly slice for this day (24 entries per day)
    h_codes = hourly.get("weather_code", [])[day_idx * 24 : (day_idx + 1) * 24]
    h_cape = hourly.get("cape", [])[day_idx * 24 : (day_idx + 1) * 24]

    t_max = float(daily.get("temperature_2m_max", [0, 0])[day_idx] or 0)
    t_min = float(daily.get("temperature_2m_min", [0, 0])[day_idx] or 0)
    gust_max = float(daily.get("wind_gusts_10m_max", [0, 0])[day_idx] or 0)
    precip_sum = float(daily.get("precipitation_sum", [0, 0])[day_idx] or 0)
    precip_hours = int(daily.get("precipitation_hours", [0, 0])[day_idx] or 0)
    snow_cm = float(daily.get("snowfall_sum", [0, 0])[day_idx] or 0)
    cape_max = float(daily.get("cape_max", [0, 0])[day_idx] or 0)
    if not cape_max and h_cape:
        cape_max = max([float(c or 0) for c in h_cape])

    return {
        "orage": _thunder_level(h_codes, cape_max, gust_max),
        "vent": _wind_level(gust_max),
        "pluie": _rain_level(precip_sum, precip_hours),
        "canicule": _heat_level(t_max),
        "grand-froid": _cold_level(t_min),
        "neige": _snow_level(snow_cm, h_codes),
    }


def _day_values(day_idx: int, data: Dict[str, Any]) -> Dict[str, Any]:
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})
    h_cape = hourly.get("cape", [])[day_idx * 24 : (day_idx + 1) * 24]
    cape_max = float(daily.get("cape_max", [0, 0])[day_idx] or 0)
    if not cape_max and h_cape:
        cape_max = max([float(c or 0) for c in h_cape])
    return {
        "t_max": float(daily.get("temperature_2m_max", [0, 0])[day_idx] or 0),
        "t_min": float(daily.get("temperature_2m_min", [0, 0])[day_idx] or 0),
        "gust_max_kmh": float(daily.get("wind_gusts_10m_max", [0, 0])[day_idx] or 0),
        "precip_sum_mm": float(daily.get("precipitation_sum", [0, 0])[day_idx] or 0),
        "precip_hours": int(daily.get("precipitation_hours", [0, 0])[day_idx] or 0),
        "snow_cm": float(daily.get("snowfall_sum", [0, 0])[day_idx] or 0),
        "cape_max": cape_max,
    }


# Dept Lourdes (65) + neighbours. "name" is the French département name.
LOURDES_DEPTS = [
    {"id": "65", "name": "Hautes-Pyrénées", "lat": 43.0951, "lon": 0.0},
    {"id": "64", "name": "Pyrénées-Atlantiques", "lat": 43.18, "lon": -0.75},
    {"id": "32", "name": "Gers", "lat": 43.65, "lon": 0.58},
    {"id": "31", "name": "Haute-Garonne", "lat": 43.48, "lon": 1.2},
    {"id": "09", "name": "Ariège", "lat": 42.95, "lon": 1.48},
]


async def compute_vigilance() -> Dict[str, Any]:
    """Compute vigilance per phenomenon for Lourdes (65) and 4 neighbouring depts."""
    async def _one(dept: Dict[str, Any]) -> Dict[str, Any]:
        data = await _fetch_open_meteo(dept["lat"], dept["lon"])
        today = _day_levels(0, data)
        tomorrow = _day_levels(1, data)
        merged = {k: max(today[k], tomorrow[k]) for k in today}
        vals_today = _day_values(0, data)
        vals_tomorrow = _day_values(1, data)
        return {
            "id": dept["id"],
            "name": dept["name"],
            "lat": dept["lat"],
            "lon": dept["lon"],
            "phenomena": [
                {
                    "key": k,
                    "label": label,
                    "icon": icon,
                    "level": merged[k],
                    "level_fr": LEVELS_FR[merged[k]],
                    "color": LEVEL_COLORS[merged[k]],
                    "today": today[k],
                    "tomorrow": tomorrow[k],
                }
                for k, label, icon in PHENOMENA_META
            ],
            "max_level": max(merged.values()),
            "max_level_fr": LEVELS_FR[max(merged.values())],
            "max_color": LEVEL_COLORS[max(merged.values())],
            "max_label": LEVEL_LABELS[max(merged.values())],
            "values_today": vals_today,
            "values_tomorrow": vals_tomorrow,
        }

    results = await asyncio.gather(*[_one(d) for d in LOURDES_DEPTS])
    # Overall worst level among all depts
    overall = max(r["max_level"] for r in results)
    return {
        "updated_at": int(time.time()),
        "source": "open-meteo",
        "disclaimer": "Vigilance calculée localement à partir des prévisions Open-Meteo. "
                      "Pour la vigilance officielle, consultez vigilance.meteofrance.fr",
        "phenomena_meta": [
            {"key": k, "label": label, "icon": icon}
            for k, label, icon in PHENOMENA_META
        ],
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

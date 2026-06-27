"""Severe weather variables (hail risk + advanced forecast).

Fetches Open-Meteo with multi-level data (pressure levels 300/500/700/850 hPa
+ surface) and computes a composite hail risk score per hour.

Hail score formula (empirical, scale 0-100):
    cape_term  = clip(cape / 2500, 0, 1) * 40
    li_term    = clip(-LI / 6, 0, 1)    * 20
    shear_term = clip(shear_0_6km / 30, 0, 1) * 25   (m/s)
    fzh_term   = clip((3500 - freezing_level_m) / 2000, 0, 1) * 15
    score = cape_term + li_term + shear_term + fzh_term

References:
- SHIP composite indicator (NOAA SPC)
- Open-Meteo pressure level docs: https://open-meteo.com/en/docs
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from weather import OPEN_METEO_BASE, _cached, get_with_retry

logger = logging.getLogger(__name__)


# ---------- Hail score ----------
def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def hail_score(
    cape: Optional[float],
    lifted_index: Optional[float],
    shear_0_6km_ms: Optional[float],
    freezing_level_m: Optional[float],
) -> float:
    """Composite hail risk 0-100 from instability + shear + freezing level."""
    if cape is None and lifted_index is None and shear_0_6km_ms is None and freezing_level_m is None:
        return 0.0
    cape_v = float(cape or 0.0)
    li_v = float(lifted_index if lifted_index is not None else 0.0)
    shear_v = float(shear_0_6km_ms or 0.0)
    fzh_v = float(freezing_level_m if freezing_level_m is not None else 5000.0)

    cape_term = _clip(cape_v / 2500.0, 0, 1) * 40
    li_term = _clip(-li_v / 6.0, 0, 1) * 20
    shear_term = _clip(shear_v / 30.0, 0, 1) * 25
    fzh_term = _clip((3500.0 - fzh_v) / 2000.0, 0, 1) * 15
    return round(cape_term + li_term + shear_term + fzh_term, 1)


def hail_level(score: float) -> str:
    """Map numeric score → categorical level for UI."""
    if score >= 70:
        return "extrême"
    if score >= 50:
        return "fort"
    if score >= 30:
        return "modéré"
    if score >= 15:
        return "faible"
    return "nul"


# ---------- Wind components ----------
def _wind_components(speed: Optional[float], direction_deg: Optional[float]) -> tuple[float, float]:
    """Convert (speed, direction-from) → (u, v) components in same unit as speed.
    Direction is "where the wind is coming from" (meteo convention)."""
    if speed is None or direction_deg is None:
        return 0.0, 0.0
    rad = math.radians(float(direction_deg))
    # meteo → math convention: wind blowing TO (dir + 180); u = east, v = north
    u = -float(speed) * math.sin(rad)
    v = -float(speed) * math.cos(rad)
    return u, v


def _shear_magnitude(
    s1: Optional[float], d1: Optional[float],
    s2: Optional[float], d2: Optional[float],
) -> Optional[float]:
    """Magnitude of the vector difference between two wind layers (m/s)."""
    if None in (s1, d1, s2, d2):
        return None
    u1, v1 = _wind_components(s1, d1)
    u2, v2 = _wind_components(s2, d2)
    return round(math.sqrt((u2 - u1) ** 2 + (v2 - v1) ** 2), 2)


# ---------- Open-Meteo fetch ----------
SEVERE_HOURLY_VARS = [
    # Surface
    "temperature_2m",
    "soil_temperature_0cm",
    "wind_speed_10m",
    "wind_direction_10m",
    # Convective indices
    "cape",
    "lifted_index",
    "convective_inhibition",
    "freezing_level_height",
    # Pressure levels
    "temperature_850hPa",
    "wind_speed_850hPa",
    "wind_direction_850hPa",
    "wind_speed_500hPa",
    "wind_direction_500hPa",
    "wind_speed_300hPa",
    "wind_direction_300hPa",
    "vertical_velocity_700hPa",
]


async def fetch_severe(lat: float, lon: float, hours: int = 24) -> Dict[str, Any]:
    """24h (rolling) severe-weather forecast incl. hail score."""
    return await _cached(
        f"severe:{lat}:{lon}:{hours}",
        300.0,  # 5 min cache
        lambda: _fetch_severe_impl(lat, lon, hours),
    )


async def _fetch_severe_impl(lat: float, lon: float, hours: int) -> Dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(SEVERE_HOURLY_VARS),
        # Wind speeds in m/s for direct use in the shear formula
        "wind_speed_unit": "ms",
        "timezone": "auto",
        "forecast_days": 2,
        "past_hours": 0,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15)
    data = r.json()
    tz_name = data.get("timezone", "Europe/Paris")
    h = data.get("hourly") or {}
    times = h.get("time") or []

    # Find starting index = first hour ≥ now (UTC truncated to hour)
    now_iso_local = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    # Open-Meteo returns local-timezone strings when timezone=auto, so we compare in local TZ
    # Simpler: just take first index whose timestamp is the closest to "now" but in practice
    # the API returns hours starting from today 00:00 local, so we scan.
    try:
        from zoneinfo import ZoneInfo
        local_now = datetime.now(ZoneInfo(tz_name))
        local_iso = local_now.strftime("%Y-%m-%dT%H:00")
    except Exception:
        local_iso = now_iso_local

    start = 0
    for i, t in enumerate(times):
        if t >= local_iso:
            start = i
            break
    end = min(start + hours, len(times))

    out: List[Dict[str, Any]] = []
    max_score = 0.0
    max_score_time: Optional[str] = None
    for i in range(start, end):
        cape = h.get("cape", [None] * len(times))[i]
        li = h.get("lifted_index", [None] * len(times))[i]
        fzh = h.get("freezing_level_height", [None] * len(times))[i]
        t2m = h.get("temperature_2m", [None] * len(times))[i]
        t850 = h.get("temperature_850hPa", [None] * len(times))[i]
        soil_t = h.get("soil_temperature_0cm", [None] * len(times))[i]
        w10_s = h.get("wind_speed_10m", [None] * len(times))[i]
        w10_d = h.get("wind_direction_10m", [None] * len(times))[i]
        w850_s = h.get("wind_speed_850hPa", [None] * len(times))[i]
        w850_d = h.get("wind_direction_850hPa", [None] * len(times))[i]
        w500_s = h.get("wind_speed_500hPa", [None] * len(times))[i]
        w500_d = h.get("wind_direction_500hPa", [None] * len(times))[i]
        w300_s = h.get("wind_speed_300hPa", [None] * len(times))[i]
        w300_d = h.get("wind_direction_300hPa", [None] * len(times))[i]
        vv700 = h.get("vertical_velocity_700hPa", [None] * len(times))[i]

        # Shear 0-6km (approximated as 10m → 500hPa) and 850-500
        shear_0_6 = _shear_magnitude(w10_s, w10_d, w500_s, w500_d)
        shear_850_500 = _shear_magnitude(w850_s, w850_d, w500_s, w500_d)

        score = hail_score(cape, li, shear_0_6, fzh)
        if score > max_score:
            max_score = score
            max_score_time = times[i]

        out.append({
            "time": times[i],
            "hail_score": score,
            "hail_level": hail_level(score),
            "cape": cape,
            "lifted_index": li,
            "freezing_level_m": fzh,
            "t2m": t2m,
            "t850": t850,
            "soil_t": soil_t,
            "jet_speed": w300_s,
            "jet_direction": w300_d,
            "wind_500_speed": w500_s,
            "wind_500_direction": w500_d,
            "wind_850_speed": w850_s,
            "wind_850_direction": w850_d,
            "wind_10_speed": w10_s,
            "wind_10_direction": w10_d,
            "shear_0_6km": shear_0_6,
            "shear_850_500": shear_850_500,
            "vertical_velocity_700": vv700,
        })

    return {
        "timezone": tz_name,
        "hours": len(out),
        "hourly": out,
        "max_hail_score": max_score,
        "max_hail_level": hail_level(max_score),
        "max_hail_time": max_score_time,
    }

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



# =============================================================================
# Grid forecast (France-wide map) and vertical profile
# =============================================================================

# France métropolitaine + Corse + marges côtières
FRANCE_BBOX = {
    "lat_min": 41.0,
    "lat_max": 51.5,
    "lon_min": -5.5,
    "lon_max": 10.0,
}
# 16 cols × 12 rows = 192 points ≈ 1 call gratuit Open-Meteo multi-location
GRID_COLS = 16
GRID_ROWS = 12


def _france_grid() -> tuple[List[float], List[float]]:
    """Compute a regular lat/lon grid covering France métropolitaine + Corse."""
    lats: List[float] = []
    lons: List[float] = []
    dlat = (FRANCE_BBOX["lat_max"] - FRANCE_BBOX["lat_min"]) / (GRID_ROWS - 1)
    dlon = (FRANCE_BBOX["lon_max"] - FRANCE_BBOX["lon_min"]) / (GRID_COLS - 1)
    for r in range(GRID_ROWS):
        lat = FRANCE_BBOX["lat_min"] + r * dlat
        for c in range(GRID_COLS):
            lon = FRANCE_BBOX["lon_min"] + c * dlon
            lats.append(round(lat, 3))
            lons.append(round(lon, 3))
    return lats, lons


# Mapping: UI param key → Open-Meteo hourly variable(s)
# For computed params (shear, hail), we need multiple variables and combine.
GRID_PARAM_MAP: Dict[str, Dict[str, Any]] = {
    "t2m": {"vars": ["temperature_2m"], "unit": "°C"},
    "t850": {"vars": ["temperature_850hPa"], "unit": "°C"},
    "soil_t": {"vars": ["soil_temperature_0cm"], "unit": "°C"},
    "cape": {"vars": ["cape"], "unit": "J/kg"},
    "freezing_level": {"vars": ["freezing_level_height"], "unit": "m"},
    "jet_speed": {"vars": ["wind_speed_300hPa"], "unit": "m/s"},
    "vv700": {"vars": ["vertical_velocity_700hPa"], "unit": "Pa/s"},
    "shear_0_6km": {
        "vars": ["wind_speed_10m", "wind_direction_10m",
                 "wind_speed_500hPa", "wind_direction_500hPa"],
        "unit": "m/s",
    },
    "hail_score": {
        "vars": ["cape", "lifted_index", "freezing_level_height",
                 "wind_speed_10m", "wind_direction_10m",
                 "wind_speed_500hPa", "wind_direction_500hPa"],
        "unit": "/100",
    },
}


async def fetch_severe_grid(param: str, hour_offset: int = 0) -> Dict[str, Any]:
    """Fetch a single-parameter forecast on the France grid (192 points)
    in ONE Open-Meteo multi-location call. Cached 10 min."""
    if param not in GRID_PARAM_MAP:
        raise ValueError(f"unknown param: {param}")
    return await _cached(
        f"severe-grid:{param}:{hour_offset}",
        600.0,
        lambda: _fetch_severe_grid_impl(param, hour_offset),
    )


async def _fetch_severe_grid_impl(param: str, hour_offset: int) -> Dict[str, Any]:
    lats, lons = _france_grid()
    spec = GRID_PARAM_MAP[param]
    needed_vars = spec["vars"]

    params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "hourly": ",".join(needed_vars),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "forecast_days": 2,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=25)
    raw = r.json()

    # Open-Meteo returns either a list (multi-location) or a single dict.
    locs = raw if isinstance(raw, list) else [raw]
    if len(locs) != len(lats):
        logger.warning("severe-grid: expected %d locations, got %d", len(lats), len(locs))

    times_ref: List[str] = []
    values: List[Optional[float]] = []
    for i, loc in enumerate(locs):
        h = loc.get("hourly") or {}
        ts = h.get("time") or []
        if not times_ref and ts:
            times_ref = ts
        idx = max(0, min(int(hour_offset), len(ts) - 1)) if ts else 0

        if param == "hail_score":
            cape = (h.get("cape") or [None] * len(ts))[idx]
            li = (h.get("lifted_index") or [None] * len(ts))[idx]
            fzh = (h.get("freezing_level_height") or [None] * len(ts))[idx]
            w10s = (h.get("wind_speed_10m") or [None] * len(ts))[idx]
            w10d = (h.get("wind_direction_10m") or [None] * len(ts))[idx]
            w5s = (h.get("wind_speed_500hPa") or [None] * len(ts))[idx]
            w5d = (h.get("wind_direction_500hPa") or [None] * len(ts))[idx]
            shear = _shear_magnitude(w10s, w10d, w5s, w5d)
            v = hail_score(cape, li, shear, fzh)
        elif param == "shear_0_6km":
            w10s = (h.get("wind_speed_10m") or [None] * len(ts))[idx]
            w10d = (h.get("wind_direction_10m") or [None] * len(ts))[idx]
            w5s = (h.get("wind_speed_500hPa") or [None] * len(ts))[idx]
            w5d = (h.get("wind_direction_500hPa") or [None] * len(ts))[idx]
            v = _shear_magnitude(w10s, w10d, w5s, w5d)
        else:
            var = needed_vars[0]
            series = h.get(var) or []
            v = series[idx] if idx < len(series) else None

        values.append(round(v, 2) if isinstance(v, (int, float)) else None)

    # Compute the displayed time string from the reference series
    selected_time = times_ref[max(0, min(int(hour_offset), len(times_ref) - 1))] if times_ref else None

    valid = [v for v in values if v is not None]
    return {
        "param": param,
        "unit": spec["unit"],
        "hour_offset": int(hour_offset),
        "time": selected_time,  # UTC ISO
        "bbox": FRANCE_BBOX,
        "grid_cols": GRID_COLS,
        "grid_rows": GRID_ROWS,
        "lats": lats,
        "lons": lons,
        "values": values,
        "min": min(valid) if valid else None,
        "max": max(valid) if valid else None,
    }


# ---------- Vertical temperature profile ----------
PROFILE_PRESSURE_LEVELS = [1000, 925, 850, 700, 500, 300]
PROFILE_VARS = ["temperature_2m"] + [f"temperature_{p}hPa" for p in PROFILE_PRESSURE_LEVELS]

# Standard atmospheric heights (m) for each pressure level (approximation)
PRESSURE_TO_HEIGHT_M = {
    "surface": 2,
    1000: 110,
    925: 760,
    850: 1500,
    700: 3000,
    500: 5500,
    300: 9200,
}


async def fetch_temp_profile(lat: float, lon: float, hour_offset: int = 0) -> Dict[str, Any]:
    """Vertical temperature profile (surface + 6 pressure levels). Cached 5 min."""
    return await _cached(
        f"profile:{lat}:{lon}:{hour_offset}",
        300.0,
        lambda: _fetch_temp_profile_impl(lat, lon, hour_offset),
    )


async def _fetch_temp_profile_impl(lat: float, lon: float, hour_offset: int) -> Dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(PROFILE_VARS),
        "timezone": "auto",
        "forecast_days": 2,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15)
    data = r.json()
    h = data.get("hourly") or {}
    times = h.get("time") or []
    idx = max(0, min(int(hour_offset), len(times) - 1)) if times else 0

    points: List[Dict[str, Any]] = []
    t_surface = (h.get("temperature_2m") or [None] * len(times))[idx] if times else None
    points.append({
        "level": "2m",
        "pressure_hpa": 1013,
        "height_m": PRESSURE_TO_HEIGHT_M["surface"],
        "temperature_c": t_surface,
    })
    for p in PROFILE_PRESSURE_LEVELS:
        v = (h.get(f"temperature_{p}hPa") or [None] * len(times))[idx] if times else None
        points.append({
            "level": f"{p}hPa",
            "pressure_hpa": p,
            "height_m": PRESSURE_TO_HEIGHT_M[p],
            "temperature_c": v,
        })

    return {
        "timezone": data.get("timezone", "Europe/Paris"),
        "hour_offset": int(hour_offset),
        "time": times[idx] if times else None,
        "lat": lat,
        "lon": lon,
        "points": points,
    }

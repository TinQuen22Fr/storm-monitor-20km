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
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

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
    shear_850_500_ms: Optional[float] = None,
) -> float:
    """Composite hail risk 0-100 from instability + shear + freezing level.

    Extended formula (Phase 34) — weights re-balanced + mid-level shear + synergy bonus:
        cape_term       = clip(CAPE / 2500)          * 30
        li_term         = clip(-LI / 6)              * 15
        shear_06_term   = clip(shear_0_6km / 30)     * 20
        shear_850500    = clip(shear_850_500 / 20)   * 15   (NEW — mid-level)
        fzh_term        = clip((3500 - fzh) / 2000)  * 10
        synergy_bonus   = (cape_norm × shear_06_norm) * 10  (NEW — interaction)

    Total max = 100. The synergy_bonus captures the meteorological reality that
    CAPE alone produces pulse storms, but CAPE + strong shear produces tilted
    multicells / supercells that grow large hail.
    """
    if (cape is None and lifted_index is None and shear_0_6km_ms is None
            and freezing_level_m is None and shear_850_500_ms is None):
        return 0.0
    cape_v = float(cape or 0.0)
    li_v = float(lifted_index if lifted_index is not None else 0.0)
    shear06_v = float(shear_0_6km_ms or 0.0)
    shear8550_v = float(shear_850_500_ms or 0.0)
    fzh_v = float(freezing_level_m if freezing_level_m is not None else 5000.0)

    cape_norm = _clip(cape_v / 2500.0, 0, 1)
    li_norm = _clip(-li_v / 6.0, 0, 1)
    shear06_norm = _clip(shear06_v / 30.0, 0, 1)
    shear8550_norm = _clip(shear8550_v / 20.0, 0, 1)
    fzh_norm = _clip((3500.0 - fzh_v) / 2000.0, 0, 1)

    cape_term = cape_norm * 30
    li_term = li_norm * 15
    shear_06_term = shear06_norm * 20
    shear_8550_term = shear8550_norm * 15
    fzh_term = fzh_norm * 10
    synergy_bonus = cape_norm * shear06_norm * 10

    total = cape_term + li_term + shear_06_term + shear_8550_term + fzh_term + synergy_bonus
    return round(_clip(total, 0, 100), 1)


# =============================================================================
# Phase 34 — Real-time lightning surge booster
# =============================================================================

WINDOW_NOW_S = 5 * 60     # last 5 min  → density_now
WINDOW_PREV_S = 15 * 60   # last 15 min total → density_prev computed from [5..15] slice
SURGE_THRESHOLD = 2.0     # density_now must be ≥ 2× density_prev
SURGE_MIN_DENSITY = 0.5   # impacts/min minimum to even consider it a surge


def effective_radius_km(monitored_radius_km: float) -> float:
    """Adaptive radius for the strike booster — `max(40 km, radius × 1.5)`.
    Cells move fast (~50 km/h in SW France), so we look slightly outside the
    monitored zone to catch incoming activity."""
    return max(40.0, float(monitored_radius_km) * 1.5)


def compute_lightning_density(strikes: List[Dict[str, Any]], now_ts: float) -> Dict[str, Any]:
    """Compute strike densities in the [now-5min] and [now-15min..now-5min] windows."""
    if not isinstance(strikes, list):
        return {"available": False, "count_5min": 0, "count_5_15min": 0,
                "density_now": 0.0, "density_prev": 0.0, "surge_ratio": 0.0, "is_surge": False}

    cutoff_now = now_ts - WINDOW_NOW_S
    cutoff_prev = now_ts - WINDOW_PREV_S
    n_now = 0
    n_prev = 0
    for s in strikes:
        ts = s.get("ts")
        if ts is None:
            continue
        if ts >= cutoff_now:
            n_now += 1
        elif ts >= cutoff_prev:
            n_prev += 1

    density_now = n_now / (WINDOW_NOW_S / 60.0)
    density_prev = n_prev / ((WINDOW_PREV_S - WINDOW_NOW_S) / 60.0)
    if density_prev < 0.01:
        surge_ratio = float(density_now) * 10
    else:
        surge_ratio = density_now / density_prev

    is_surge = density_now >= SURGE_MIN_DENSITY and surge_ratio >= SURGE_THRESHOLD

    return {
        "available": True,
        "count_5min": n_now,
        "count_5_15min": n_prev,
        "density_now": round(density_now, 2),
        "density_prev": round(density_prev, 2),
        "surge_ratio": round(surge_ratio, 2),
        "is_surge": is_surge,
    }


def compute_boost(density: Dict[str, Any], base_score: float) -> Tuple[float, float]:
    """Compute the realtime boost (0-30 pts) to apply to a base hail score.

    Gating: `boost × (0.4 + 0.6 × base/100)` — prevents false positives on
    modelled-calm skies and rewards alignment between physical & electrical signals.
    """
    if not density.get("available"):
        return 0.0, 0.0
    density_now = density.get("density_now", 0.0)
    if density.get("is_surge"):
        boost_raw = _clip(density_now / 10.0, 0, 1) * 30.0
    else:
        boost_raw = _clip(density_now / 5.0, 0, 1) * 15.0
    gating = 0.4 + 0.6 * (_clip(base_score, 0, 100) / 100.0)
    return round(boost_raw * gating, 1), round(boost_raw, 1)


# ---------- 1h in-memory history of (theoretical, realtime) scores ----------
HISTORY_MAX_AGE_S = 60 * 60
HISTORY_MAX_POINTS = 360
_history_store: Dict[Tuple[float, float, float], Deque[Dict[str, Any]]] = {}


def _hist_key(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float]:
    return (round(float(lat), 3), round(float(lon), 3), round(float(radius_km), 1))


def record_score_sample(
    lat: float, lon: float, radius_km: float,
    theoretical: float, realtime: float, is_surge: bool,
    lightning_available: bool, density_now: float,
) -> None:
    key = _hist_key(lat, lon, radius_km)
    dq = _history_store.get(key)
    if dq is None:
        dq = deque(maxlen=HISTORY_MAX_POINTS)
        _history_store[key] = dq
    dq.append({
        "ts": time.time(),
        "theoretical": round(float(theoretical), 1),
        "realtime": round(float(realtime), 1),
        "is_surge": bool(is_surge),
        "lightning_available": bool(lightning_available),
        "density_now": round(float(density_now), 2),
    })


def get_score_history(lat: float, lon: float, radius_km: float) -> List[Dict[str, Any]]:
    key = _hist_key(lat, lon, radius_km)
    dq = _history_store.get(key)
    if not dq:
        return []
    cutoff = time.time() - HISTORY_MAX_AGE_S
    return [s for s in list(dq) if s["ts"] >= cutoff]


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

        score = hail_score(cape, li, shear_0_6, fzh, shear_850_500)
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
    """Slice one (param, hour) from the local bulk store. NEVER calls Open-Meteo
    when the slider moves — the bulk store is refreshed at most every BULK_TTL_S
    seconds via `fetch_severe_grid_bulk()` and persisted on disk."""
    if param not in GRID_PARAM_MAP:
        raise ValueError(f"unknown param: {param}")
    bulk = await _get_or_refresh_bulk()
    return _slice_bulk(bulk, param, hour_offset)


# =============================================================================
# Bulk fetch architecture (Phase 35 — "Bulk Fetch & Local Storage")
#
# Single Open-Meteo multi-location call covers:
#   - ALL 192 grid points across France
#   - ALL hourly variables needed by ANY of the 9 UI params
#   - ALL 48 hours of forecast
#
# Total payload ≈ 192 × 12 vars × 48 h ≈ 110k float values ≈ 1.5 MB JSON.
# Done once every BULK_TTL_S (= 600 s). After that, every (param, hour_offset)
# request is served from the in-memory snapshot + disk JSON in <10 ms.
#
# The disk JSON is also a fallback when the upstream API is unreachable:
# the snapshot survives backend restarts.
# =============================================================================

from pathlib import Path  # noqa: E402  (kept local to the bulk section)
import asyncio  # noqa: E402
import json  # noqa: E402

BULK_TTL_S = 600.0   # 10 min — matches the previous per-param cache TTL
BULK_FILE = Path(__file__).parent / "cache" / "grid_bulk.json"

# Union of every hourly variable needed by GRID_PARAM_MAP
BULK_HOURLY_VARS = sorted({
    v for spec in GRID_PARAM_MAP.values() for v in spec["vars"]
})

_bulk_lock = asyncio.Lock()
_bulk_snapshot: Optional[Dict[str, Any]] = None  # in-memory cache


def _load_bulk_from_disk() -> Optional[Dict[str, Any]]:
    if not BULK_FILE.exists():
        return None
    try:
        with BULK_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load bulk file %s: %s", BULK_FILE, e)
        return None


def _save_bulk_to_disk(snap: Dict[str, Any]) -> None:
    """Atomic write. Handles permission errors gracefully (warn + continue in
    in-memory mode) so a read-only filesystem or restricted www-data perms
    never block the request thread."""
    try:
        BULK_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = BULK_FILE.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(snap, f, separators=(",", ":"))
        tmp.replace(BULK_FILE)
    except PermissionError as e:
        logger.warning(
            "Bulk cache disk write blocked by permissions on %s: %s. "
            "Continuing with in-memory-only snapshot.", BULK_FILE, e,
        )
    except OSError as e:
        logger.warning(
            "Bulk cache disk write OSError on %s: %s. Continuing in-memory only.",
            BULK_FILE, e,
        )
    except Exception as e:
        logger.warning("Bulk cache disk write failed (%s): %s", type(e).__name__, e)


async def _save_bulk_to_disk_async(snap: Dict[str, Any]) -> None:
    """Run the synchronous disk write in a thread pool so the event loop
    stays responsive on weak CPUs (Intel Atom Kimsufi). A 448 KB JSON dump
    can take 100-300 ms on slow IO — offloading prevents request stalls."""
    try:
        await asyncio.to_thread(_save_bulk_to_disk, snap)
    except Exception as e:
        logger.warning("Bulk save thread failed: %s", e)


async def _get_or_refresh_bulk() -> Dict[str, Any]:
    """Return a fresh bulk snapshot. Refreshes from upstream only if the
    current one (in-memory or disk) is older than BULK_TTL_S."""
    global _bulk_snapshot
    now = time.time()

    # Try in-memory first
    if _bulk_snapshot and (now - _bulk_snapshot.get("fetched_at", 0)) < BULK_TTL_S:
        return _bulk_snapshot

    async with _bulk_lock:
        # Re-check under lock
        if _bulk_snapshot and (now - _bulk_snapshot.get("fetched_at", 0)) < BULK_TTL_S:
            return _bulk_snapshot

        # Try disk
        disk = _load_bulk_from_disk()
        if disk and (now - disk.get("fetched_at", 0)) < BULK_TTL_S:
            _bulk_snapshot = disk
            return _bulk_snapshot

        # Fetch fresh from Open-Meteo
        try:
            fresh = await _fetch_bulk_impl()
            _bulk_snapshot = fresh
            # Non-blocking disk persistence — never stalls the request thread
            asyncio.create_task(_save_bulk_to_disk_async(fresh))
            return _bulk_snapshot
        except Exception as e:
            # Fall back to stale disk/in-memory rather than failing
            stale = _bulk_snapshot or disk
            if stale is not None:
                logger.warning(
                    "Bulk fetch failed (%s) — serving stale snapshot from %s",
                    type(e).__name__,
                    "memory" if _bulk_snapshot else "disk",
                )
                return stale
            raise


async def _fetch_bulk_impl() -> Dict[str, Any]:
    """ONE Open-Meteo call covering 192 points × all needed hourly vars × 48 h.
    This is the single network access point for the entire France map."""
    lats, lons = _france_grid()
    params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "hourly": ",".join(BULK_HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "forecast_days": 2,
    }
    t0 = time.time()
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=45)
    raw = r.json()
    locs = raw if isinstance(raw, list) else [raw]
    if len(locs) != len(lats):
        logger.warning("bulk-grid: expected %d locations, got %d", len(lats), len(locs))

    # Build a unified snapshot: per_param[param] = list[n_hours] of list[n_locs] floats
    times_ref: List[str] = []
    loc_series: List[Dict[str, List[Optional[float]]]] = []
    for loc in locs:
        h = loc.get("hourly") or {}
        if not times_ref:
            times_ref = h.get("time") or []
        loc_series.append(h)
    n_hours = len(times_ref)
    n_locs = len(loc_series)

    per_param: Dict[str, List[List[Optional[float]]]] = {}
    for param, spec in GRID_PARAM_MAP.items():
        per_param[param] = _compute_param_values(param, loc_series, n_hours, spec["vars"])

    snap = {
        "fetched_at": time.time(),
        "fetch_duration_s": round(time.time() - t0, 2),
        "run_iso": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bbox": FRANCE_BBOX,
        "grid_cols": GRID_COLS,
        "grid_rows": GRID_ROWS,
        "n_locs": n_locs,
        "n_hours": n_hours,
        "times": times_ref,
        "lats": lats,
        "lons": lons,
        "per_param": per_param,
        "units": {p: GRID_PARAM_MAP[p]["unit"] for p in GRID_PARAM_MAP},
    }
    logger.info(
        "Bulk grid fetched: %d locs × %d hours × %d params in %.2fs",
        n_locs, n_hours, len(GRID_PARAM_MAP), snap["fetch_duration_s"],
    )
    return snap


def _compute_param_values(
    param: str,
    loc_series: List[Dict[str, List[Optional[float]]]],
    n_hours: int,
    needed_vars: List[str],
) -> List[List[Optional[float]]]:
    """Compute the [n_hours][n_locs] matrix for one logical param.
    Pure CPU work — operates on the bulk hourly arrays already fetched."""
    matrix: List[List[Optional[float]]] = []
    for hour_idx in range(n_hours):
        row: List[Optional[float]] = []
        for h in loc_series:
            ts = h.get("time") or []
            idx = hour_idx if hour_idx < len(ts) else -1
            v: Optional[float] = None
            if idx >= 0:
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
            row.append(round(v, 2) if isinstance(v, (int, float)) else None)
        matrix.append(row)
    return matrix


def _slice_bulk(bulk: Dict[str, Any], param: str, hour_offset: int) -> Dict[str, Any]:
    """Pure in-memory slice — never hits the network."""
    times = bulk.get("times") or []
    matrix = bulk.get("per_param", {}).get(param) or []
    if not times or not matrix:
        return {
            "param": param,
            "unit": GRID_PARAM_MAP[param]["unit"],
            "hour_offset": int(hour_offset),
            "time": None,
            "bbox": bulk.get("bbox", FRANCE_BBOX),
            "grid_cols": bulk.get("grid_cols", GRID_COLS),
            "grid_rows": bulk.get("grid_rows", GRID_ROWS),
            "lats": bulk.get("lats", []),
            "lons": bulk.get("lons", []),
            "values": [],
            "min": None,
            "max": None,
            "source": "bulk-empty",
        }
    idx = max(0, min(int(hour_offset), len(times) - 1))
    values = matrix[idx] if idx < len(matrix) else []
    valid = [v for v in values if v is not None]
    return {
        "param": param,
        "unit": GRID_PARAM_MAP[param]["unit"],
        "hour_offset": int(hour_offset),
        "time": times[idx],
        "bbox": bulk.get("bbox"),
        "grid_cols": bulk.get("grid_cols"),
        "grid_rows": bulk.get("grid_rows"),
        "lats": bulk.get("lats", []),
        "lons": bulk.get("lons", []),
        "values": values,
        "min": min(valid) if valid else None,
        "max": max(valid) if valid else None,
        "source": "bulk",
        "fetched_at": bulk.get("fetched_at"),
        "run_iso": bulk.get("run_iso"),
    }


async def get_bulk_snapshot_for_frontend() -> Dict[str, Any]:
    """Return the FULL bulk snapshot in one payload (all 9 params × all hours
    × 192 locs). The frontend fetches this ONCE then slices client-side. This
    is what eliminates the per-hour micro-request cascade that was saturating
    the Kimsufi Atom backend."""
    bulk = await _get_or_refresh_bulk()
    return {
        "fetched_at": bulk.get("fetched_at"),
        "run_iso": bulk.get("run_iso"),
        "bbox": bulk.get("bbox"),
        "grid_cols": bulk.get("grid_cols"),
        "grid_rows": bulk.get("grid_rows"),
        "n_locs": bulk.get("n_locs"),
        "n_hours": bulk.get("n_hours"),
        "times": bulk.get("times", []),
        "lats": bulk.get("lats", []),
        "lons": bulk.get("lons", []),
        "per_param": bulk.get("per_param", {}),
        "units": bulk.get("units", {}),
    }


async def get_bulk_status() -> Dict[str, Any]:
    """Diagnostic — exposed via /api/weather/severe/grid/status."""
    snap = _bulk_snapshot or _load_bulk_from_disk()
    if not snap:
        return {"available": False, "params": list(GRID_PARAM_MAP.keys())}
    age_s = round(time.time() - snap.get("fetched_at", 0), 1)
    return {
        "available": True,
        "params": list(snap.get("per_param", {}).keys()),
        "n_hours": snap.get("n_hours", 0),
        "n_locs": snap.get("n_locs", 0),
        "times_first": (snap.get("times") or [None])[0],
        "times_last": (snap.get("times") or [None])[-1],
        "run_iso": snap.get("run_iso"),
        "fetched_at": snap.get("fetched_at"),
        "age_seconds": age_s,
        "fresh": age_s < BULK_TTL_S,
        "fetch_duration_s": snap.get("fetch_duration_s"),
        "ttl_seconds": BULK_TTL_S,
        "in_memory": _bulk_snapshot is not None,
        "on_disk": BULK_FILE.exists(),
        "disk_path": str(BULK_FILE),
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
    """Vertical temperature profile (surface + 6 pressure levels).
    Same caching strategy as the grid: the expensive Open-Meteo call returns
    ALL 48 hours; cache is keyed by `(lat, lon)` only (10 min). Slider scrubbing
    re-uses the cached snapshot — no extra HTTP call, no 429 rate-limit."""
    all_hours = await _cached(
        f"profile-all:{round(float(lat), 3)}:{round(float(lon), 3)}",
        600.0,
        lambda: _fetch_temp_profile_all_hours_impl(lat, lon),
    )
    return _extract_hour_from_profile(all_hours, hour_offset)


async def _fetch_temp_profile_all_hours_impl(lat: float, lon: float) -> Dict[str, Any]:
    """Single Open-Meteo call for the full 48h temp profile."""
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
    return {
        "timezone": data.get("timezone", "Europe/Paris"),
        "lat": lat,
        "lon": lon,
        "times": times,
        "t2m_series": h.get("temperature_2m") or [None] * len(times),
        "levels_series": {
            p: h.get(f"temperature_{p}hPa") or [None] * len(times)
            for p in PROFILE_PRESSURE_LEVELS
        },
    }


def _extract_hour_from_profile(snapshot: Dict[str, Any], hour_offset: int) -> Dict[str, Any]:
    """Build the points[] list for a single hour from the cached snapshot."""
    times = snapshot.get("times") or []
    if not times:
        return {
            "timezone": snapshot.get("timezone", "Europe/Paris"),
            "hour_offset": int(hour_offset),
            "time": None,
            "lat": snapshot.get("lat"),
            "lon": snapshot.get("lon"),
            "points": [],
        }
    idx = max(0, min(int(hour_offset), len(times) - 1))
    t_surface = snapshot["t2m_series"][idx] if idx < len(snapshot["t2m_series"]) else None
    points: List[Dict[str, Any]] = [{
        "level": "2m",
        "pressure_hpa": 1013,
        "height_m": PRESSURE_TO_HEIGHT_M["surface"],
        "temperature_c": t_surface,
    }]
    for p in PROFILE_PRESSURE_LEVELS:
        series = snapshot["levels_series"].get(p, [])
        v = series[idx] if idx < len(series) else None
        points.append({
            "level": f"{p}hPa",
            "pressure_hpa": p,
            "height_m": PRESSURE_TO_HEIGHT_M[p],
            "temperature_c": v,
        })
    return {
        "timezone": snapshot.get("timezone", "Europe/Paris"),
        "hour_offset": int(hour_offset),
        "time": times[idx],
        "lat": snapshot.get("lat"),
        "lon": snapshot.get("lon"),
        "points": points,
    }

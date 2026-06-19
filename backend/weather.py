"""Open-Meteo client for thunderstorm tracking around Lourdes."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List

import httpx

logger = logging.getLogger(__name__)

# Lourdes center coordinates
LOURDES_LAT = 43.0951
LOURDES_LON = -0.0434
RADIUS_KM = 20.0

# Weather codes indicating thunderstorm activity
THUNDERSTORM_CODES = {95, 96, 99}
# Rain/shower codes indicating active precipitation
RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82}

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# Stale cache persistence (survives backend restarts)
_STALE_FILE = Path(
    os.environ.get(
        "STALE_CACHE_FILE",
        # Default to a path co-located with this module — works in any deploy
        str(Path(__file__).parent / ".stale_cache.pkl"),
    )
)


# ---------- Resilient HTTP with 429 retry ----------
async def get_with_retry(url: str, params: Dict[str, Any] | None = None,
                        headers: Dict[str, Any] | None = None,
                        timeout: float = 10.0, max_retries: int = 2) -> httpx.Response:
    """GET with short exponential backoff on 429/503. Fails fast."""
    last_response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries):
            try:
                r = await client.get(url, params=params, headers=headers)
                last_response = r
                if r.status_code in (429, 503):
                    if attempt >= max_retries - 1:
                        break
                    wait = 1.0 + attempt  # 1s, 2s
                    logger.info("Rate-limited (%s), waiting %.1fs (attempt %d/%d)",
                               r.status_code, wait, attempt + 1, max_retries)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return r
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0)
                    continue
                raise
    if last_response is not None:
        last_response.raise_for_status()
        return last_response
    raise RuntimeError("get_with_retry exhausted without result")


# ---------- Simple async TTL cache with stale-while-error fallback ----------
_cache: Dict[str, tuple[float, Any]] = {}
_cache_locks: Dict[str, asyncio.Lock] = {}
_last_log: Dict[str, float] = {}


def _load_stale() -> Dict[str, Any]:
    try:
        if _STALE_FILE.exists():
            with open(_STALE_FILE, "rb") as f:
                return pickle.load(f)
    except Exception as e:
        logger.warning("Failed to load stale cache: %s", e)
    return {}


_stale_cache: Dict[str, Any] = _load_stale()
_stale_save_pending = False


async def _save_stale_soon() -> None:
    """Debounced save to disk (max once per 30s)."""
    global _stale_save_pending
    if _stale_save_pending:
        return
    _stale_save_pending = True
    try:
        await asyncio.sleep(30)
        try:
            with open(_STALE_FILE, "wb") as f:
                pickle.dump(_stale_cache, f)
        except Exception as e:
            logger.warning("Failed to save stale cache: %s", e)
    finally:
        _stale_save_pending = False


async def _cached(key: str, ttl: float, fn: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    now = time.time()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    lock = _cache_locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        try:
            value = await fn()
            _cache[key] = (now + ttl, value)
            _stale_cache[key] = value
            # Fire-and-forget persistence
            try:
                asyncio.create_task(_save_stale_soon())
            except RuntimeError:
                pass
            return value
        except Exception as exc:
            stale = _stale_cache.get(key)
            if stale is not None:
                _cache[key] = (now + min(ttl, 60.0), stale)
                last = _last_log.get(key, 0)
                if now - last > 60:
                    _last_log[key] = now
                    logger.warning(
                        "Upstream error for '%s' — serving stale cache (%s)",
                        key, type(exc).__name__
                    )
                return stale
            raise


def km_to_deg_lat(km: float) -> float:
    return km / 111.0


def km_to_deg_lon(km: float, lat: float) -> float:
    return km / (111.0 * max(math.cos(math.radians(lat)), 0.0001))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def sampling_grid(lat: float, lon: float, radius_km: float, step_km: float | None = None) -> List[Dict[str, float]]:
    """Return a list of lat/lon points in a grid within the given radius.

    Grid density adapts to the radius so large areas (up to ~70 km) are still
    sampled reasonably without breaking the 49-point Open-Meteo limit.
    """
    if step_km is None:
        # Scale step with radius so we always fit roughly 7x7 points = 49
        step_km = max(4.0, radius_km / 4.0)
    points: List[Dict[str, float]] = []
    dlat = km_to_deg_lat(step_km)
    dlon = km_to_deg_lon(step_km, lat)
    # Up to 7x7 = 49 points (Open-Meteo multi-coord limit is 100, we stay well under)
    half = 3 if radius_km > 25 else 2
    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            plat = lat + i * dlat
            plon = lon + j * dlon
            if haversine_km(lat, lon, plat, plon) <= radius_km:
                points.append({"lat": round(plat, 4), "lon": round(plon, 4)})
    return points


async def fetch_current(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
    return await _cached(f"current:{lat}:{lon}", 180.0, lambda: _fetch_current_impl(lat, lon))


async def _fetch_current_impl(lat: float, lon: float) -> Dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "rain",
            "weather_code",
            "pressure_msl",
            "surface_pressure",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "cloud_cover",
        ]),
        "hourly": ",".join([
            "cape",
            "lightning_potential",
            "precipitation_probability",
        ]),
        "timezone": "auto",
        "forecast_days": 1,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15)
    data = r.json()

    # pick current-hour CAPE & lightning_potential
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    idx = 0
    for i, t in enumerate(times):
        if t >= now_iso:
            idx = i
            break
    cape = (hourly.get("cape") or [None])[idx] if times else None
    lp = (hourly.get("lightning_potential") or [None])[idx] if times else None
    pp = (hourly.get("precipitation_probability") or [None])[idx] if times else None
    current = data.get("current", {})
    return {
        "lat": lat,
        "lon": lon,
        "current": current,
        "cape": cape,
        "lightning_potential": lp,
        "precipitation_probability": pp,
        "time": current.get("time"),
        "timezone": data.get("timezone") or "Europe/Paris",
        "timezone_abbreviation": data.get("timezone_abbreviation"),
        "utc_offset_seconds": data.get("utc_offset_seconds"),
    }


async def fetch_forecast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
    return await _cached(f"forecast:{lat}:{lon}", 600.0, lambda: _fetch_forecast_impl(lat, lon))


async def _fetch_forecast_impl(lat: float, lon: float) -> Dict[str, Any]:
    """Short term 24h forecast with precipitation, CAPE, lightning potential."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "precipitation",
            "precipitation_probability",
            "weather_code",
            "cape",
            "lightning_potential",
            "wind_speed_10m",
        ]),
        "timezone": "auto",
        "forecast_days": 2,
        "past_hours": 0,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15)
    data = r.json()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    # Return next 24 hours from now
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    start = 0
    for i, t in enumerate(times):
        if t >= now_iso:
            start = i
            break
    end = min(start + 24, len(times))
    out: List[Dict[str, Any]] = []
    for i in range(start, end):
        out.append({
            "time": times[i],
            "temperature": hourly.get("temperature_2m", [None])[i],
            "precipitation": hourly.get("precipitation", [None])[i],
            "precipitation_probability": hourly.get("precipitation_probability", [None])[i],
            "weather_code": hourly.get("weather_code", [None])[i],
            "cape": hourly.get("cape", [None])[i],
            "lightning_potential": hourly.get("lightning_potential", [None])[i],
            "wind_speed": hourly.get("wind_speed_10m", [None])[i],
        })
    return {"hourly": out}


async def fetch_history_24h(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
    return await _cached(f"history24:{lat}:{lon}", 300.0, lambda: _fetch_history_24h_impl(lat, lon))


async def _fetch_history_24h_impl(lat: float, lon: float) -> Dict[str, Any]:
    """Past 24h hourly data for storm history timeline."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "precipitation",
            "weather_code",
            "cape",
            "lightning_potential",
            "wind_gusts_10m",
        ]),
        "timezone": "auto",
        "past_days": 1,
        "forecast_days": 1,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15)
    data = r.json()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    # Return the last 24h (up to now)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    end = len(times)
    for i, t in enumerate(times):
        if t > now_iso:
            end = i
            break
    start = max(0, end - 24)
    out: List[Dict[str, Any]] = []
    for i in range(start, end):
        code = hourly.get("weather_code", [None])[i]
        out.append({
            "time": times[i],
            "precipitation": hourly.get("precipitation", [None])[i],
            "weather_code": code,
            "cape": hourly.get("cape", [None])[i],
            "lightning_potential": hourly.get("lightning_potential", [None])[i],
            "wind_gust": hourly.get("wind_gusts_10m", [None])[i],
            "is_storm": code in THUNDERSTORM_CODES if code is not None else False,
        })
    return {"hourly": out}


async def fetch_history_days(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, days: int = 7) -> Dict[str, Any]:
    days = max(1, min(int(days), 60))
    return await _cached(f"historyD:{lat}:{lon}:{days}", 600.0, lambda: _fetch_history_days_impl(lat, lon, days))


async def _fetch_history_days_impl(lat: float, lon: float, days: int) -> Dict[str, Any]:
    """Multi-day daily aggregated history using Open-Meteo past_days.

    Returns a list of daily summaries with: precipitation total, max CAPE,
    storm hours count, max wind gust, max lightning_potential.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "precipitation",
            "weather_code",
            "cape",
            "lightning_potential",
            "wind_gusts_10m",
            "temperature_2m",
        ]),
        "timezone": "auto",
        "past_days": days,
        "forecast_days": 1,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
    data = r.json()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    # Group by date
    by_day: Dict[str, Dict[str, Any]] = {}
    for i, t in enumerate(times):
        day = t.split("T")[0]
        b = by_day.setdefault(day, {
            "date": day,
            "precipitation_total": 0.0,
            "max_cape": 0.0,
            "max_lightning_potential": 0.0,
            "max_wind_gust": 0.0,
            "max_temperature": None,
            "min_temperature": None,
            "storm_hours": 0,
        })
        p = hourly.get("precipitation", [0])[i] or 0
        cape = hourly.get("cape", [0])[i] or 0
        lp = hourly.get("lightning_potential", [0])[i] or 0
        gust = hourly.get("wind_gusts_10m", [0])[i] or 0
        code = hourly.get("weather_code", [None])[i]
        temp = hourly.get("temperature_2m", [None])[i]

        b["precipitation_total"] += float(p)
        b["max_cape"] = max(b["max_cape"], float(cape))
        b["max_lightning_potential"] = max(b["max_lightning_potential"], float(lp))
        b["max_wind_gust"] = max(b["max_wind_gust"], float(gust))
        if code in THUNDERSTORM_CODES:
            b["storm_hours"] += 1
        if temp is not None:
            b["max_temperature"] = temp if b["max_temperature"] is None else max(b["max_temperature"], temp)
            b["min_temperature"] = temp if b["min_temperature"] is None else min(b["min_temperature"], temp)

    out = sorted(by_day.values(), key=lambda d: d["date"])
    # Round
    for d in out:
        d["precipitation_total"] = round(d["precipitation_total"], 1)
        d["max_cape"] = round(d["max_cape"], 0)
        d["max_lightning_potential"] = round(d["max_lightning_potential"], 1)
        d["max_wind_gust"] = round(d["max_wind_gust"], 0)
        if d["max_temperature"] is not None:
            d["max_temperature"] = round(d["max_temperature"], 1)
        if d["min_temperature"] is not None:
            d["min_temperature"] = round(d["min_temperature"], 1)
    return {"days": out}


async def fetch_storm_risk_forecast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, days: int = 7) -> Dict[str, Any]:
    days = max(1, min(int(days), 14))
    return await _cached(f"risk:{lat}:{lon}:{days}", 900.0, lambda: _fetch_storm_risk_impl(lat, lon, days))


async def _fetch_storm_risk_impl(lat: float, lon: float, days: int) -> Dict[str, Any]:
    """Daily storm risk forecast using Open-Meteo upcoming days.

    Aggregates CAPE, lightning_potential, precipitation_probability and
    thunderstorm hours per day, then assigns a 0-100 risk score.
    """
    from analysis import _risk_score  # local import to avoid cycle at module load

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "precipitation",
            "precipitation_probability",
            "weather_code",
            "cape",
            "lightning_potential",
            "wind_gusts_10m",
        ]),
        "timezone": "auto",
        "forecast_days": days,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
    data = r.json()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    by_day: Dict[str, Dict[str, Any]] = {}
    for i, t in enumerate(times):
        day = t.split("T")[0]
        b = by_day.setdefault(day, {
            "date": day,
            "max_cape": 0.0,
            "max_lightning_potential": 0.0,
            "peak_precip_probability": 0.0,
            "precipitation_total": 0.0,
            "max_wind_gust": 0.0,
            "max_temperature": None,
            "min_temperature": None,
            "thunder_hours": 0,
            "peak_hour": None,
            "_peak_score_tmp": -1.0,
        })
        cape = hourly.get("cape", [0])[i] or 0
        lp = hourly.get("lightning_potential", [0])[i] or 0
        prob = hourly.get("precipitation_probability", [0])[i] or 0
        precip = hourly.get("precipitation", [0])[i] or 0
        gust = hourly.get("wind_gusts_10m", [0])[i] or 0
        temp = hourly.get("temperature_2m", [None])[i]
        code = hourly.get("weather_code", [None])[i]

        b["max_cape"] = max(b["max_cape"], float(cape))
        b["max_lightning_potential"] = max(b["max_lightning_potential"], float(lp))
        b["peak_precip_probability"] = max(b["peak_precip_probability"], float(prob))
        b["precipitation_total"] += float(precip)
        b["max_wind_gust"] = max(b["max_wind_gust"], float(gust))
        if code in THUNDERSTORM_CODES:
            b["thunder_hours"] += 1
        if temp is not None:
            b["max_temperature"] = temp if b["max_temperature"] is None else max(b["max_temperature"], temp)
            b["min_temperature"] = temp if b["min_temperature"] is None else min(b["min_temperature"], temp)

        # Track peak hour by local convective intensity
        inst = float(cape) + float(lp) * 20 + float(prob) * 2
        if inst > b["_peak_score_tmp"]:
            b["_peak_score_tmp"] = inst
            b["peak_hour"] = t.split("T")[1][:5]

    out = sorted(by_day.values(), key=lambda d: d["date"])
    for d in out:
        d.pop("_peak_score_tmp", None)
        risk = _risk_score(d)
        d["risk"] = risk
        d["max_cape"] = round(d["max_cape"], 0)
        d["max_lightning_potential"] = round(d["max_lightning_potential"], 1)
        d["peak_precip_probability"] = round(d["peak_precip_probability"], 0)
        d["precipitation_total"] = round(d["precipitation_total"], 1)
        d["max_wind_gust"] = round(d["max_wind_gust"], 0)
        if d["max_temperature"] is not None:
            d["max_temperature"] = round(d["max_temperature"], 1)
        if d["min_temperature"] is not None:
            d["min_temperature"] = round(d["min_temperature"], 1)
    return {"days": out}


async def fetch_storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    return await _cached(f"zones:{lat}:{lon}:{radius_km}", 240.0, lambda: _fetch_storm_zones_impl(lat, lon, radius_km))


async def fetch_wind_grid(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    return await _cached(f"wind:{lat}:{lon}:{radius_km}", 300.0, lambda: _fetch_wind_grid_impl(lat, lon, radius_km))


async def _fetch_wind_grid_impl(lat: float, lon: float, radius_km: float) -> Dict[str, Any]:
    """Sample wind speed + direction at grid points to draw vector arrows."""
    points = sampling_grid(lat, lon, radius_km)
    lats = ",".join(str(p["lat"]) for p in points)
    lons = ",".join(str(p["lon"]) for p in points)
    params = {
        "latitude": lats,
        "longitude": lons,
        "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "timezone": "auto",
        "forecast_days": 1,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
    raw = r.json()

    responses = raw if isinstance(raw, list) else [raw]
    arrows: List[Dict[str, Any]] = []
    max_speed = 0.0
    for i, resp in enumerate(responses):
        p = points[i] if i < len(points) else {"lat": lat, "lon": lon}
        current = resp.get("current", {})
        speed = float(current.get("wind_speed_10m") or 0)
        direction = float(current.get("wind_direction_10m") or 0)
        gust = float(current.get("wind_gusts_10m") or 0)
        arrows.append({
            "lat": p["lat"],
            "lon": p["lon"],
            "speed": round(speed, 1),
            "direction": round(direction, 0),
            "gust": round(gust, 1),
        })
        if speed > max_speed:
            max_speed = speed
    return {
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "arrows": arrows,
        "max_speed": round(max_speed, 1),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def _fetch_storm_zones_impl(lat: float, lon: float, radius_km: float) -> Dict[str, Any]:
    """Sample the grid for active storm/convective zones around Lourdes."""
    points = sampling_grid(lat, lon, radius_km)

    # Batch all points into single Open-Meteo request (supports comma-sep lat/lon)
    lats = ",".join(str(p["lat"]) for p in points)
    lons = ",".join(str(p["lon"]) for p in points)
    params = {
        "latitude": lats,
        "longitude": lons,
        "current": "weather_code,precipitation,wind_gusts_10m",
        "hourly": "cape,lightning_potential",
        "timezone": "auto",
        "forecast_days": 1,
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
    raw = r.json()

    # Response is a list when multiple lat/lon provided
    responses = raw if isinstance(raw, list) else [raw]

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    zones: List[Dict[str, Any]] = []
    storm_active = False
    max_cape = 0.0
    max_lp = 0.0

    for i, resp in enumerate(responses):
        p = points[i] if i < len(points) else {"lat": lat, "lon": lon}
        current = resp.get("current", {})
        hourly = resp.get("hourly", {})
        times = hourly.get("time", [])
        idx = 0
        for k, t in enumerate(times):
            if t >= now_iso:
                idx = k
                break
        cape = (hourly.get("cape") or [0])[idx] if times else 0
        lp = (hourly.get("lightning_potential") or [0])[idx] if times else 0
        cape = cape or 0
        lp = lp or 0
        code = current.get("weather_code")
        precip = current.get("precipitation", 0) or 0
        gust = current.get("wind_gusts_10m", 0) or 0

        is_thunder = code in THUNDERSTORM_CODES
        # Severity score 0-100
        severity = min(100, int((cape / 30.0) + (lp * 4) + (precip * 8) + (30 if is_thunder else 0)))
        if is_thunder or severity >= 40:
            storm_active = True

        if cape > max_cape:
            max_cape = cape
        if lp > max_lp:
            max_lp = lp

        zones.append({
            "lat": p["lat"],
            "lon": p["lon"],
            "weather_code": code,
            "precipitation": precip,
            "wind_gust": gust,
            "cape": cape,
            "lightning_potential": lp,
            "is_thunder": is_thunder,
            "severity": severity,
        })

    return {
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "zones": zones,
        "storm_active": storm_active,
        "max_cape": max_cape,
        "max_lightning_potential": max_lp,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

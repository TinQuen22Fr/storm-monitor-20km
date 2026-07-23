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
                        timeout: float = 10.0, max_retries: int = 4) -> httpx.Response:
    """GET with exponential backoff on 429/503 (1, 2, 4, 8 s)."""
    last_response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries):
            try:
                r = await client.get(url, params=params, headers=headers)
                last_response = r
                if r.status_code in (429, 503):
                    if attempt >= max_retries - 1:
                        break
                    wait = float(2 ** attempt)  # 1s, 2s, 4s, 8s
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
        half = 3 if radius_km > 25 else 2
    else:
        # Fixed absolute lattice: half derived from radius, spacing constant
        half = max(1, int(radius_km // step_km))
    points: List[Dict[str, float]] = []
    dlat = km_to_deg_lat(step_km)
    dlon = km_to_deg_lon(step_km, lat)
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


# =============================================================================
# Zones + vent — GRILLE FIXE 25 POINTS (5×5), 100 % TEMPS RÉEL, ZÉRO CACHE.
# Le nombre de points n'augmente JAMAIS avec le rayon : la grille 5×5 est
# simplement étendue spatialement (espacement plus large) pour couvrir la zone.
# UNE seule requête HTTP Open-Meteo (25 coordonnées) par consultation.
# Aucun polling de fond : appel déclenché uniquement par le chargement de la
# carte ou un rafraîchissement manuel. En cas d'échec (429/panne) : erreur
# propre remontée au frontend, aucun repli sur cache.
# =============================================================================

def grid_25(lat: float, lon: float, radius_km: float) -> List[Dict[str, float]]:
    """Grille fixe 5×5 = 25 points couvrant le rayon demandé (coins sur le cercle).
    Toujours 25 points quel que soit le rayon (20 → 60 km) : seul l'espacement change."""
    step_km = float(radius_km) / (2 * math.sqrt(2))
    dlat = km_to_deg_lat(step_km)
    dlon = km_to_deg_lon(step_km, lat)
    return [
        {"lat": round(lat + i * dlat, 4), "lon": round(lon + j * dlon, 4)}
        for i in (-2, -1, 0, 1, 2) for j in (-2, -1, 0, 1, 2)
    ]


async def fetch_storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    """Zones de la carte principale — 25 points (5×5), 1 requête globale, temps réel pur.
    En cas d'échec Open-Meteo (429/timeout), bascule sur Xweather si configuré."""
    points = grid_25(lat, lon, radius_km)
    params = {
        "latitude": ",".join(str(p["lat"]) for p in points),
        "longitude": ",".join(str(p["lon"]) for p in points),
        "current": "weather_code,precipitation,wind_gusts_10m",
        "hourly": "cape,lightning_potential",
        "timezone": "UTC",
        "forecast_days": 1,
    }
    try:
        r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
    except Exception as exc:
        from xweather import is_configured, fetch_zones_xweather
        if is_configured():
            logger.warning("Open-Meteo zones failed (%s) — falling back to Xweather", type(exc).__name__)
            return await fetch_zones_xweather(points, lat, lon, radius_km)
        raise
    raw = r.json()
    responses = raw if isinstance(raw, list) else [raw]

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    zones: List[Dict[str, Any]] = []
    for i, resp in enumerate(responses):
        p = points[i] if i < len(points) else {"lat": lat, "lon": lon}
        cur = resp.get("current") or {}
        h = resp.get("hourly") or {}
        times = h.get("time") or []
        idx = times.index(now_iso) if now_iso in times else 0
        cape_list = h.get("cape") or []
        lp_list = h.get("lightning_potential") or []
        cape = float(cape_list[idx]) if idx < len(cape_list) and cape_list[idx] is not None else 0.0
        lp = float(lp_list[idx]) if idx < len(lp_list) and lp_list[idx] is not None else 0.0
        code = int(cur.get("weather_code") or 0)
        precip = float(cur.get("precipitation") or 0)
        gust = float(cur.get("wind_gusts_10m") or 0)
        is_thunder = code in THUNDERSTORM_CODES
        severity = min(100, int((cape / 30.0) + (lp * 4) + (precip * 8) + (30 if is_thunder else 0)))
        zones.append({
            "lat": p["lat"], "lon": p["lon"], "weather_code": code,
            "precipitation": precip, "wind_gust": gust, "cape": cape,
            "lightning_potential": lp, "is_thunder": is_thunder, "severity": severity,
        })
    return {
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "zones": zones,
        "storm_active": any(z["is_thunder"] or z["severity"] >= 40 for z in zones),
        "max_cape": max((z["cape"] for z in zones), default=0),
        "max_lightning_potential": max((z["lightning_potential"] for z in zones), default=0),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "live",
    }


async def fetch_wind_grid(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    """Flèches de vent — 25 points (5×5), 1 requête globale, temps réel pur.
    En cas d'échec Open-Meteo (429/timeout), bascule sur Xweather si configuré."""
    points = grid_25(lat, lon, radius_km)
    params = {
        "latitude": ",".join(str(p["lat"]) for p in points),
        "longitude": ",".join(str(p["lon"]) for p in points),
        "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "timezone": "UTC",
        "forecast_days": 1,
    }
    try:
        resp = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
    except Exception as exc:
        from xweather import is_configured, fetch_wind_xweather
        if is_configured():
            logger.warning("Open-Meteo wind failed (%s) — falling back to Xweather", type(exc).__name__)
            return await fetch_wind_xweather(points, lat, lon, radius_km)
        raise
    raw = resp.json()
    responses = raw if isinstance(raw, list) else [raw]

    arrows: List[Dict[str, Any]] = []
    max_speed = 0.0
    for i, r in enumerate(responses):
        p = points[i] if i < len(points) else {"lat": lat, "lon": lon}
        cur = r.get("current") or {}
        speed = float(cur.get("wind_speed_10m") or 0)
        direction = float(cur.get("wind_direction_10m") or 0)
        gust = float(cur.get("wind_gusts_10m") or 0)
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
        "source": "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_rain_nowcast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
    """Prévision pluie imminente — Open-Meteo minutely_15 (AROME 1,5 km), 1 point, 8 pas (2 h)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "minutely_15": "precipitation",
        "forecast_minutely_15": 8,
        "timezone": "UTC",
    }
    r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15)
    raw = r.json()
    m = raw.get("minutely_15") or {}
    times = m.get("time") or []
    precs = m.get("precipitation") or []
    now = datetime.now(timezone.utc)
    slots = []
    for t, p in zip(times, precs):
        start = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        minutes = (start - now).total_seconds() / 60.0
        slots.append({"time": t, "in_minutes": round(minutes), "precipitation": float(p or 0)})
    raining_now = any(s["precipitation"] > 0.05 and s["in_minutes"] <= 0 < s["in_minutes"] + 15 for s in slots)
    next_rain = next((s for s in slots if s["in_minutes"] > 0 and s["precipitation"] > 0.05), None)
    return {
        "lat": lat,
        "lon": lon,
        "raining_now": raining_now,
        "next_rain_minutes": next_rain["in_minutes"] if next_rain else None,
        "next_rain_mm": next_rain["precipitation"] if next_rain else None,
        "slots": slots,
        "source": "open-meteo-minutely15",
        "fetched_at": now.isoformat(),
    }

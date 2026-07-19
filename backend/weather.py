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
    """GET with exponential backoff on 429/503.

    Open-Meteo's free tier shares a per-IP minute-bucket limit. When a user
    rapidly toggles params on the Forecast map, several big multi-location
    calls can stack up in <2s. We retry up to 4 times with backoff
    `2 ** attempt` (1, 2, 4, 8 s) — total worst-case wait ≈15s before
    surrendering. This stays under the FastAPI request timeout while giving
    the rate-limit window enough room to drain."""
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
# BULK LOCAL "zones + vent" — même philosophie que la carte France :
# UN fetch périodique (rafraîchisseur nocturne/6 h) → fichier cache local →
# toute la journée les requêtes utilisateurs sont servies depuis CE fichier,
# ZÉRO appel Open-Meteo déclenché par la consultation.
# Grille maîtresse ABSOLUE : maillage fixe 8 km couvrant 60 km. La sévérité
# d'un point est une valeur absolue ; le rayon = pur filtre spatial.
# =============================================================================
MASTER_ZONE_RADIUS_KM = 60.0
MASTER_ZONE_STEP_KM = 8.0
ZONE_CHUNK_SIZE = 85          # limite Open-Meteo : 100 coordonnées / requête
ZONES_BULK_TTL_S = 6 * 3600.0  # 4 refreshs/jour max ≈ 708 appels/j (quota 10k)
ZONES_BULK_VARS = [
    "weather_code", "cape", "lightning_potential", "precipitation",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]
ZONES_BULK_FILE = Path(__file__).parent / "cache" / "zones_bulk.json"

_zones_bulk_mem: Dict[str, Dict[str, Any]] = {}
_zones_bulk_lock = asyncio.Lock()
_zones_bulk_disk_loaded = False


def _zb_key(lat: float, lon: float) -> str:
    return f"{round(float(lat), 3)}:{round(float(lon), 3)}"


def _zb_save_disk() -> None:
    try:
        ZONES_BULK_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Ne garde que les 6 centres les plus récents (Lourdes + favoris)
        keys = sorted(_zones_bulk_mem, key=lambda k: _zones_bulk_mem[k]["fetched_at"], reverse=True)[:6]
        payload = {k: _zones_bulk_mem[k] for k in keys}
        tmp = ZONES_BULK_FILE.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        tmp.replace(ZONES_BULK_FILE)
    except Exception as e:
        logger.warning("Zones bulk : écriture disque impossible (%s)", e)


def _zb_load_disk() -> None:
    global _zones_bulk_disk_loaded
    _zones_bulk_disk_loaded = True
    if not ZONES_BULK_FILE.exists():
        return
    try:
        with ZONES_BULK_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            _zones_bulk_mem.setdefault(k, v)
        logger.info("Zones bulk : %d centre(s) rechargé(s) depuis le disque", len(data))
    except Exception as e:
        logger.warning("Zones bulk : lecture disque impossible (%s)", e)


async def get_zones_bulk(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
    """Snapshot bulk (177 pts × 48 h × 7 variables) pour un centre donné.
    Mémoire → disque → fetch. En cas d'échec réseau : sert le cache local
    périmé (et retentera au prochain passage du rafraîchisseur)."""
    key = _zb_key(lat, lon)
    now = time.time()
    snap = _zones_bulk_mem.get(key)
    if snap and now - snap["fetched_at"] < ZONES_BULK_TTL_S:
        return snap
    async with _zones_bulk_lock:
        if not _zones_bulk_disk_loaded:
            _zb_load_disk()
        snap = _zones_bulk_mem.get(key)
        if snap and now - snap["fetched_at"] < ZONES_BULK_TTL_S:
            return snap
        try:
            fresh = await _fetch_zones_bulk_impl(lat, lon)
            _zones_bulk_mem[key] = fresh
            try:
                asyncio.create_task(asyncio.to_thread(_zb_save_disk))
            except RuntimeError:
                pass
            return fresh
        except Exception as e:
            if snap is not None:
                logger.warning(
                    "Zones bulk : refresh impossible (%s) — cache local servi (age %.1f h)",
                    type(e).__name__, (now - snap["fetched_at"]) / 3600,
                )
                return snap
            raise


async def _fetch_zones_bulk_impl(lat: float, lon: float) -> Dict[str, Any]:
    """LE seul point d'accès réseau zones/vent : grille maîtresse complète,
    48 h de données horaires, par lots ≤ 85 coordonnées."""
    points = sampling_grid(lat, lon, MASTER_ZONE_RADIUS_KM, step_km=MASTER_ZONE_STEP_KM)
    responses: List[Dict[str, Any]] = []
    for start in range(0, len(points), ZONE_CHUNK_SIZE):
        chunk = points[start:start + ZONE_CHUNK_SIZE]
        params = {
            "latitude": ",".join(str(p["lat"]) for p in chunk),
            "longitude": ",".join(str(p["lon"]) for p in chunk),
            "hourly": ",".join(ZONES_BULK_VARS),
            "timezone": "UTC",
            "forecast_days": 2,
        }
        r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=40)
        raw = r.json()
        responses.extend(raw if isinstance(raw, list) else [raw])

    times: List[str] = []
    series: Dict[str, List[List[Any]]] = {v: [] for v in ZONES_BULK_VARS}
    for resp in responses:
        h = resp.get("hourly") or {}
        if not times:
            times = h.get("time") or []
        for v in ZONES_BULK_VARS:
            series[v].append(h.get(v) or [])

    snap = {
        "fetched_at": time.time(),
        "fetched_at_iso": datetime.now(timezone.utc).isoformat(),
        "center": {"lat": lat, "lon": lon},
        "points": [{"lat": p["lat"], "lon": p["lon"]} for p in points],
        "times": times,
        "series": series,
    }
    logger.info(
        "Zones bulk : %d points × %d heures × %d variables rafraîchis",
        len(points), len(times), len(ZONES_BULK_VARS),
    )
    return snap


def _zb_hour_index(times: List[str]) -> int:
    """Index de l'heure courante (UTC) dans le snapshot ; borné aux limites."""
    if not times:
        return 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    for k, t in enumerate(times):
        if t >= now_iso:
            return k
    return len(times) - 1


def _zb_val(snap: Dict[str, Any], var: str, i: int, idx: int) -> float:
    try:
        v = snap["series"][var][i][idx]
        return float(v) if v is not None else 0.0
    except (IndexError, KeyError, TypeError, ValueError):
        return 0.0


def _zones_master_from_bulk(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Construit l'état des zones depuis le snapshot local (repli/watcher)."""
    idx = _zb_hour_index(snap["times"])
    zones: List[Dict[str, Any]] = []
    for i, p in enumerate(snap["points"]):
        cape = _zb_val(snap, "cape", i, idx)
        lp = _zb_val(snap, "lightning_potential", i, idx)
        precip = _zb_val(snap, "precipitation", i, idx)
        gust = _zb_val(snap, "wind_gusts_10m", i, idx)
        code = int(_zb_val(snap, "weather_code", i, idx))
        is_thunder = code in THUNDERSTORM_CODES
        severity = min(100, int((cape / 30.0) + (lp * 4) + (precip * 8) + (30 if is_thunder else 0)))
        zones.append({
            "lat": p["lat"], "lon": p["lon"], "weather_code": code,
            "precipitation": precip, "wind_gust": gust, "cape": cape,
            "lightning_potential": lp, "is_thunder": is_thunder, "severity": severity,
        })
    return {
        "center": snap["center"],
        "zones": zones,
        "fetched_at": snap["fetched_at_iso"],
        "source": "cache_local",
    }


async def _fetch_zones_live(lat: float, lon: float) -> Dict[str, Any]:
    """Zones EN DIRECT (champ `current` + heure courante). Repli automatique
    sur le snapshot local si Open-Meteo est indisponible."""
    points = sampling_grid(lat, lon, MASTER_ZONE_RADIUS_KM, step_km=MASTER_ZONE_STEP_KM)
    try:
        responses: List[Dict[str, Any]] = []
        for start in range(0, len(points), ZONE_CHUNK_SIZE):
            chunk = points[start:start + ZONE_CHUNK_SIZE]
            params = {
                "latitude": ",".join(str(p["lat"]) for p in chunk),
                "longitude": ",".join(str(p["lon"]) for p in chunk),
                "current": "weather_code,precipitation,wind_gusts_10m",
                "hourly": "cape,lightning_potential",
                "timezone": "UTC",
                "forecast_days": 1,
            }
            r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=30)
            raw = r.json()
            responses.extend(raw if isinstance(raw, list) else [raw])
    except Exception as e:
        logger.warning("Zones : direct indisponible (%s) — repli sur le cache local", type(e).__name__)
        return _zones_master_from_bulk(await get_zones_bulk(lat, lon))

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
        "zones": zones,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "live",
    }


def _filter_zones(master: Dict[str, Any], lat: float, lon: float, radius_km: float) -> Dict[str, Any]:
    r = min(float(radius_km), MASTER_ZONE_RADIUS_KM)
    zones = [z for z in master["zones"] if haversine_km(lat, lon, z["lat"], z["lon"]) <= r]
    return {
        "center": master["center"],
        "radius_km": radius_km,
        "zones": zones,
        "storm_active": any(z["is_thunder"] or z["severity"] >= 40 for z in zones),
        "max_cape": max((z["cape"] for z in zones), default=0),
        "max_lightning_potential": max((z["lightning_potential"] for z in zones), default=0),
        "fetched_at": master["fetched_at"],
        "source": master.get("source", "live"),
    }


async def fetch_storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    """Zones de la carte principale — DONNÉES EN DIRECT (règle : seule la page
    Prévisions exploite le cache journalier ; le reste est live).
    Cache anti-rafale 240 s ; repli cache local uniquement en cas de panne."""
    master = await _cached(f"zones-live:{lat}:{lon}", 240.0, lambda: _fetch_zones_live(lat, lon))
    return _filter_zones(master, lat, lon, radius_km)


async def fetch_storm_zones_local(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    """Variante SANS appel réseau (snapshot local) — réservée au guetteur
    d'alertes en arrière-plan pour ne rien consommer 24h/24."""
    snap = await get_zones_bulk(lat, lon)
    return _filter_zones(_zones_master_from_bulk(snap), lat, lon, radius_km)


async def fetch_wind_grid(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    """Flèches de vent — données EN DIRECT (champ `current` Open-Meteo).

    Le vent est activé ponctuellement par l'utilisateur : l'appel direct ne
    pèse presque rien sur le quota (cache 10 min anti-spam). Si Open-Meteo
    est indisponible (429/panne), repli automatique sur la découpe du
    snapshot bulk local (donnée horaire prévue, marquée `source`)."""
    return await _cached(f"wind:{lat}:{lon}:{radius_km}", 600.0, lambda: _fetch_wind_grid_live(lat, lon, radius_km))


async def _fetch_wind_grid_live(lat: float, lon: float, radius_km: float) -> Dict[str, Any]:
    r = min(float(radius_km), MASTER_ZONE_RADIUS_KM)
    pts = [
        p for p in sampling_grid(lat, lon, MASTER_ZONE_RADIUS_KM, step_km=MASTER_ZONE_STEP_KM)
        if haversine_km(lat, lon, p["lat"], p["lon"]) <= r
    ]
    try:
        responses: List[Dict[str, Any]] = []
        for start in range(0, len(pts), ZONE_CHUNK_SIZE):
            chunk = pts[start:start + ZONE_CHUNK_SIZE]
            params = {
                "latitude": ",".join(str(p["lat"]) for p in chunk),
                "longitude": ",".join(str(p["lon"]) for p in chunk),
                "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
                "timezone": "UTC",
                "forecast_days": 1,
            }
            resp = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=20)
            raw = resp.json()
            responses.extend(raw if isinstance(raw, list) else [raw])
    except Exception as e:
        logger.warning("Vent : direct indisponible (%s) — repli sur le cache local", type(e).__name__)
        return await _wind_grid_from_bulk(lat, lon, radius_km)

    arrows: List[Dict[str, Any]] = []
    max_speed = 0.0
    for i, resp in enumerate(responses):
        p = pts[i] if i < len(pts) else {"lat": lat, "lon": lon}
        cur = resp.get("current") or {}
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


async def _wind_grid_from_bulk(lat: float, lon: float, radius_km: float) -> Dict[str, Any]:
    """Repli : découpe du snapshot bulk local (prévision horaire)."""
    snap = await get_zones_bulk(lat, lon)
    idx = _zb_hour_index(snap["times"])
    r = min(float(radius_km), MASTER_ZONE_RADIUS_KM)
    arrows: List[Dict[str, Any]] = []
    max_speed = 0.0
    for i, p in enumerate(snap["points"]):
        if haversine_km(lat, lon, p["lat"], p["lon"]) > r:
            continue
        speed = _zb_val(snap, "wind_speed_10m", i, idx)
        direction = _zb_val(snap, "wind_direction_10m", i, idx)
        gust = _zb_val(snap, "wind_gusts_10m", i, idx)
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
        "center": snap["center"],
        "radius_km": radius_km,
        "arrows": arrows,
        "max_speed": round(max_speed, 1),
        "source": "cache_local",
        "fetched_at": snap["fetched_at_iso"],
    }

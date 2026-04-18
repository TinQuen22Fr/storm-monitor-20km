"""Open-Meteo client for thunderstorm tracking around Lourdes."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

# Lourdes center coordinates
LOURDES_LAT = 43.0951
LOURDES_LON = -0.0434
RADIUS_KM = 20.0

# Weather codes indicating thunderstorm activity
THUNDERSTORM_CODES = {95, 96, 99}
# Rain/shower codes indicating active precipitation
RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82}

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"


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


def sampling_grid(lat: float, lon: float, radius_km: float, step_km: float = 7.0) -> List[Dict[str, float]]:
    """Return a list of lat/lon points in a grid within the given radius."""
    points: List[Dict[str, float]] = []
    dlat = km_to_deg_lat(step_km)
    dlon = km_to_deg_lon(step_km, lat)
    # 5x5 grid
    for i in range(-2, 3):
        for j in range(-2, 3):
            plat = lat + i * dlat
            plon = lon + j * dlon
            if haversine_km(lat, lon, plat, plon) <= radius_km:
                points.append({"lat": round(plat, 4), "lon": round(plon, 4)})
    return points


async def fetch_current(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
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
        "timezone": "Europe/Paris",
        "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(OPEN_METEO_BASE, params=params)
        r.raise_for_status()
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
    }


async def fetch_forecast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON) -> Dict[str, Any]:
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
        "timezone": "Europe/Paris",
        "forecast_days": 2,
        "past_hours": 0,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(OPEN_METEO_BASE, params=params)
        r.raise_for_status()
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
        "timezone": "Europe/Paris",
        "past_days": 1,
        "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(OPEN_METEO_BASE, params=params)
        r.raise_for_status()
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


async def fetch_storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM) -> Dict[str, Any]:
    """Sample the grid for active storm/convective zones around Lourdes."""
    points = sampling_grid(lat, lon, radius_km, step_km=7.0)

    # Batch all points into single Open-Meteo request (supports comma-sep lat/lon)
    lats = ",".join(str(p["lat"]) for p in points)
    lons = ",".join(str(p["lon"]) for p in points)
    params = {
        "latitude": lats,
        "longitude": lons,
        "current": "weather_code,precipitation,wind_gusts_10m",
        "hourly": "cape,lightning_potential",
        "timezone": "Europe/Paris",
        "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(OPEN_METEO_BASE, params=params)
        r.raise_for_status()
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

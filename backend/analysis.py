"""Storm approach analysis + multi-day storm risk forecast helpers."""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from (lat1,lon1) to (lat2,lon2) in degrees [0-360)."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = math.degrees(math.atan2(y, x))
    return (brg + 360.0) % 360.0


def compass_fr(bearing: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
    i = int((bearing + 11.25) // 22.5) % 16
    return dirs[i]


def analyze_approach(center_lat: float, center_lon: float, strikes: List[Dict[str, Any]], now: Optional[float] = None) -> Dict[str, Any]:
    """Detect whether strikes are approaching the center and compute ETA.

    Strategy:
      - Keep only strikes in the last 60 min.
      - If fewer than 3 strikes, return {approaching: False}.
      - Split in two halves by time (oldest vs newest).
      - Compare median distance of oldest half vs newest half.
      - If newest is significantly closer (>= 2 km), we consider it approaching.
      - Speed = (d_old - d_new) / dt (hours); ETA (min) = d_new / speed * 60.
      - Bearing = from newest (closest) strike to center.
    """
    now = now or time.time()
    recent = [s for s in strikes if now - s["ts"] <= 3600]
    if len(recent) < 3:
        return {"approaching": False, "reason": "not_enough_strikes", "count": len(recent)}

    recent.sort(key=lambda s: s["ts"])  # oldest first

    n = len(recent)
    mid = n // 2
    old_half = recent[:mid] or recent[:1]
    new_half = recent[mid:]

    def median(xs: List[float]) -> float:
        xs = sorted(xs)
        m = len(xs)
        if m == 0:
            return 0.0
        if m % 2:
            return xs[m // 2]
        return (xs[m // 2 - 1] + xs[m // 2]) / 2.0

    d_old = median([float(s["distance_km"]) for s in old_half])
    d_new = median([float(s["distance_km"]) for s in new_half])

    t_old = sum(s["ts"] for s in old_half) / len(old_half)
    t_new = sum(s["ts"] for s in new_half) / len(new_half)
    dt_h = max((t_new - t_old) / 3600.0, 1 / 60.0)

    approach_km = d_old - d_new  # positive means approaching
    speed_kmh = approach_km / dt_h
    min_distance = min(float(s["distance_km"]) for s in new_half)

    approaching = approach_km >= 2.0 and speed_kmh > 5.0

    eta_min: Optional[float] = None
    if approaching and speed_kmh > 0:
        eta_min = (min_distance / speed_kmh) * 60.0

    closest = min(new_half, key=lambda s: float(s["distance_km"]))
    brg = _bearing_deg(float(closest["lat"]), float(closest["lon"]), center_lat, center_lon)
    from_brg = (brg + 180.0) % 360.0

    return {
        "approaching": approaching,
        "count": n,
        "distance_old_km": round(d_old, 1),
        "distance_new_km": round(d_new, 1),
        "min_distance_km": round(min_distance, 1),
        "approach_km_over_interval": round(approach_km, 1),
        "interval_min": round(dt_h * 60.0, 1),
        "speed_kmh": round(speed_kmh, 1) if approaching else None,
        "eta_min": round(eta_min, 1) if eta_min is not None else None,
        "from_bearing": round(from_brg, 1),
        "from_compass": compass_fr(from_brg),
    }


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _find_dominant_cluster(strikes: List[Dict[str, Any]], eps_km: float = 25.0, min_points: int = 4) -> List[Dict[str, Any]]:
    """Return the largest spatially-coherent cluster of strikes.

    Simple DBSCAN-like grid clustering: assigns each strike to a 0.25°x0.25°
    grid cell (~25 km), picks the cell with the most strikes PLUS its
    immediate neighbours. This removes the "many dispersed cells" noise
    problem that produces 4000 km/h fake trajectories.
    """
    if not strikes:
        return []

    # Bucket by 0.25° grid (~27 km at 43°N)
    grid: Dict[tuple, List[Dict[str, Any]]] = {}
    for s in strikes:
        key = (round(float(s["lat"]) * 4) / 4, round(float(s["lon"]) * 4) / 4)
        grid.setdefault(key, []).append(s)

    # Pick most populated cell
    best_key = max(grid, key=lambda k: len(grid[k]))
    if len(grid[best_key]) < min_points:
        return []

    # Include neighbours (9-cell neighbourhood)
    lat0, lon0 = best_key
    cluster: List[Dict[str, Any]] = []
    for dlat in (-0.25, 0, 0.25):
        for dlon in (-0.25, 0, 0.25):
            cluster.extend(grid.get((lat0 + dlat, lon0 + dlon), []))

    return cluster


def predict_trajectory(
    center_lat: float,
    center_lon: float,
    strikes: List[Dict[str, Any]],
    now: Optional[float] = None,
    project_minutes: int = 45,
) -> Dict[str, Any]:
    """Linear-regression trajectory prediction of the dominant storm cell.

    Steps:
      1. Keep strikes from last 60 min only.
      2. Cluster spatially (0.25° grid + neighbours) → isolate the dominant cell.
      3. Fit lat(t) & lon(t) linearly on the cluster.
      4. Project forward, compute speed/bearing/ETA.
    """
    now = now or time.time()
    recent = [s for s in strikes if now - s["ts"] <= 3600]
    if len(recent) < 4:
        return {"detected": False, "reason": "not_enough_strikes", "count": len(recent)}

    # Isolate dominant cluster to avoid dispersed-noise regressions
    cluster = _find_dominant_cluster(recent, eps_km=25.0, min_points=4)
    if len(cluster) < 4:
        return {
            "detected": False,
            "reason": "no_dominant_cluster",
            "count": len(recent),
        }

    # Sort by time and keep the last 20 to limit noise
    cluster.sort(key=lambda s: s["ts"])
    cluster = cluster[-20:]

    ts = [float(s["ts"]) for s in cluster]
    lats = [float(s["lat"]) for s in cluster]
    lons = [float(s["lon"]) for s in cluster]

    t0 = ts[0]
    x = [(t - t0) / 60.0 for t in ts]
    n = len(x)
    mean_x = sum(x) / n
    mean_lat = sum(lats) / n
    mean_lon = sum(lons) / n

    var_x = sum((xi - mean_x) ** 2 for xi in x)
    if var_x == 0:
        return {"detected": False, "reason": "static_centroid"}

    slope_lat = sum((xi - mean_x) * (lat - mean_lat) for xi, lat in zip(x, lats)) / var_x
    slope_lon = sum((xi - mean_x) * (lon - mean_lon) for xi, lon in zip(x, lons)) / var_x

    now_min = (now - t0) / 60.0

    def at(minute_offset: float) -> Dict[str, float]:
        m = now_min + minute_offset
        plat = mean_lat + slope_lat * (m - mean_x)
        plon = mean_lon + slope_lon * (m - mean_x)
        return {
            "lat": round(plat, 4),
            "lon": round(plon, 4),
            "t_offset_min": minute_offset,
        }

    waypoints: List[Dict[str, float]] = [at(0)]
    for off in range(10, project_minutes + 1, 10):
        waypoints.append(at(off))

    p1 = at(0)
    p2 = at(60)
    hourly_km = _haversine(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
    speed_kmh = round(hourly_km, 1)

    # Reject noisy regressions even after clustering
    if speed_kmh > 120.0:
        return {
            "detected": False,
            "reason": "noise_too_high",
            "computed_speed_kmh": speed_kmh,
            "count": n,
        }
    if speed_kmh < 3.0:
        return {
            "detected": False,
            "reason": "stationary",
            "computed_speed_kmh": speed_kmh,
            "count": n,
        }

    eta_min: Optional[float] = None
    min_distance: float = _haversine(p1["lat"], p1["lon"], center_lat, center_lon)
    for off in range(0, project_minutes + 1, 5):
        w = at(off)
        d = _haversine(w["lat"], w["lon"], center_lat, center_lon)
        if d < min_distance:
            min_distance = d
            if d <= 10.0 and eta_min is None:
                eta_min = off

    bearing = _bearing_deg(p1["lat"], p1["lon"], p2["lat"], p2["lon"])

    return {
        "detected": True,
        "count": n,
        "waypoints": waypoints,
        "speed_kmh": speed_kmh,
        "bearing_deg": round(bearing, 0),
        "compass": compass_fr(bearing),
        "eta_min": eta_min,
        "closest_distance_km": round(min_distance, 1),
    }


# ---------- Multi-day storm risk forecast ----------

def _risk_score(day: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a 0-100 risk score and label for a given aggregated day."""
    cape = float(day.get("max_cape") or 0)
    lp = float(day.get("max_lightning_potential") or 0)
    prob = float(day.get("peak_precip_probability") or 0)
    thunder_h = int(day.get("thunder_hours") or 0)

    # Weighted combination
    score = 0.0
    score += min(cape / 30.0, 40.0)  # up to 40 points from CAPE
    score += min(lp * 5.0, 20.0)  # up to 20 from lightning_potential
    score += min(prob * 0.25, 25.0)  # up to 25 from rain probability
    score += min(thunder_h * 7.0, 35.0)  # up to 35 if several thunder hours
    score = min(round(score), 100)

    if score >= 75:
        label = "Extrême"
        color = "#991B1B"
    elif score >= 55:
        label = "Élevé"
        color = "#DC2626"
    elif score >= 35:
        label = "Modéré"
        color = "#EA580C"
    elif score >= 15:
        label = "Faible"
        color = "#D97706"
    else:
        label = "Nul"
        color = "#10B981"

    return {"score": int(score), "label": label, "color": color}

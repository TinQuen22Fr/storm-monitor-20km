"""Reconstituted demo storms for the Replay/Video showcase.

These are NOT real Blitzortung archive data (no public archive API exists).
They are plausible reconstructions of recent Pyrenees thunderstorm patterns
(spring cévenol type) intended to demonstrate Replay + MP4 export features.

Each demo storm contains a list of synthetic strikes with realistic:
- centroid drift (SW → NE typical for Pyrenees foothills)
- temporal density (peak in the middle, taper at edges)
- spatial spread within ~30 km of Lourdes
- intensity peaks (15-25 strikes/10min at climax)
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List


def _generate_pyrenees_storm(
    center_lat: float,
    center_lon: float,
    start_ts: float,
    duration_s: int = 2700,  # 45 min
    n_strikes: int = 62,
    drift_km: float = 18.0,  # Total cell drift over the event
    drift_bearing_deg: float = 45.0,  # NE direction (typical Pyrenees foothill flow)
    spread_km: float = 8.0,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Build a coherent thunderstorm of N strikes with believable physics."""
    rnd = random.Random(seed)

    # Convert bearing (compass deg) to cartesian unit vector in lat/lon
    # 1° lat ≈ 111 km, 1° lon ≈ 111 * cos(lat) km
    cos_lat = math.cos(math.radians(center_lat))
    bearing_rad = math.radians(drift_bearing_deg)
    drift_dlat = (drift_km * math.cos(bearing_rad)) / 111.0
    drift_dlon = (drift_km * math.sin(bearing_rad)) / (111.0 * cos_lat)

    # Start the cell SW of the centroid so it drifts through Lourdes
    cell_lat0 = center_lat - drift_dlat / 2
    cell_lon0 = center_lon - drift_dlon / 2

    strikes = []
    # Time distribution: gaussian-ish around middle (more strikes mid-event)
    middle = duration_s / 2.0
    sigma = duration_s / 4.0
    for i in range(n_strikes):
        # Draw a time biased toward the middle
        t_offset = max(0, min(duration_s,
                              rnd.gauss(middle, sigma)))
        # Cell position at this t
        progress = t_offset / duration_s
        cell_lat = cell_lat0 + drift_dlat * progress
        cell_lon = cell_lon0 + drift_dlon * progress
        # Strike scatter around cell (km radius gaussian)
        scatter_dlat = rnd.gauss(0, spread_km / 3) / 111.0
        scatter_dlon = rnd.gauss(0, spread_km / 3) / (111.0 * cos_lat)
        s_lat = cell_lat + scatter_dlat
        s_lon = cell_lon + scatter_dlon
        strikes.append({
            "lat": round(s_lat, 4),
            "lon": round(s_lon, 4),
            "ts": start_ts + t_offset,
            "demo": True,
        })
    strikes.sort(key=lambda s: s["ts"])
    return strikes


# Lourdes coordinates
LOURDES_LAT = 43.0951
LOURDES_LON = -0.0434


# Demo manifest: each entry self-describes a complete replay-able event
DEMOS: List[Dict[str, Any]] = [
    {
        "id": "demo-pyrenees-cevenol",
        "label": "Orage cévenol · Pyrénées",
        "subtitle": "Reconstitution — type fin avril sur Lourdes",
        "description": (
            "Cellule orageuse de fin d'après-midi traversant les Pyrénées du sud-ouest "
            "vers le nord-est, avec un pic d'activité vers 16h25 (45 min, ~60 impacts)."
        ),
        # Use a fixed synthetic timestamp anchored "yesterday at 15:50 local"
        # so the demo always feels recent without depending on real archive data.
        "anchor_offset_hours": -22,  # ~22h ago — keeps it inside the 24h replay window
        "duration_min": 45,
        "n_strikes": 62,
        "drift_km": 18.0,
        "drift_bearing_deg": 45.0,
        "spread_km": 7.0,
        "seed": 1428,
    },
    {
        "id": "demo-cellule-isolee",
        "label": "Cellule isolée · Argelès-Gazost",
        "subtitle": "Reconstitution — cellule courte mais intense",
        "description": (
            "Cellule unique très électrique de courte durée (20 min, ~32 impacts) "
            "stationnaire au sud de Lourdes — typique des soirées chaudes d'avril."
        ),
        "anchor_offset_hours": -10,
        "duration_min": 20,
        "n_strikes": 32,
        "drift_km": 4.0,
        "drift_bearing_deg": 20.0,
        "spread_km": 5.0,
        "seed": 2025,
    },
]


def _resolve_strikes(demo: Dict[str, Any], now: float) -> List[Dict[str, Any]]:
    start_ts = now + demo["anchor_offset_hours"] * 3600
    return _generate_pyrenees_storm(
        center_lat=LOURDES_LAT,
        center_lon=LOURDES_LON,
        start_ts=start_ts,
        duration_s=demo["duration_min"] * 60,
        n_strikes=demo["n_strikes"],
        drift_km=demo["drift_km"],
        drift_bearing_deg=demo["drift_bearing_deg"],
        spread_km=demo["spread_km"],
        seed=demo["seed"],
    )


def list_demo_events(now: float) -> List[Dict[str, Any]]:
    """Return demo events as Replay-event payloads (mirrors /api/replay/events shape)."""
    out = []
    for demo in DEMOS:
        strikes = _resolve_strikes(demo, now)
        if not strikes:
            continue
        start = strikes[0]["ts"]
        end = strikes[-1]["ts"]
        # Compute peak 10-min rate
        peak = 0
        left = 0
        for right in range(len(strikes)):
            while strikes[right]["ts"] - strikes[left]["ts"] > 600:
                left += 1
            peak = max(peak, right - left + 1)
        c_lat = sum(s["lat"] for s in strikes) / len(strikes)
        c_lon = sum(s["lon"] for s in strikes) / len(strikes)
        out.append({
            "id": demo["id"],
            "label": demo["label"],
            "subtitle": demo["subtitle"],
            "description": demo["description"],
            "is_demo": True,
            "start_ts": int(start),
            "end_ts": int(end),
            "duration_min": round((end - start) / 60.0, 1),
            "strike_count": len(strikes),
            "peak_count_10min": peak,
            "center_lat": round(c_lat, 4),
            "center_lon": round(c_lon, 4),
            "max_distance_km": 30.0,
        })
    return out


def get_demo_strikes(demo_id: str, now: float) -> List[Dict[str, Any]] | None:
    """Return the synthetic strike list for a demo, or None if unknown id."""
    for demo in DEMOS:
        if demo["id"] == demo_id:
            return _resolve_strikes(demo, now)
    return None

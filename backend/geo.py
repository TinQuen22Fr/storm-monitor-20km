"""French departement geolocation.

Loads the GeoJSON of French metropolitan departements (simplified polygons)
and exposes:
  - find_departement(lat, lon) -> code or None
  - find_neighbours(code)      -> list of codes sharing a border

Shapely is an optional dependency. If it's missing (older venv, upgrade
without --with-deps), the module loads with empty data and callers receive
None / [] so the vigilance code falls back to the historical Lourdes view.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

try:
    from shapely.geometry import Point, shape
    from shapely.prepared import prep
    _SHAPELY_OK = True
except Exception as _e:  # noqa: BLE001
    _SHAPELY_OK = False
    _SHAPELY_ERR = _e

logger = logging.getLogger(__name__)

_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "data", "departements-fr.geojson")

# Populated at import time
_DEPT_INFO: Dict[str, dict] = {}  # code -> {code, name, geom, prepared}
_ADJACENCY: Dict[str, List[str]] = {}  # code -> [neighbour codes]


def _load() -> None:
    global _DEPT_INFO, _ADJACENCY
    if not _SHAPELY_OK:
        logger.warning("geo: shapely missing (%s) — dynamic vigilance disabled, "
                       "using historical Lourdes fallback", _SHAPELY_ERR)
        return
    if not os.path.exists(_GEOJSON_PATH):
        logger.warning("geo: GeoJSON not found at %s — dynamic vigilance disabled",
                       _GEOJSON_PATH)
        return

    with open(_GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for feature in data.get("features", []):
        code = feature["properties"]["code"]
        name = feature["properties"]["nom"]
        geom = shape(feature["geometry"])
        _DEPT_INFO[code] = {
            "code": code,
            "name": name,
            "geom": geom,
            "prepared": prep(geom),
        }

    # Pre-compute adjacency (two polygons that touch or overlap share a border).
    codes = list(_DEPT_INFO.keys())
    for code_a in codes:
        prep_a = _DEPT_INFO[code_a]["prepared"]
        neigh = []
        for code_b in codes:
            if code_b == code_a:
                continue
            geom_b = _DEPT_INFO[code_b]["geom"]
            if prep_a.intersects(geom_b):
                neigh.append(code_b)
        _ADJACENCY[code_a] = neigh

    logger.info("geo: loaded %d departements, %d adjacency entries",
                len(_DEPT_INFO), sum(len(v) for v in _ADJACENCY.values()))


def find_departement(lat: float, lon: float) -> Optional[str]:
    """Return INSEE code of the departement containing (lat, lon), or None if outside FR."""
    if not _DEPT_INFO:
        return None
    pt = Point(lon, lat)
    for code, info in _DEPT_INFO.items():
        if info["prepared"].contains(pt):
            return code
    # Nearest-polygon fallback for coastal / border points (≤ ~30 km)
    best_code = None
    best_dist = float("inf")
    for code, info in _DEPT_INFO.items():
        d = info["geom"].distance(pt)
        if d < best_dist:
            best_dist = d
            best_code = code
    if best_dist <= 0.3:
        return best_code
    return None


def find_neighbours(code: str) -> List[str]:
    """Return INSEE codes of departements sharing a border with `code`."""
    return list(_ADJACENCY.get(code, []))


def get_dept_name(code: str) -> Optional[str]:
    info = _DEPT_INFO.get(code)
    return info["name"] if info else None


# Load at import — never raises
try:
    _load()
except Exception as e:  # noqa: BLE001
    logger.error("geo: failed to load GeoJSON: %s", e)


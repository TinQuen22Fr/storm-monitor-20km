"""French departement geolocation — 100% pure Python (NO shapely, NO binary).

The production server (Kimsufi, Intel Atom D425, SSSE3 only) dies with
'Illegal instruction' on shapely/GEOS wheels. Everything here is stdlib only:
  - find_departement(lat, lon) -> code or None   (bbox prefilter + ray casting)
  - find_neighbours(code)      -> list of codes  (static precomputed JSON)
  - get_dept_name(code)        -> name

Adjacency is precomputed once (data/departements-adjacence.json) — zero heavy
geometry at runtime.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_GEOJSON_PATH = os.path.join(_DATA_DIR, "departements-fr.geojson")
_ADJACENCY_PATH = os.path.join(_DATA_DIR, "departements-adjacence.json")

# code -> {"code", "name", "polygons": [ {"bbox": (minx,miny,maxx,maxy), "rings": [ring, ...]} ]}
# ring = list of (lon, lat) tuples ; rings[0] = extérieur, suivants = trous
_DEPT_INFO: Dict[str, dict] = {}
_ADJACENCY: Dict[str, List[str]] = {}


def _ring_bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def _extract_polygons(geometry: dict):
    """Normalise Polygon/MultiPolygon en liste de {'bbox', 'rings'}."""
    gtype = geometry.get("type")
    if gtype == "Polygon":
        polys = [geometry["coordinates"]]
    elif gtype == "MultiPolygon":
        polys = geometry["coordinates"]
    else:
        return []
    out = []
    for rings in polys:
        clean = [[(float(x), float(y)) for x, y in ring] for ring in rings]
        out.append({"bbox": _ring_bbox(clean[0]), "rings": clean})
    return out


def _point_in_ring(lon: float, lat: float, ring) -> bool:
    """Ray casting pair/impair — stdlib uniquement."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, poly: dict) -> bool:
    minx, miny, maxx, maxy = poly["bbox"]
    if not (minx <= lon <= maxx and miny <= lat <= maxy):
        return False
    rings = poly["rings"]
    if not _point_in_ring(lon, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _dist_point_segment_deg(px, py, ax, ay, bx, by) -> float:
    """Distance euclidienne en degrés entre un point et un segment."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _dist_to_dept_deg(lon: float, lat: float, info: dict, cutoff: float) -> float:
    """Distance min (degrés) du point au contour extérieur — early-exit bbox."""
    best = float("inf")
    for poly in info["polygons"]:
        minx, miny, maxx, maxy = poly["bbox"]
        # Distance bbox rapide : si déjà > cutoff et > best, inutile d'affiner
        ddx = max(minx - lon, 0.0, lon - maxx)
        ddy = max(miny - lat, 0.0, lat - maxy)
        if (ddx * ddx + ddy * ddy) ** 0.5 > min(best, cutoff):
            continue
        ring = poly["rings"][0]
        j = len(ring) - 1
        for i in range(len(ring)):
            d = _dist_point_segment_deg(lon, lat, ring[j][0], ring[j][1], ring[i][0], ring[i][1])
            if d < best:
                best = d
            j = i
    return best


def _load() -> None:
    global _DEPT_INFO, _ADJACENCY
    if not os.path.exists(_GEOJSON_PATH):
        logger.warning("geo: GeoJSON introuvable (%s) — vigilance dynamique désactivée",
                       _GEOJSON_PATH)
        return
    with open(_GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for feature in data.get("features", []):
        code = feature["properties"]["code"]
        name = feature["properties"]["nom"]
        _DEPT_INFO[code] = {
            "code": code,
            "name": name,
            "polygons": _extract_polygons(feature["geometry"]),
        }
    if os.path.exists(_ADJACENCY_PATH):
        with open(_ADJACENCY_PATH, "r", encoding="utf-8") as f:
            _ADJACENCY = {k: list(v) for k, v in json.load(f).items()}
    else:
        logger.warning("geo: fichier d'adjacence introuvable (%s) — voisins indisponibles",
                       _ADJACENCY_PATH)
    logger.info("geo: %d départements chargés (pur Python), %d entrées d'adjacence",
                len(_DEPT_INFO), sum(len(v) for v in _ADJACENCY.values()))


def find_departement(lat: float, lon: float) -> Optional[str]:
    """Code INSEE du département contenant (lat, lon), ou None hors France."""
    if not _DEPT_INFO:
        return None
    for code, info in _DEPT_INFO.items():
        for poly in info["polygons"]:
            if _point_in_polygon(lon, lat, poly):
                return code
    # Repli côtier/frontalier : département le plus proche à ≤ ~0.3° (~30 km)
    best_code, best_dist = None, float("inf")
    for code, info in _DEPT_INFO.items():
        d = _dist_to_dept_deg(lon, lat, info, 0.3)
        if d < best_dist:
            best_dist, best_code = d, code
    if best_dist <= 0.3:
        return best_code
    return None


def find_neighbours(code: str) -> List[str]:
    """Codes INSEE des départements limitrophes (table statique pré-calculée)."""
    return list(_ADJACENCY.get(code, []))


def get_dept_name(code: str) -> Optional[str]:
    info = _DEPT_INFO.get(code)
    return info["name"] if info else None


# Chargement à l'import — ne lève jamais
try:
    _load()
except Exception as e:  # noqa: BLE001
    logger.error("geo: échec de chargement: %s", e)

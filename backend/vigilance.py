"""Official vigilance from Météo-France via MeteoAlarm feed.

MeteoAlarm is the official European consortium aggregator of national weather
services, including Météo-France. The feed at
https://feeds.meteoalarm.org/api/v1/warnings/feeds-france returns the SAME
vigilance data shown on https://vigilance.meteofrance.fr — fully open-data,
no key required.

If MeteoAlarm is unavailable, we fall back to a locally-computed Open-Meteo
assessment so the banner is never empty.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import httpx

from weather import _cached, OPEN_METEO_BASE, get_with_retry

logger = logging.getLogger(__name__)

METEOALARM_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-france"

LEVELS_FR = {1: "vert", 2: "jaune", 3: "orange", 4: "rouge"}
LEVEL_COLORS = {
    1: "#10B981",
    2: "#F59E0B",
    3: "#EA580C",
    4: "#DC2626",
}
LEVEL_LABELS = {
    1: "Pas de vigilance particulière",
    2: "Soyez attentif",
    3: "Soyez très vigilant",
    4: "Vigilance absolue",
}

# MeteoAlarm awareness_type code → our phenomenon key
AWARENESS_TYPE_MAP = {
    "1": "vent",             # Wind
    "2": "neige",            # Snow/Ice
    "3": "orage",            # Thunderstorm
    "4": "brouillard",       # Fog
    "5": "grand-froid",      # Extreme low temp
    "6": "canicule",         # Extreme high temp
    "7": "neige",            # Coastal event (partial)
    "8": "pluie",             # Rain/flood
    "9": "pluie",             # Flood
    "10": "pluie",            # Rain
    "11": "avalanche",       # Avalanche
    "12": "vent",             # Strong wind on sea
}

PHENOMENA_META = [
    ("orage", "Orages", "⚡"),
    ("vent", "Vent violent", "🌬"),
    ("pluie", "Pluie-inondation", "🌧"),
    ("canicule", "Canicule", "🔥"),
    ("grand-froid", "Grand froid", "❄"),
    ("neige", "Neige-verglas", "🌨"),
    ("brouillard", "Brouillard", "🌫"),
    ("avalanche", "Avalanches", "🗻"),
]

# Lourdes dept (65) + neighbours. NUTS3 codes come from MeteoAlarm (FRxxx).
LOURDES_DEPTS = [
    {"id": "65", "name": "Hautes-Pyrénées", "nuts3": "FR626", "lat": 43.0951, "lon": 0.15},
    {"id": "64", "name": "Pyrénées-Atlantiques", "nuts3": "FR615", "lat": 43.30, "lon": -0.75},
    {"id": "32", "name": "Gers", "nuts3": "FR624", "lat": 43.65, "lon": 0.58},
    {"id": "31", "name": "Haute-Garonne", "nuts3": "FR623", "lat": 43.48, "lon": 1.2},
    {"id": "09", "name": "Ariège", "nuts3": "FR621", "lat": 42.95, "lon": 1.48},
    {"id": "66", "name": "Pyrénées-Orientales", "nuts3": "FR815", "lat": 42.60, "lon": 2.55},
    {"id": "40", "name": "Landes", "nuts3": "FR613", "lat": 43.95, "lon": -0.80},
]

# Full metropolitan France + DOM: INSEE dept code → NUTS3 (MeteoAlarm key)
INSEE_TO_NUTS3 = {
    "01": "FR711", "02": "FR221", "03": "FR721", "04": "FR821", "05": "FR822",
    "06": "FR823", "07": "FR712", "08": "FR211", "09": "FR621", "10": "FR212",
    "11": "FR811", "12": "FR622", "13": "FR824", "14": "FR251", "15": "FR722",
    "16": "FR531", "17": "FR532", "18": "FR241", "19": "FR631", "21": "FR261",
    "22": "FR521", "23": "FR632", "24": "FR611", "25": "FR431", "26": "FR713",
    "27": "FR231", "28": "FR242", "29": "FR522", "2A": "FR831", "2B": "FR832",
    "30": "FR812", "31": "FR623", "32": "FR624", "33": "FR612", "34": "FR813",
    "35": "FR523", "36": "FR243", "37": "FR244", "38": "FR714", "39": "FR432",
    "40": "FR613", "41": "FR245", "42": "FR715", "43": "FR723", "44": "FR511",
    "45": "FR246", "46": "FR625", "47": "FR614", "48": "FR814", "49": "FR512",
    "50": "FR252", "51": "FR213", "52": "FR214", "53": "FR513", "54": "FR411",
    "55": "FR412", "56": "FR524", "57": "FR413", "58": "FR262", "59": "FR301",
    "60": "FR222", "61": "FR253", "62": "FR302", "63": "FR724", "64": "FR615",
    "65": "FR626", "66": "FR815", "67": "FR421", "68": "FR422", "69": "FR716",
    "70": "FR433", "71": "FR263", "72": "FR514", "73": "FR717", "74": "FR718",
    "75": "FR101", "76": "FR232", "77": "FR102", "78": "FR103", "79": "FR533",
    "80": "FR223", "81": "FR627", "82": "FR628", "83": "FR825", "84": "FR826",
    "85": "FR515", "86": "FR534", "87": "FR633", "88": "FR414", "89": "FR264",
    "90": "FR434", "91": "FR104", "92": "FR105", "93": "FR106", "94": "FR107",
    "95": "FR108",
    # DOM-TOM
    "971": "FRY10", "972": "FRY20", "973": "FRY30", "974": "FRY40", "976": "FRY50",
}

# Dept label by INSEE code (metropolitan France only, for backend use)
INSEE_TO_NAME = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes", "06": "Alpes-Maritimes", "07": "Ardèche", "08": "Ardennes",
    "09": "Ariège", "10": "Aube", "11": "Aude", "12": "Aveyron", "13": "Bouches-du-Rhône",
    "14": "Calvados", "15": "Cantal", "16": "Charente", "17": "Charente-Maritime",
    "18": "Cher", "19": "Corrèze", "21": "Côte-d'Or", "22": "Côtes-d'Armor",
    "23": "Creuse", "24": "Dordogne", "25": "Doubs", "26": "Drôme", "27": "Eure",
    "28": "Eure-et-Loir", "29": "Finistère", "2A": "Corse-du-Sud", "2B": "Haute-Corse",
    "30": "Gard", "31": "Haute-Garonne", "32": "Gers", "33": "Gironde", "34": "Hérault",
    "35": "Ille-et-Vilaine", "36": "Indre", "37": "Indre-et-Loire", "38": "Isère",
    "39": "Jura", "40": "Landes", "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire",
    "44": "Loire-Atlantique", "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne",
    "48": "Lozère", "49": "Maine-et-Loire", "50": "Manche", "51": "Marne",
    "52": "Haute-Marne", "53": "Mayenne", "54": "Meurthe-et-Moselle", "55": "Meuse",
    "56": "Morbihan", "57": "Moselle", "58": "Nièvre", "59": "Nord",
    "60": "Oise", "61": "Orne", "62": "Pas-de-Calais", "63": "Puy-de-Dôme",
    "64": "Pyrénées-Atlantiques", "65": "Hautes-Pyrénées", "66": "Pyrénées-Orientales",
    "67": "Bas-Rhin", "68": "Haut-Rhin", "69": "Rhône", "70": "Haute-Saône",
    "71": "Saône-et-Loire", "72": "Sarthe", "73": "Savoie", "74": "Haute-Savoie",
    "75": "Paris", "76": "Seine-Maritime", "77": "Seine-et-Marne", "78": "Yvelines",
    "79": "Deux-Sèvres", "80": "Somme", "81": "Tarn", "82": "Tarn-et-Garonne",
    "83": "Var", "84": "Vaucluse", "85": "Vendée", "86": "Vienne",
    "87": "Haute-Vienne", "88": "Vosges", "89": "Yonne", "90": "Territoire de Belfort",
    "91": "Essonne", "92": "Hauts-de-Seine", "93": "Seine-Saint-Denis",
    "94": "Val-de-Marne", "95": "Val-d'Oise",
}

METEOALARM_URL_ANDORRA = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-andorra"

# Awareness_level: "1; green", "2; yellow", "3; orange", "4; red"
def _parse_awareness_level(val: str) -> int:
    if not val:
        return 1
    first = val.split(";")[0].strip()
    try:
        return max(1, min(4, int(first)))
    except ValueError:
        return 1


def _now_epoch() -> float:
    return time.time()


def _parse_iso(s: str) -> float:
    """Parse ISO 8601 with timezone → epoch seconds."""
    from datetime import datetime
    try:
        # Python 3.11+ accepts +02:00 directly
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


async def _fetch_meteoalarm() -> Dict[str, Any]:
    """Fetch and cache the MeteoAlarm France feed (TTL 15 min)."""
    async def _do() -> Dict[str, Any]:
        r = await get_with_retry(
            METEOALARM_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Lourdes-Storm-Tracker)",
                "Accept": "application/json",
            },
            timeout=12.0,
        )
        return r.json()

    return await _cached("vigilance:meteoalarm", ttl=900.0, fn=_do)


def _extract_dept_alerts(data: Dict[str, Any], nuts3: str) -> List[Dict[str, Any]]:
    """Return per-phenomenon max level for a given NUTS3 dept, valid NOW or NEXT 24H."""
    now = _now_epoch()
    horizon = now + 24 * 3600

    per_phen: Dict[str, Dict[str, Any]] = {}

    for w in data.get("warnings", []):
        alert = w.get("alert", {})
        for info in alert.get("info", []):
            # Only fr-FR to avoid duplicates
            if info.get("language") != "fr-FR":
                continue
            # Check if this area applies
            areas = info.get("area", [])
            matches = False
            for area in areas:
                for g in area.get("geocode", []):
                    if g.get("valueName") == "NUTS3" and g.get("value") == nuts3:
                        matches = True
                        break
                if matches:
                    break
            if not matches:
                continue

            effective = _parse_iso(info.get("effective", ""))
            expires = _parse_iso(info.get("expires", ""))
            # Only keep alerts currently active or starting within 24h
            if expires and expires < now:
                continue
            if effective and effective > horizon:
                continue

            params = {p["valueName"]: p["value"] for p in info.get("parameter", [])}
            lvl = _parse_awareness_level(params.get("awareness_level", ""))
            awareness_type = params.get("awareness_type", "").split(";")[0].strip()
            phen_key = AWARENESS_TYPE_MAP.get(awareness_type)
            if not phen_key:
                continue

            # Keep max level for this phenomenon
            cur = per_phen.get(phen_key)
            if not cur or lvl > cur["level"]:
                per_phen[phen_key] = {
                    "level": lvl,
                    "event": info.get("event", ""),
                    "description": info.get("description", ""),
                    "effective": info.get("effective", ""),
                    "expires": info.get("expires", ""),
                }

    return per_phen


def _build_phenomena(per_phen: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for key, label, icon in PHENOMENA_META:
        data = per_phen.get(key, {"level": 1})
        lvl = data.get("level", 1)
        items.append({
            "key": key,
            "label": label,
            "icon": icon,
            "level": lvl,
            "level_fr": LEVELS_FR[lvl],
            "color": LEVEL_COLORS[lvl],
            "today": lvl,  # MeteoAlarm active-now
            "tomorrow": lvl,  # Same horizon window
            "event": data.get("event"),
            "description": data.get("description"),
        })
    return items


async def _compute_from_meteoalarm() -> Dict[str, Any]:
    data = await _fetch_meteoalarm()

    results: List[Dict[str, Any]] = []
    for dept in LOURDES_DEPTS:
        per_phen = _extract_dept_alerts(data, dept["nuts3"])
        phenomena = _build_phenomena(per_phen)
        max_level = max((p["level"] for p in phenomena), default=1)
        results.append({
            "id": dept["id"],
            "name": dept["name"],
            "nuts3": dept["nuts3"],
            "lat": dept["lat"],
            "lon": dept["lon"],
            "phenomena": phenomena,
            "max_level": max_level,
            "max_level_fr": LEVELS_FR[max_level],
            "max_color": LEVEL_COLORS[max_level],
            "max_label": LEVEL_LABELS[max_level],
        })

    overall = max((r["max_level"] for r in results), default=1)
    return {
        "updated_at": int(time.time()),
        "source": "meteoalarm",
        "source_label": "Météo-France (via MeteoAlarm)",
        "source_url": "https://vigilance.meteofrance.fr/",
        "disclaimer": "Vigilance officielle Météo-France agrégée par MeteoAlarm (EUMETNET).",
        "phenomena_meta": [{"key": k, "label": label, "icon": icon} for k, label, icon in PHENOMENA_META],
        "levels_meta": [
            {"level": lv, "name": LEVELS_FR[lv], "color": LEVEL_COLORS[lv], "label": LEVEL_LABELS[lv]}
            for lv in (1, 2, 3, 4)
        ],
        "departements": results,
        "overall_level": overall,
        "overall_level_fr": LEVELS_FR[overall],
        "overall_color": LEVEL_COLORS[overall],
        "overall_label": LEVEL_LABELS[overall],
    }


# ---------- Open-Meteo fallback (used only if MeteoAlarm fails) ----------

def _thunder_level(weather_codes, cape_max, gust_max):
    thunder_hours = sum(1 for c in weather_codes if c in {95, 96, 99})
    if thunder_hours >= 3 and cape_max >= 2500:
        return 4
    if thunder_hours >= 2 or (cape_max >= 2000 and thunder_hours >= 1):
        return 3
    if thunder_hours >= 1 or cape_max >= 1500:
        return 2
    return 1


async def _compute_from_openmeteo_fallback() -> Dict[str, Any]:
    """Very simplified fallback; used only if MeteoAlarm is unreachable."""
    async def _do():
        lats = ",".join(f"{d['lat']}" for d in LOURDES_DEPTS)
        lons = ",".join(f"{d['lon']}" for d in LOURDES_DEPTS)
        params = {
            "latitude": lats, "longitude": lons,
            "hourly": "weather_code,cape",
            "daily": "weather_code,wind_gusts_10m_max,cape_max",
            "forecast_days": 1, "timezone": "auto",
        }
        r = await get_with_retry(OPEN_METEO_BASE, params=params, timeout=15.0)
        payload = r.json()
        return payload if isinstance(payload, list) else [payload]

    data_list = await _do()
    if isinstance(data_list, dict):
        data_list = [data_list]

    results = []
    for i, dept in enumerate(LOURDES_DEPTS):
        data = data_list[i] if i < len(data_list) else {}
        hourly = data.get("hourly", {}).get("weather_code", [])[:24]
        cape_h = data.get("hourly", {}).get("cape", [])[:24]
        cape_max = max([float(c or 0) for c in cape_h], default=0)
        gust_max = float((data.get("daily", {}).get("wind_gusts_10m_max") or [0])[0] or 0)
        orage_lvl = _thunder_level(hourly, cape_max, gust_max)
        phenomena = [
            {
                "key": k, "label": label, "icon": icon,
                "level": orage_lvl if k == "orage" else 1,
                "level_fr": LEVELS_FR[orage_lvl if k == "orage" else 1],
                "color": LEVEL_COLORS[orage_lvl if k == "orage" else 1],
                "today": orage_lvl if k == "orage" else 1,
                "tomorrow": orage_lvl if k == "orage" else 1,
            }
            for k, label, icon in PHENOMENA_META
        ]
        max_level = max((p["level"] for p in phenomena), default=1)
        results.append({
            "id": dept["id"], "name": dept["name"], "nuts3": dept["nuts3"],
            "lat": dept["lat"], "lon": dept["lon"],
            "phenomena": phenomena,
            "max_level": max_level,
            "max_level_fr": LEVELS_FR[max_level],
            "max_color": LEVEL_COLORS[max_level],
            "max_label": LEVEL_LABELS[max_level],
        })

    overall = max((r["max_level"] for r in results), default=1)
    return {
        "updated_at": int(time.time()),
        "source": "open-meteo-fallback",
        "source_label": "Estimation locale Open-Meteo (fallback)",
        "source_url": "https://vigilance.meteofrance.fr/",
        "disclaimer": "Source officielle MeteoAlarm temporairement indisponible — estimation locale.",
        "phenomena_meta": [{"key": k, "label": label, "icon": icon} for k, label, icon in PHENOMENA_META],
        "levels_meta": [
            {"level": lv, "name": LEVELS_FR[lv], "color": LEVEL_COLORS[lv], "label": LEVEL_LABELS[lv]}
            for lv in (1, 2, 3, 4)
        ],
        "departements": results,
        "overall_level": overall,
        "overall_level_fr": LEVELS_FR[overall],
        "overall_color": LEVEL_COLORS[overall],
        "overall_label": LEVEL_LABELS[overall],
    }


async def compute_vigilance() -> Dict[str, Any]:
    """Primary: MeteoAlarm (official MF). Fallback: Open-Meteo estimation."""
    try:
        return await _compute_from_meteoalarm()
    except Exception as e:
        logger.warning("MeteoAlarm fetch failed, falling back to Open-Meteo: %s", e)
        try:
            return await _compute_from_openmeteo_fallback()
        except Exception as e2:
            logger.error("Both vigilance sources failed: %s / %s", e, e2)
            raise



async def _fetch_meteoalarm_andorra() -> Dict[str, Any]:
    async def _do() -> Dict[str, Any]:
        r = await get_with_retry(
            METEOALARM_URL_ANDORRA,
            headers={"User-Agent": "Mozilla/5.0 (Lourdes-Storm-Tracker)", "Accept": "application/json"},
            timeout=12.0,
        )
        return r.json()
    return await _cached("vigilance:meteoalarm:andorra", ttl=900.0, fn=_do)


def _extract_level_and_phenomena_for_key(data: Dict[str, Any], geocode_value: str,
                                         geocode_name: str = "NUTS3") -> Dict[str, Any]:
    """Return {max_level, phenomena: [{key, level, event}]} for a given geocode value."""
    now = _now_epoch()
    horizon = now + 24 * 3600
    per_phen: Dict[str, Dict[str, Any]] = {}

    for w in data.get("warnings", []):
        alert = w.get("alert", {})
        for info in alert.get("info", []):
            if info.get("language") != "fr-FR":
                continue
            matches = False
            for area in info.get("area", []):
                for g in area.get("geocode", []):
                    if g.get("valueName") == geocode_name and g.get("value") == geocode_value:
                        matches = True
                        break
                if matches:
                    break
            if not matches:
                continue
            effective = _parse_iso(info.get("effective", ""))
            expires = _parse_iso(info.get("expires", ""))
            if expires and expires < now:
                continue
            if effective and effective > horizon:
                continue
            params = {p["valueName"]: p["value"] for p in info.get("parameter", [])}
            lvl = _parse_awareness_level(params.get("awareness_level", ""))
            awareness_type = params.get("awareness_type", "").split(";")[0].strip()
            phen_key = AWARENESS_TYPE_MAP.get(awareness_type)
            if not phen_key:
                continue
            cur = per_phen.get(phen_key)
            if not cur or lvl > cur["level"]:
                per_phen[phen_key] = {"level": lvl, "event": info.get("event", "")}

    phenomena = [
        {
            "key": k, "label": label, "icon": icon,
            "level": per_phen.get(k, {"level": 1})["level"],
            "level_fr": LEVELS_FR[per_phen.get(k, {"level": 1})["level"]],
            "color": LEVEL_COLORS[per_phen.get(k, {"level": 1})["level"]],
            "event": per_phen.get(k, {}).get("event"),
        }
        for k, label, icon in PHENOMENA_META
    ]
    max_level = max((p["level"] for p in phenomena), default=1)
    return {
        "max_level": max_level,
        "max_level_fr": LEVELS_FR[max_level],
        "max_color": LEVEL_COLORS[max_level],
        "max_label": LEVEL_LABELS[max_level],
        "phenomena": phenomena,
    }


async def compute_full_france_vigilance() -> Dict[str, Any]:
    """Return vigilance for all 101 French departements + Andorra."""
    try:
        fr_data = await _fetch_meteoalarm()
    except Exception as e:
        logger.warning("MeteoAlarm France fetch failed: %s", e)
        fr_data = {"warnings": []}

    try:
        ad_data = await _fetch_meteoalarm_andorra()
    except Exception as e:
        logger.warning("MeteoAlarm Andorra fetch failed: %s", e)
        ad_data = {"warnings": []}

    fr_depts = []
    for insee, nuts3 in INSEE_TO_NUTS3.items():
        entry = _extract_level_and_phenomena_for_key(fr_data, nuts3, "NUTS3")
        entry.update({
            "id": insee,
            "nuts3": nuts3,
            "name": INSEE_TO_NAME.get(insee, insee),
            "country": "FR",
        })
        fr_depts.append(entry)

    # Andorra: aggregate across all parishes ("Zone nord", "Zone est"…)
    andorra_max = 1
    andorra_phenomena: Dict[str, Dict[str, Any]] = {}
    now = _now_epoch()
    horizon = now + 24 * 3600
    for w in ad_data.get("warnings", []):
        for info in w.get("alert", {}).get("info", []):
            if info.get("language") != "fr-FR":
                continue
            expires = _parse_iso(info.get("expires", ""))
            effective = _parse_iso(info.get("effective", ""))
            if expires and expires < now:
                continue
            if effective and effective > horizon:
                continue
            params = {p["valueName"]: p["value"] for p in info.get("parameter", [])}
            lvl = _parse_awareness_level(params.get("awareness_level", ""))
            andorra_max = max(andorra_max, lvl)
            awareness_type = params.get("awareness_type", "").split(";")[0].strip()
            phen_key = AWARENESS_TYPE_MAP.get(awareness_type)
            if phen_key:
                cur = andorra_phenomena.get(phen_key)
                if not cur or lvl > cur["level"]:
                    andorra_phenomena[phen_key] = {"level": lvl, "event": info.get("event", "")}

    andorra_entry = {
        "id": "AD",
        "name": "Andorre",
        "country": "AD",
        "max_level": andorra_max,
        "max_level_fr": LEVELS_FR[andorra_max],
        "max_color": LEVEL_COLORS[andorra_max],
        "max_label": LEVEL_LABELS[andorra_max],
        "phenomena": [
            {
                "key": k, "label": label, "icon": icon,
                "level": andorra_phenomena.get(k, {"level": 1})["level"],
                "level_fr": LEVELS_FR[andorra_phenomena.get(k, {"level": 1})["level"]],
                "color": LEVEL_COLORS[andorra_phenomena.get(k, {"level": 1})["level"]],
                "event": andorra_phenomena.get(k, {}).get("event"),
            }
            for k, label, icon in PHENOMENA_META
        ],
    }

    all_entries = fr_depts + [andorra_entry]
    overall = max((e["max_level"] for e in all_entries), default=1)

    return {
        "updated_at": int(time.time()),
        "source": "meteoalarm",
        "source_label": "Météo-France + Servei Meteorològic Andorrà (via MeteoAlarm/EUMETNET)",
        "source_url": "https://feeds.meteoalarm.org/",
        "disclaimer": "Vigilance officielle agrégée par MeteoAlarm (EUMETNET).",
        "phenomena_meta": [{"key": k, "label": label, "icon": icon} for k, label, icon in PHENOMENA_META],
        "levels_meta": [
            {"level": lv, "name": LEVELS_FR[lv], "color": LEVEL_COLORS[lv], "label": LEVEL_LABELS[lv]}
            for lv in (1, 2, 3, 4)
        ],
        "areas": all_entries,
        "overall_level": overall,
        "overall_level_fr": LEVELS_FR[overall],
        "overall_color": LEVEL_COLORS[overall],
        "overall_label": LEVEL_LABELS[overall],
    }

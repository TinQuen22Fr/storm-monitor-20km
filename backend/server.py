"""FastAPI server for Lourdes thunderstorm tracker."""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from auth import (
    create_token,
    get_current_user,
    get_current_user_optional,
    hash_password,
    verify_password,
)
from weather import (
    LOURDES_LAT,
    LOURDES_LON,
    RADIUS_KM,
    fetch_current,
    fetch_forecast,
    fetch_history_24h,
    fetch_history_days,
    fetch_rain_nowcast,
    fetch_storm_risk_forecast,
    fetch_storm_zones,
    fetch_wind_grid,
)
import lightning as lightning_mod
import push as push_mod
import fcm as fcm_mod
import reports as reports_mod
import analysis as analysis_mod
import demo_storms as demo_mod
import video_export as video_mod
import severe as severe_mod
import webhooks as webhooks_mod
import uploads as uploads_mod
import vigilance as vigilance_mod
import share_card as share_card_mod
import email_service as email_mod
import secrets
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Lourdes Storm Tracker API")
api_router = APIRouter(prefix="/api")


# ---------- Models ----------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: Optional[str] = None


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class ResendVerifyInput(BaseModel):
    email: EmailStr


class VerifyTokenInput(BaseModel):
    token: str


ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").lower().strip()


async def require_admin(user=Depends(get_current_user)):
    if not ADMIN_EMAIL or user["email"].lower() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    return user


class FavoriteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float
    lon: float


class Favorite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    name: str
    lat: float
    lon: float
    created_at: str


# ---------- Meta ----------
@api_router.get("/")
async def root():
    return {"service": "lourdes-storm-tracker", "center": {"lat": LOURDES_LAT, "lon": LOURDES_LON}, "radius_km": RADIUS_KM}


@api_router.get("/health")
async def health():
    """Self-diagnostic endpoint — returns the runtime config status for debugging."""
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:  # noqa: BLE001
        mongo_ok = False
    return {
        "status": "ok" if mongo_ok else "degraded",
        "service": "storm-monitoring",
        "version": "2026-06-19",
        "mongo_connected": mongo_ok,
        "env_loaded": {
            "RESEND_API_KEY": bool(os.environ.get("RESEND_API_KEY")),
            "SENDER_EMAIL": bool(os.environ.get("SENDER_EMAIL")),
            "PUBLIC_APP_URL": os.environ.get("PUBLIC_APP_URL", ""),
            "ADMIN_EMAIL": os.environ.get("ADMIN_EMAIL", ""),
        },
        "now": datetime.now(timezone.utc).isoformat(),
    }


# ---------- Auth ----------
@api_router.post("/auth/register")
async def register(payload: RegisterInput):
    existing = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email")
    user_id = str(uuid.uuid4())
    verification_token = secrets.token_urlsafe(32)
    name = payload.name or payload.email.split("@")[0]
    is_admin = payload.email.lower() == ADMIN_EMAIL
    doc = {
        "id": user_id,
        "email": payload.email.lower(),
        "name": name,
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Admin account auto-verified, others must confirm by email
        "email_verified": is_admin,
        "verification_token": None if is_admin else verification_token,
        "is_admin": is_admin,
        "disabled": False,
    }
    await db.users.insert_one(doc)

    if is_admin:
        token = create_token(user_id, payload.email.lower())
        return {
            "ok": True,
            "auto_verified": True,
            "token": token,
            "user": {"id": user_id, "email": doc["email"], "name": name, "is_admin": True},
        }

    sent = await email_mod.send_verification_email(payload.email.lower(), name, verification_token)
    return {
        "ok": True,
        "auto_verified": False,
        "email_sent": sent,
        "message": "Compte créé. Vérifie ta boîte mail pour activer ton compte.",
    }


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginInput):
    doc = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if not doc or not verify_password(payload.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if doc.get("disabled"):
        raise HTTPException(status_code=403, detail="Ce compte a été désactivé par l'administrateur.")
    if not doc.get("email_verified", False):
        raise HTTPException(
            status_code=403,
            detail="Compte non vérifié. Clique sur le lien envoyé par mail (ou demande un nouveau lien).",
        )
    token = create_token(doc["id"], doc["email"])
    return AuthResponse(
        token=token,
        user={
            "id": doc["id"],
            "email": doc["email"],
            "name": doc.get("name", ""),
            "is_admin": doc.get("is_admin", False),
        },
    )


@api_router.post("/auth/verify-email")
async def verify_email(payload: VerifyTokenInput):
    doc = await db.users.find_one({"verification_token": payload.token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=400, detail="Lien de vérification invalide ou déjà utilisé.")
    if doc.get("email_verified"):
        return {"ok": True, "already_verified": True}
    await db.users.update_one(
        {"id": doc["id"]},
        {"$set": {"email_verified": True}, "$unset": {"verification_token": ""}},
    )
    token = create_token(doc["id"], doc["email"])
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": doc["id"],
            "email": doc["email"],
            "name": doc.get("name", ""),
            "is_admin": doc.get("is_admin", False),
        },
    }


@api_router.post("/auth/resend-verification")
async def resend_verification(payload: ResendVerifyInput):
    doc = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    # Always return ok=True to avoid email enumeration
    if doc and not doc.get("email_verified"):
        new_token = secrets.token_urlsafe(32)
        await db.users.update_one(
            {"id": doc["id"]}, {"$set": {"verification_token": new_token}}
        )
        await email_mod.send_verification_email(doc["email"], doc.get("name", ""), new_token)
    return {"ok": True, "message": "Si un compte non vérifié existe, un nouveau mail a été envoyé."}


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0, "verification_token": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return doc


# ---------- Admin ----------
@api_router.get("/admin/users")
async def admin_list_users(_=Depends(require_admin)):
    users = await db.users.find(
        {}, {"_id": 0, "password_hash": 0, "verification_token": 0}
    ).sort("created_at", -1).to_list(1000)
    # Add favorites count for each user
    for u in users:
        u["favorites_count"] = await db.favorites.count_documents({"user_id": u["id"]})
    return users


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas supprimer ton propre compte admin.")
    res = await db.users.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await db.favorites.delete_many({"user_id": user_id})
    return {"ok": True}


@api_router.post("/admin/users/{user_id}/verify")
async def admin_force_verify(user_id: str, _=Depends(require_admin)):
    res = await db.users.update_one(
        {"id": user_id},
        {"$set": {"email_verified": True}, "$unset": {"verification_token": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"ok": True}


@api_router.post("/admin/users/{user_id}/disable")
async def admin_toggle_disable(user_id: str, _=Depends(require_admin)):
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "disabled": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    new_state = not doc.get("disabled", False)
    await db.users.update_one({"id": user_id}, {"$set": {"disabled": new_state}})
    return {"ok": True, "disabled": new_state}


# ---------- Favorites ----------
@api_router.get("/favorites", response_model=List[Favorite])
async def list_favorites(user=Depends(get_current_user)):
    docs = await db.favorites.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    return docs


@api_router.post("/favorites", response_model=Favorite)
async def create_favorite(payload: FavoriteCreate, user=Depends(get_current_user)):
    fav = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "name": payload.name,
        "lat": payload.lat,
        "lon": payload.lon,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.favorites.insert_one(fav)
    return {k: v for k, v in fav.items() if k != "_id"}


@api_router.delete("/favorites/{fav_id}")
async def delete_favorite(fav_id: str, user=Depends(get_current_user)):
    res = await db.favorites.delete_one({"id": fav_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Favori introuvable")
    return {"ok": True}


# ---------- Weather ----------
def _degraded(kind: str, error: Exception) -> Dict[str, Any]:
    """Return a safe empty payload when upstream is unavailable."""
    logger.warning("Upstream failure on %s: %s", kind, type(error).__name__)
    base = {
        "degraded": True,
        "source_error": str(error)[:120],
        "message": "Service météo temporairement indisponible — réessayez dans quelques minutes.",
    }
    if kind == "current":
        base.update({"current": {}, "hourly": {}})
    elif kind == "forecast":
        base.update({"hourly": [], "daily": []})
    elif kind == "history":
        base.update({"hourly": []})
    elif kind == "zones":
        base.update({"zones": [], "storm_active": False, "max_cape": 0, "max_lightning_potential": 0})
    elif kind == "risk":
        base.update({"days": []})
    elif kind == "wind":
        base.update({"arrows": [], "max_speed": 0})
    elif kind == "severe":
        base.update({"hourly": [], "max_hail_score": 0, "max_hail_level": 0})
    elif kind == "severe-grid":
        # Match the bulk endpoint shape exactly so the frontend never trips
        # on a missing `per_param` / `times` key.
        base.update({
            "lats": [], "lons": [], "times": [], "per_param": {},
            "units": {}, "grid_cols": 0, "grid_rows": 0,
        })
    elif kind == "severe-profile":
        base.update({"levels": [], "temperatures": []})
    return base


@api_router.get("/weather/current")
async def weather_current(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    try:
        return await fetch_current(lat, lon)
    except Exception as e:
        return _degraded("current", e)


@api_router.get("/weather/forecast")
async def weather_forecast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    try:
        return await fetch_forecast(lat, lon)
    except Exception as e:
        return _degraded("forecast", e)


@api_router.get("/weather/history")
async def weather_history(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    try:
        return await fetch_history_24h(lat, lon)
    except Exception as e:
        return _degraded("history", e)


@api_router.get("/weather/history-days")
async def weather_history_days(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, days: int = 7):
    try:
        return await fetch_history_days(lat, lon, days)
    except Exception as e:
        return _degraded("history", e)


@api_router.get("/storms/zones")
async def storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM):
    try:
        return await fetch_storm_zones(lat, lon, radius_km)
    except Exception as e:
        return _degraded("zones", e)


@api_router.get("/weather/wind-grid")
async def weather_wind_grid(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM):
    try:
        return await fetch_wind_grid(lat, lon, radius_km)
    except Exception as e:
        return _degraded("wind", e)


@api_router.get("/airquality")
async def airquality(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    """Indice qualité de l'air (Xweather) — cache serveur 30 min."""
    import xweather
    if not xweather.is_configured():
        raise HTTPException(status_code=503, detail="Xweather non configuré")
    try:
        return await xweather.fetch_airquality(lat, lon)
    except Exception as e:
        logger.warning("airquality fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Erreur Xweather airquality")


@api_router.get("/weather/rain-nowcast")
async def weather_rain_nowcast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    """Pluie imminente (minutely_15 AROME) — 1 point, indicateur dashboard."""
    try:
        return await fetch_rain_nowcast(lat, lon)
    except Exception as e:
        logger.warning("rain-nowcast failed: %s", e)
        raise HTTPException(status_code=502, detail="Erreur prévision pluie imminente")


@api_router.get("/weather/severe")
async def weather_severe(
    lat: float = LOURDES_LAT,
    lon: float = LOURDES_LON,
    hours: int = 24,
    radius_km: float = RADIUS_KM,
):
    """48 h max severe-weather forecast incl. hail score + advanced atmospheric
    parameters. When `radius_km` is supplied, also computes the realtime hail
    score (Blitzortung lightning surge booster) and a 1-hour history."""
    hours = max(1, min(int(hours), 48))
    try:
        # 1. Theoretical forecast from Open-Meteo (cached)
        forecast = await severe_mod.fetch_severe(lat, lon, hours)
    except Exception as e:
        return _degraded("severe", e)

    # 2. Realtime overlay using Blitzortung lightning store
    realtime: Dict[str, Any] = {
        "lightning_available": False,
        "boost_pts": 0.0,
        "boost_raw_pts": 0.0,
        "density": None,
        "theoretical_h0": None,
        "realtime_h0": None,
        "is_surge": False,
    }
    try:
        hourly = forecast.get("hourly") or []
        if hourly:
            theoretical_h0 = float(hourly[0].get("hail_score") or 0.0)
            realtime["theoretical_h0"] = theoretical_h0

            # Adaptive radius for strike collection (cells move fast)
            eff_radius = severe_mod.effective_radius_km(radius_km)
            now_ts = time.time()
            since_ts = now_ts - severe_mod.WINDOW_PREV_S
            strikes = await lightning_mod.store.recent(lat, lon, eff_radius, since_ts=since_ts)

            density = severe_mod.compute_lightning_density(strikes, now_ts)
            boost_eff, boost_raw = severe_mod.compute_boost(density, theoretical_h0)
            rt_score = min(100.0, round(theoretical_h0 + boost_eff, 1))

            realtime.update({
                "lightning_available": True,
                "boost_pts": boost_eff,
                "boost_raw_pts": boost_raw,
                "density": density,
                "realtime_h0": rt_score,
                "is_surge": density.get("is_surge", False),
                "effective_radius_km": eff_radius,
            })

            # Persist the sample in the 1-hour history (best-effort)
            severe_mod.record_score_sample(
                lat, lon, radius_km,
                theoretical_h0, rt_score,
                density.get("is_surge", False),
                True,
                density.get("density_now", 0.0),
            )
    except Exception as e:
        logger.warning("severe realtime overlay failed: %s", e)
        # Still record a sample with lightning_available=False so the UI can show
        # the badge "Données électriques indisponibles".
        try:
            hourly = forecast.get("hourly") or []
            if hourly:
                theoretical_h0 = float(hourly[0].get("hail_score") or 0.0)
                severe_mod.record_score_sample(
                    lat, lon, radius_km,
                    theoretical_h0, theoretical_h0,
                    False, False, 0.0,
                )
        except Exception:
            pass

    forecast["realtime"] = realtime
    forecast["history_1h"] = severe_mod.get_score_history(lat, lon, radius_km)
    return forecast


@api_router.get("/weather/severe/grid")
async def weather_severe_grid(param: str = "t850", hour: int = 0):
    """Single-parameter forecast on a 16×12 grid covering France métropolitaine.
    Served from the local bulk store — NEVER calls Open-Meteo directly when the
    slider moves. See severe.py `_get_or_refresh_bulk()` for the architecture."""
    if param not in severe_mod.GRID_PARAM_MAP:
        raise HTTPException(status_code=400, detail=f"unknown param '{param}'")
    hour = max(0, min(int(hour), 47))
    try:
        return await severe_mod.fetch_severe_grid(param, hour)
    except Exception as e:
        return _degraded("severe-grid", e)


@api_router.get("/weather/severe/grid/status")
async def weather_severe_grid_status():
    """Diagnostic: state of the local bulk store (age, run timestamp, freshness)."""
    return await severe_mod.get_bulk_status()


@api_router.get("/weather/severe/grid/bulk")
async def weather_severe_grid_bulk():
    """Return the FULL bulk snapshot in ONE response (all params × all hours).
    The frontend fetches this once on mount and slices client-side. Eliminates
    the per-hour micro-request cascade that was 504-ing the Kimsufi Atom under
    rapid slider input.

    On cold start (no disk cache yet), this MUST do a synchronous fetch to
    Open-Meteo (up to ~60 s on a weak Atom). The client uses an extended
    timeout (90 s) for this single endpoint. If even that fails, we surface a
    proper 503 with a clear message so the user knows it's an upstream issue,
    not a code bug."""
    try:
        snap = await severe_mod.get_bulk_snapshot_for_frontend()
        # Validate the snapshot — never let a half-built payload through, the
        # frontend would just display "Snapshot bulk invalide".
        if not isinstance(snap, dict) or not snap.get("lats") or not snap.get("per_param"):
            raise HTTPException(
                status_code=503,
                detail="Bulk snapshot incomplete — upstream Open-Meteo "
                       "fetch failed and no stale cache available. Retry "
                       "in a moment.",
            )
        return snap
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Bulk endpoint failed: %s", e)
        # Friendly, short message — never dump huge upstream URLs into the
        # response body (would overflow the frontend banner).
        err_name = type(e).__name__
        msg = "Service météo amont temporairement indisponible."
        if "429" in str(e) or "Too Many Requests" in str(e):
            msg = "Rate-limit Open-Meteo atteint — réessaie dans 30-60 s."
        elif "Timeout" in err_name or "Timeout" in str(e):
            msg = "Délai dépassé vers Open-Meteo — réessaie."
        elif "ConnectError" in err_name or "Network" in err_name:
            msg = "Connexion à Open-Meteo impossible — vérifie le réseau du serveur."
        raise HTTPException(status_code=503, detail=msg)


@api_router.get("/weather/severe/profile")
async def weather_severe_profile(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, hour: int = 0):
    """Vertical temperature profile (surface + 1000/925/850/700/500/300 hPa)."""
    hour = max(0, min(int(hour), 47))
    try:
        return await severe_mod.fetch_temp_profile(lat, lon, hour)
    except Exception as e:
        return _degraded("severe-profile", e)


@api_router.get("/weather/vigilance")
async def weather_vigilance():
    """Vigilance météo calculée localement (Open-Meteo) pour Lourdes + départements voisins."""
    return await vigilance_mod.compute_vigilance()


@api_router.get("/weather/vigilance/full")
async def weather_vigilance_full():
    """Vigilance officielle MeteoAlarm pour toute la France + Andorre."""
    return await vigilance_mod.compute_full_france_vigilance()


@api_router.get("/share/card.png")
async def share_card_png():
    """Shareable PNG snapshot (1200x630) of current storm state around Lourdes."""
    png_bytes = await share_card_mod.render_share_card()
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=60"},
    )


# ---------- Lightning (Blitzortung) ----------
@api_router.get("/lightning/strikes")
async def lightning_strikes(
    lat: float = LOURDES_LAT,
    lon: float = LOURDES_LON,
    radius_km: float = RADIUS_KM,
    since: float | None = None,
):
    """Return recent lightning strikes within radius_km. `since` is epoch seconds."""
    strikes = await lightning_mod.store.recent(lat, lon, radius_km, since_ts=since)
    strikes.sort(key=lambda s: s["ts"], reverse=True)
    return {
        "count": len(strikes),
        "strikes": strikes[:500],
        "server_time": datetime.now(timezone.utc).timestamp(),
    }


@api_router.get("/lightning/status")
async def lightning_status():
    return lightning_mod.status()


@api_router.get("/replay/events")
async def replay_events(
    lat: float = LOURDES_LAT,
    lon: float = LOURDES_LON,
    radius_km: float = 70.0,
    min_strikes: int = 5,
    gap_min: int = 15,
):
    """Detect contiguous "storm bursts" in the last 24h strike buffer.

    Algorithm:
      - Fetch all strikes within radius.
      - Sort by ts ascending.
      - A burst = any group where consecutive strikes are <= `gap_min` minutes apart.
      - A burst is kept only if it contains >= `min_strikes` strikes and spans >= 5 min.
      - Each event exposes start/end timestamps, peak 10-min rate, and centroid.
    """
    strikes = await lightning_mod.store.recent(lat, lon, radius_km, since_ts=None)
    if not strikes:
        return {"events": [], "source_window_h": 24}

    strikes.sort(key=lambda s: s["ts"])
    gap_s = gap_min * 60.0

    # 1. Segment into bursts by time-gap
    bursts: list[list[dict]] = []
    current: list[dict] = []
    for s in strikes:
        if not current or (s["ts"] - current[-1]["ts"]) <= gap_s:
            current.append(s)
        else:
            if len(current) >= min_strikes:
                bursts.append(current)
            current = [s]
    if len(current) >= min_strikes:
        bursts.append(current)

    # 2. Qualify each burst
    events = []
    for b in bursts:
        start = b[0]["ts"]
        end = b[-1]["ts"]
        duration_s = max(end - start, 0.0)
        if duration_s < 300:  # < 5 min = not worth replaying
            continue
        # Peak 10-min rate (rolling window)
        peak = 0
        w = 10 * 60.0
        # Simple 2-pointer since sorted
        left = 0
        for right in range(len(b)):
            while b[right]["ts"] - b[left]["ts"] > w:
                left += 1
            peak = max(peak, right - left + 1)
        c_lat = sum(float(s["lat"]) for s in b) / len(b)
        c_lon = sum(float(s["lon"]) for s in b) / len(b)
        max_dist = max(float(s.get("distance_km") or 0) for s in b)
        events.append({
            "id": f"ev-{int(start)}",
            "start_ts": int(start),
            "end_ts": int(end),
            "duration_min": round(duration_s / 60.0, 1),
            "strike_count": len(b),
            "peak_count_10min": peak,
            "center_lat": round(c_lat, 4),
            "center_lon": round(c_lon, 4),
            "max_distance_km": round(max_dist, 1),
        })

    # 3. Sort by intensity (peak rate then strike_count) descending, then recency
    events.sort(key=lambda e: (-e["peak_count_10min"], -e["strike_count"], -e["start_ts"]))
    return {"events": events, "source_window_h": 24}


@api_router.get("/replay/demos")
async def replay_demos():
    """Return the list of reconstructed demo storms (Pyrenees type).

    These are synthetic events used to showcase the Replay + MP4 export
    features when no live thunderstorm is detected.
    """
    import time as _t
    now = _t.time()
    return {"demos": demo_mod.list_demo_events(now), "is_reconstructed": True}


class VideoExportInput(BaseModel):
    start_ts: float
    end_ts: float
    lat: float = LOURDES_LAT
    lon: float = LOURDES_LON
    radius_km: float = 70.0
    label: str = "Replay Storm Monitoring"
    demo_id: str | None = None


@api_router.post("/replay/video")
async def replay_video_start(body: VideoExportInput):
    """Kick off async MP4 generation for a replay episode.

    If `demo_id` is set, strikes come from the demo fixture. Otherwise we
    pull strikes from the live in-memory Blitzortung store.
    """
    import time as _t
    start_ts = body.start_ts
    end_ts = body.end_ts
    label = body.label
    if body.demo_id:
        strikes = demo_mod.get_demo_strikes(body.demo_id, _t.time()) or []
        if not strikes:
            raise HTTPException(status_code=404, detail="Demo not found")
        # Demos carry their own time window + label — body values are ignored.
        start_ts = strikes[0]["ts"]
        end_ts = strikes[-1]["ts"]
        for d in demo_mod.DEMOS:
            if d["id"] == body.demo_id:
                label = d["label"]
                break
    else:
        strikes = await lightning_mod.store.recent(
            body.lat, body.lon, body.radius_km * 1.2,
            since_ts=body.start_ts, until_ts=body.end_ts,
        )
    if len(strikes) < 3:
        raise HTTPException(status_code=400, detail="Not enough strikes to render a replay")

    # Opportunistic purge of old artifacts
    video_mod.purge_old(max_age_h=24)

    job_id = await video_mod.start_job(
        strikes=strikes,
        start_ts=start_ts,
        end_ts=end_ts,
        center_lat=body.lat,
        center_lon=body.lon,
        radius_km=body.radius_km,
        label=label,
    )
    return {"job_id": job_id, "status": "queued"}


@api_router.get("/replay/video/{job_id}")
async def replay_video_status(job_id: str):
    j = video_mod.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j


@api_router.get("/replay/video/{job_id}/file.mp4")
async def replay_video_file(job_id: str):
    from fastapi.responses import FileResponse
    j = video_mod.get_job(job_id)
    if not j or j.get("status") != "done":
        raise HTTPException(status_code=404, detail="Video not ready")
    path = j.get("mp4_path")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=410, detail="Video expired")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"storm-replay-{job_id}.mp4",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@api_router.get("/storms/approach")
async def storms_approach(
    lat: float = LOURDES_LAT,
    lon: float = LOURDES_LON,
    radius_km: float = 100.0,
    at_ts: float | None = None,
):
    """Analyze approach of lightning strikes toward the center.

    When `at_ts` is provided, analysis is anchored at that timestamp (timeline scrub).
    """
    strikes = await lightning_mod.store.recent(
        lat, lon, radius_km, since_ts=None, until_ts=at_ts
    )
    result = analysis_mod.analyze_approach(lat, lon, strikes, now=at_ts)
    result["radius_analyzed_km"] = radius_km
    return result


@api_router.get("/storms/trajectory")
async def storms_trajectory(
    lat: float = LOURDES_LAT,
    lon: float = LOURDES_LON,
    radius_km: float = 150.0,
    project_minutes: int = 45,
    at_ts: float | None = None,
):
    """Predict the storm centroid trajectory via linear regression on recent strikes.

    When `at_ts` is provided, the analysis is anchored on that timestamp:
    only strikes with ts <= at_ts are used, and projection starts from at_ts.
    This lets the timeline scrub back in time and see past trajectories.
    """
    strikes = await lightning_mod.store.recent(
        lat, lon, radius_km, since_ts=None, until_ts=at_ts
    )
    return analysis_mod.predict_trajectory(
        lat, lon, strikes, now=at_ts, project_minutes=project_minutes
    )


@api_router.get("/forecast/storm-risk")
async def forecast_storm_risk(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, days: int = 7):
    """Daily storm risk forecast for the next N days."""
    try:
        return await fetch_storm_risk_forecast(lat, lon, days)
    except Exception as e:
        return _degraded("risk", e)


# ---------- Storm upload (secured with API key header) ----------
class StormUploadInput(BaseModel):
    distance: float = Field(..., description="Distance in km")
    energy: float = Field(..., description="Energy (kA, kJ or arbitrary)")
    timestamp: Optional[str] = None
    kind: Optional[str] = Field(default="lightning", description="lightning | disturber | heartbeat | tune_freq")
    device_id: Optional[str] = None
    raw_freq_hz: Optional[float] = Field(default=None, description="Antenna frequency (Hz) for kind=tune_freq")
    tune_cap: Optional[int] = Field(default=None, description="Current tuneCap value (0-15) for kind=tune_freq")


def _require_upload_api_key(request: Request) -> None:
    expected = os.environ.get("UPLOAD_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="UPLOAD_API_KEY not configured on server")
    received = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if not received or received != expected:
        raise HTTPException(status_code=401, detail="Clé API invalide ou manquante")


@api_router.post("/upload_storm")
async def upload_storm(payload: StormUploadInput, request: Request):
    """Upload a storm data point. Requires header 'X-API-Key'."""
    _require_upload_api_key(request)
    record = await uploads_mod.append(
        payload.distance,
        payload.energy,
        payload.timestamp,
        kind=payload.kind or "lightning",
        device_id=payload.device_id,
        raw_freq_hz=payload.raw_freq_hz,
        tune_cap=payload.tune_cap,
    )
    return {"ok": True, "record": record}


@api_router.get("/detector/tune")
async def detector_tune_status(device_id: Optional[str] = None, window_min: int = 60):
    """
    Return the latest tune_freq samples + a suggested optimal tuneCap value.

    Adaptive: if we observe samples at multiple tuneCap values, we compute the
    actual Hz/step sensitivity of THIS specific board via linear regression.
    Otherwise we fall back to the rough ~1400 Hz/step from the datasheet.
    """
    TARGET_HZ = 500_000.0
    DEFAULT_HZ_PER_STEP = 1400.0  # fallback when only 1 distinct tune_cap observed
    items = await uploads_mod.list_all(None)
    if device_id:
        items = [it for it in items if it.get("device_id") == device_id]
    tune = [it for it in items if it.get("kind") == "tune_freq" and it.get("raw_freq_hz")]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_min)
    recent = []
    for it in tune:
        try:
            t = datetime.fromisoformat((it.get("timestamp") or "").replace("Z", "+00:00"))
            if t >= cutoff:
                recent.append(it)
        except (ValueError, AttributeError, TypeError):
            continue

    if not recent:
        return {
            "online": False,
            "samples": [],
            "current": None,
            "suggestion": None,
            "calibration": {"adaptive": False, "hz_per_step": DEFAULT_HZ_PER_STEP, "points": 0, "r_squared": None},
            "window_minutes": window_min,
        }

    # ---- Adaptive calibration ----
    # Group recent samples by tune_cap, take median frequency per group
    by_cap: dict = {}
    for s in recent:
        cap = int(s.get("tune_cap") or 0)
        by_cap.setdefault(cap, []).append(float(s["raw_freq_hz"]))
    points = []  # list of (cap, median_freq)
    for cap, freqs in by_cap.items():
        freqs.sort()
        median = freqs[len(freqs) // 2]
        points.append((cap, median))
    points.sort(key=lambda p: p[0])

    adaptive = False
    hz_per_step = DEFAULT_HZ_PER_STEP
    r_squared = None
    if len(points) >= 2:
        # Linear regression: freq = a + b * cap, we want b (negative usually)
        n = len(points)
        sx = sum(p[0] for p in points)
        sy = sum(p[1] for p in points)
        sxx = sum(p[0] ** 2 for p in points)
        sxy = sum(p[0] * p[1] for p in points)
        denom = n * sxx - sx * sx
        if denom != 0:
            slope = (n * sxy - sx * sy) / denom  # Hz per step (typically negative)
            intercept = (sy - slope * sx) / n
            # Compute R²
            mean_y = sy / n
            ss_tot = sum((p[1] - mean_y) ** 2 for p in points)
            ss_res = sum((p[1] - (intercept + slope * p[0])) ** 2 for p in points)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            # Use |slope| as Hz/step; keep sign convention "positive = how much added cap reduces freq"
            if abs(slope) > 100:  # sanity check: slope must be plausible
                hz_per_step = abs(slope)
                adaptive = True

    # ---- Current state + suggestion ----
    latest = recent[0]
    f = float(latest["raw_freq_hz"])
    cur_cap = int(latest.get("tune_cap") or 0)
    delta_hz = f - TARGET_HZ
    delta_pct = (delta_hz / TARGET_HZ) * 100.0
    needed_steps = round(delta_hz / hz_per_step)
    suggested_cap = max(0, min(15, cur_cap + needed_steps))
    expected_delta = delta_hz - (suggested_cap - cur_cap) * hz_per_step

    note = (
        f"Calibré sur ce capteur ({len(points)} points, R²={r_squared:.3f})."
        if adaptive
        else "Approximation linéaire par défaut (~1400 Hz/pas). Reflashe avec plusieurs valeurs de tuneCap pour calibrer."
    )

    return {
        "online": True,
        "samples": [
            {
                "timestamp": s.get("timestamp"),
                "freq_hz": float(s.get("raw_freq_hz", 0)),
                "tune_cap": int(s.get("tune_cap") or 0),
            }
            for s in recent[:50]
        ],
        "current": {
            "freq_hz": f,
            "delta_hz": delta_hz,
            "delta_pct": delta_pct,
            "in_spec": abs(delta_pct) <= 3.5,
            "tune_cap": cur_cap,
            "timestamp": latest.get("timestamp"),
        },
        "suggestion": {
            "tune_cap": suggested_cap,
            "expected_delta_hz_after": expected_delta,
            "note": note,
        },
        "calibration": {
            "adaptive": adaptive,
            "hz_per_step": hz_per_step,
            "points": [{"tune_cap": c, "median_freq_hz": float(f_)} for c, f_ in points],
            "r_squared": r_squared,
        },
        "window_minutes": window_min,
    }


@api_router.get("/detector/status")
async def detector_status(device_id: Optional[str] = None, online_window_min: int = 10):
    """Return liveness + latest events for the AS3935 hardware detector page."""
    items = await uploads_mod.list_all(None)
    if device_id:
        items = [it for it in items if it.get("device_id") == device_id]
    # items are already sorted desc by timestamp
    now = datetime.now(timezone.utc)
    last = items[0] if items else None
    online = False
    last_seen_ts = None
    if last:
        try:
            ts = last.get("received_at") or last.get("timestamp")
            last_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            last_seen_ts = last_dt.isoformat()
            online = (now - last_dt).total_seconds() <= online_window_min * 60
        except (ValueError, AttributeError, TypeError):
            online = False

    # 24h slice for charts/feed
    cutoff = now - timedelta(hours=24)
    last_24h = []
    for it in items:
        try:
            t = datetime.fromisoformat((it.get("timestamp") or "").replace("Z", "+00:00"))
            if t >= cutoff:
                last_24h.append(it)
        except (ValueError, AttributeError, TypeError):
            continue

    lightnings = [it for it in last_24h if (it.get("kind") or "lightning") == "lightning"]
    disturbers = [it for it in last_24h if it.get("kind") == "disturber"]

    closest_km = min((it["distance"] for it in lightnings), default=None)
    max_energy = max((it["energy"] for it in lightnings), default=None)

    return {
        "online": online,
        "last_seen": last_seen_ts,
        "window_minutes": online_window_min,
        "stats_24h": {
            "lightnings": len(lightnings),
            "disturbers": len(disturbers),
            "closest_km": closest_km,
            "max_energy": max_energy,
        },
        "recent": last_24h[:50],
    }


@api_router.get("/storm_uploads")
async def list_storm_uploads(limit: Optional[int] = None):
    """Public: list all uploaded storm records from storm_data.json."""
    items = await uploads_mod.list_all(limit)
    return {"count": len(items), "items": items}


# ---------- Web Push (VAPID) ----------
class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


@api_router.get("/push/status")
async def push_status():
    """Diagnostic public : état FCM serveur + nombre d'appareils enregistrés."""
    return {
        "fcm_available": fcm_mod.available(),
        "fcm": fcm_mod.diagnose(),
        "fcm_tokens": await db.fcm_tokens.count_documents({}),
        "webpush_subscriptions": await db.push_subscriptions.count_documents({}),
    }


@api_router.get("/push/vapid-public-key")
async def push_vapid_public_key():
    return {"key": push_mod.vapid_public_key()}


@api_router.post("/push/subscribe")
async def push_subscribe(
    subscription: PushSubscription,
    user=Depends(get_current_user_optional),
):
    saved = await push_mod.save_subscription(
        db,
        subscription.model_dump(),
        user_id=user["id"] if user else None,
    )
    return {"ok": True, "id": saved["id"]}


@api_router.post("/push/unsubscribe")
async def push_unsubscribe(payload: dict = Body(...)):
    endpoint = payload.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint required")
    n = await push_mod.remove_subscription(db, endpoint)
    return {"removed": n}


@api_router.post("/push/fcm/subscribe")
async def push_fcm_subscribe(
    payload: dict = Body(...),
    user=Depends(get_current_user_optional),
):
    token = payload.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    await fcm_mod.save_token(db, token, user_id=user["id"] if user else None)
    return {"ok": True, "fcm_available": fcm_mod.available()}


@api_router.post("/push/fcm/unsubscribe")
async def push_fcm_unsubscribe(payload: dict = Body(...)):
    token = payload.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    n = await fcm_mod.remove_token(db, token)
    return {"removed": n}


@api_router.post("/push/test")
async def push_test(user=Depends(get_current_user)):
    """Unicast : cible uniquement les appareils de l'utilisateur connecté."""
    result = await push_mod.send_to_user(
        db,
        user["id"],
        title="Test · Alerte orage",
        body="Ceci est un test de notification push — tout fonctionne.",
        url="/",
    )
    return result


# ---------- Webhooks (Discord + Telegram) ----------
@api_router.get("/webhooks/status")
async def webhooks_status():
    """Return which channels are configured. No secret is leaked."""
    return webhooks_mod.status()


@api_router.post("/webhooks/test")
async def webhooks_test(user=Depends(get_current_user)):
    """Send a test message on all configured channels (bypasses cooldown)."""
    res = await webhooks_mod.dispatch(
        title="Test webhook · Storm Monitoring",
        body=(
            "Ceci est un test de notification — tout fonctionne.\n"
            "Les canaux recevront désormais les alertes orages, impacts et vigilance."
        ),
        tag="test",
        force=True,
    )
    return res


# ---------- PDF bulletin ----------
@api_router.get("/reports/bulletin.pdf")
async def bulletin_pdf(
    lat: float = LOURDES_LAT,
    lon: float = LOURDES_LON,
    radius_km: float = RADIUS_KM,
    name: str = "Lourdes",
    z: List[str] = Query(default_factory=list),
):
    """
    Generate a storm bulletin PDF.

    Two modes:
    - Single zone (legacy): pass lat, lon, name, radius_km.
    - Multi-zone: pass one or more z=name|lat|lon|radius query params.
      The 'z' parameters take precedence if present.
    """
    # ----- Parse zone descriptors -----
    descriptors: List[Dict[str, Any]] = []
    if z:
        for entry in z:
            try:
                parts = entry.split("|")
                if len(parts) != 4:
                    continue
                nm, la, lo, rd = parts
                nm = nm.strip() or "—"
                la_f, lo_f, rd_f = float(la), float(lo), float(rd)
                if not (-90 <= la_f <= 90 and -180 <= lo_f <= 180 and 1 <= rd_f <= 500):
                    continue
                descriptors.append({"name": nm, "lat": la_f, "lon": lo_f, "radius_km": rd_f})
            except Exception:
                continue
    if not descriptors:
        descriptors = [{"name": name, "lat": lat, "lon": lon, "radius_km": radius_km}]

    # ----- Fetch all zones in parallel -----
    async def _fetch_zone(d: Dict[str, Any]) -> Dict[str, Any]:
        async def _safe_severe():
            try:
                return await severe_mod.fetch_severe(d["lat"], d["lon"], 24)
            except Exception:
                return {}
        c, f, h, zres, sv = await asyncio.gather(
            fetch_current(d["lat"], d["lon"]),
            fetch_forecast(d["lat"], d["lon"]),
            fetch_history_24h(d["lat"], d["lon"]),
            fetch_storm_zones(d["lat"], d["lon"], d["radius_km"]),
            _safe_severe(),
        )
        strikes_data = await lightning_mod.store.recent(d["lat"], d["lon"], d["radius_km"], since_ts=None)
        strikes_data.sort(key=lambda s: s["ts"], reverse=True)
        return {
            **d,
            "current": c,
            "zones": zres,
            "history": h,
            "forecast": f,
            "strikes": strikes_data[:50],
            "severe": sv,
        }

    payload = await asyncio.gather(*[_fetch_zone(d) for d in descriptors])
    tz_name = (payload[0].get("current") or {}).get("timezone")

    pdf = reports_mod.build_bulletin_pdf(payload, tz_name=tz_name)

    # ----- Slugified filename -----
    def _slug(v: str) -> str:
        out = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in (v or "").lower()).strip("-")
        return out or "zone"

    if len(payload) == 1:
        slug = _slug(payload[0]["name"])
    else:
        head = "-".join(_slug(p["name"])[:12] for p in payload[:3])
        slug = f"multi-{head}" + (f"-plus{len(payload) - 3}" if len(payload) > 3 else "")
    filename = f"bulletin-orage-{slug}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.pdf"

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def _start_lightning_listener():
    try:
        lightning_mod.start()
        logger.info("Lightning listener started")
    except Exception as e:
        logger.warning("Could not start lightning listener: %s", e)

    # Force FCM SDK init at boot so `journalctl | grep FCM` reports availability.
    try:
        if fcm_mod.available():
            logger.info("FCM prêt · notifications Android natives activées")
        else:
            logger.info("FCM indisponible · credentials manquants ou invalides")
    except Exception as e:
        logger.warning("FCM init au démarrage a échoué : %s", e)

    # Alert watcher: push notifications on storm transitions + new strikes in radius
    asyncio.create_task(_alert_watcher())
    logger.info("Alert watcher started")

    # Rafraîchisseur autonome du cache local Prévisions/carte France (24h/24,
    # profite du créneau nocturne où le quota Open-Meteo est disponible)
    asyncio.create_task(severe_mod.bulk_refresher_loop())
    logger.info("Bulk refresher started")


# Shared state for alerter
_alerter_state = {
    "storm_active": False,
    "last_strike_ts": 0.0,
    "approach_active": False,
    "vigilance_level": 1,  # 1=vert, 2=jaune, 3=orange, 4=rouge
    "vigilance_last_check": 0.0,
}


async def _alert_watcher():
    """Every 45s, check storm status + recent strikes inside 20km and fire push notifications on transitions.

    Détection orage 100 % Blitzortung (0 appel Open-Meteo) : un orage est
    considéré actif si ≥ 2 impacts réels dans le rayon sur les 15 dernières minutes."""
    while True:
        try:
            await asyncio.sleep(45)
            recent_strikes = await lightning_mod.store.recent(
                LOURDES_LAT, LOURDES_LON, RADIUS_KM, since_ts=time.time() - 15 * 60
            )
            storm_now = len(recent_strikes) >= 2
            was_storm = _alerter_state["storm_active"]
            if storm_now and not was_storm:
                closest_km = min(s["distance_km"] for s in recent_strikes)
                body = f"{len(recent_strikes)} impacts de foudre détectés dans le rayon (le plus proche à {closest_km:.1f} km)."
                await push_mod.send_to_all(
                    db,
                    title="Alerte orage · Lourdes",
                    body=body,
                    url="/",
                    tag="storm-active",
                )
                await webhooks_mod.dispatch(
                    title="Alerte orage · Lourdes",
                    body=body,
                    tag="storm-active",
                )
            _alerter_state["storm_active"] = storm_now

            # Fresh strikes in radius
            strikes = await lightning_mod.store.recent(LOURDES_LAT, LOURDES_LON, RADIUS_KM, since_ts=_alerter_state["last_strike_ts"] or None)
            new_strikes = [s for s in strikes if s["ts"] > _alerter_state["last_strike_ts"]]
            if new_strikes:
                closest = min(new_strikes, key=lambda s: s["distance_km"])
                await push_mod.send_to_all(
                    db,
                    title=f"⚡ {len(new_strikes)} impact(s) de foudre",
                    body=f"Le plus proche à {closest['distance_km']:.1f} km de Lourdes.",
                    url="/",
                    tag="lightning-strike",
                )
                await webhooks_mod.dispatch(
                    title=f"{len(new_strikes)} impact(s) de foudre",
                    body=f"Le plus proche à {closest['distance_km']:.1f} km de Lourdes.",
                    tag="lightning-strike",
                )
                _alerter_state["last_strike_ts"] = max(s["ts"] for s in new_strikes)

            # Storm approach detection (wider 100km radius)
            approach_strikes = await lightning_mod.store.recent(LOURDES_LAT, LOURDES_LON, 100.0, since_ts=None)
            approach = analysis_mod.analyze_approach(LOURDES_LAT, LOURDES_LON, approach_strikes)
            if approach.get("approaching") and not _alerter_state["approach_active"]:
                eta = approach.get("eta_min")
                speed = approach.get("speed_kmh")
                body = (
                    f"Distance {approach.get('min_distance_km')} km · vitesse {speed} km/h · "
                    f"arrivée estimée {int(eta)} min · direction {approach.get('from_compass')}"
                )
                await push_mod.send_to_all(
                    db,
                    title="⚠ Orage en approche de Lourdes",
                    body=body,
                    url="/",
                    tag="storm-approach",
                )
                await webhooks_mod.dispatch(
                    title="Orage en approche de Lourdes",
                    body=body,
                    tag="storm-approach",
                )
            _alerter_state["approach_active"] = bool(approach.get("approaching"))

            # Vigilance escalation check (every 20 min — vigilance data TTL is 15 min)
            import time as _t
            if _t.time() - _alerter_state["vigilance_last_check"] > 20 * 60:
                _alerter_state["vigilance_last_check"] = _t.time()
                try:
                    vig = await vigilance_mod.compute_vigilance()
                    # Overall level for Lourdes (65) primarily
                    lourdes = next((d for d in vig["departements"] if d["id"] == "65"), None)
                    current_level = lourdes["max_level"] if lourdes else vig["overall_level"]
                    prev_level = _alerter_state["vigilance_level"]
                    # Notify only on escalation to orange (3) or rouge (4)
                    if current_level >= 3 and current_level > prev_level:
                        level_fr = {3: "orange", 4: "rouge"}[current_level]
                        # Find which phenomena triggered
                        worst_phen = [
                            p for p in lourdes["phenomena"]
                            if p["level"] == current_level
                        ] if lourdes else []
                        names = ", ".join(p["label"] for p in worst_phen[:3])
                        await push_mod.send_to_all(
                            db,
                            title=f"⚠ Vigilance {level_fr.upper()} · Lourdes",
                            body=f"{names} · passage en niveau {level_fr}. Soyez vigilant.",
                            url="/",
                            tag=f"vigilance-{level_fr}",
                        )
                        await webhooks_mod.dispatch(
                            title=f"Vigilance {level_fr.upper()} · Lourdes (Hautes-Pyrénées)",
                            body=f"{names} · passage en niveau {level_fr}. Soyez vigilant.",
                            tag=f"vigilance-{level_fr}",
                        )
                    _alerter_state["vigilance_level"] = current_level
                except Exception as e:
                    logger.warning("Vigilance check error: %s", e)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("Alert watcher error: %s", e)


@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        lightning_mod.stop()
    except Exception:
        pass
    client.close()

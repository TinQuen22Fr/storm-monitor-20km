"""FastAPI server for Lourdes thunderstorm tracker."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException
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
    fetch_storm_zones,
)
import lightning as lightning_mod
import push as push_mod
import reports as reports_mod
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


# ---------- Auth ----------
@api_router.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterInput):
    existing = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": payload.email.lower(),
        "name": payload.name or payload.email.split("@")[0],
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_token(user_id, payload.email.lower())
    return AuthResponse(token=token, user={"id": user_id, "email": doc["email"], "name": doc["name"]})


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginInput):
    doc = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if not doc or not verify_password(payload.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_token(doc["id"], doc["email"])
    return AuthResponse(token=token, user={"id": doc["id"], "email": doc["email"], "name": doc.get("name", "")})


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return doc


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
@api_router.get("/weather/current")
async def weather_current(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    return await fetch_current(lat, lon)


@api_router.get("/weather/forecast")
async def weather_forecast(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    return await fetch_forecast(lat, lon)


@api_router.get("/weather/history")
async def weather_history(lat: float = LOURDES_LAT, lon: float = LOURDES_LON):
    return await fetch_history_24h(lat, lon)


@api_router.get("/weather/history-days")
async def weather_history_days(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, days: int = 7):
    return await fetch_history_days(lat, lon, days)


@api_router.get("/storms/zones")
async def storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM):
    return await fetch_storm_zones(lat, lon, radius_km)


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


# ---------- Web Push (VAPID) ----------
class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


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


@api_router.post("/push/test")
async def push_test(user=Depends(get_current_user)):
    result = await push_mod.send_to_all(
        db,
        title="Test · Alerte orage",
        body="Ceci est un test de notification push — tout fonctionne.",
        url="/",
    )
    return result


# ---------- PDF bulletin ----------
@api_router.get("/reports/bulletin.pdf")
async def bulletin_pdf(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM):
    current, forecast, history, zones = await asyncio.gather(
        fetch_current(lat, lon),
        fetch_forecast(lat, lon),
        fetch_history_24h(lat, lon),
        fetch_storm_zones(lat, lon, radius_km),
    )
    strikes_data = await lightning_mod.store.recent(lat, lon, radius_km, since_ts=None)
    strikes_data.sort(key=lambda s: s["ts"], reverse=True)
    pdf = reports_mod.build_bulletin_pdf(current, zones, history, forecast, strikes_data[:50])
    filename = f"bulletin-orage-lourdes-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.pdf"
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

    # Alert watcher: push notifications on storm transitions + new strikes in radius
    asyncio.create_task(_alert_watcher())
    logger.info("Alert watcher started")


# Shared state for alerter
_alerter_state = {
    "storm_active": False,
    "last_strike_ts": 0.0,
}


async def _alert_watcher():
    """Every 45s, check storm status + recent strikes inside 20km and fire push notifications on transitions."""
    while True:
        try:
            await asyncio.sleep(45)
            zones = await fetch_storm_zones(LOURDES_LAT, LOURDES_LON, RADIUS_KM)
            storm_now = bool(zones.get("storm_active"))
            was_storm = _alerter_state["storm_active"]
            if storm_now and not was_storm:
                await push_mod.send_to_all(
                    db,
                    title="Alerte orage · Lourdes",
                    body=f"Activité orageuse détectée (CAPE {int(zones.get('max_cape') or 0)} J/kg).",
                    url="/",
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
                _alerter_state["last_strike_ts"] = max(s["ts"] for s in new_strikes)
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

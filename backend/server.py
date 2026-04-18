"""FastAPI server for Lourdes thunderstorm tracker."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from auth import (
    create_token,
    get_current_user,
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
    fetch_storm_zones,
)

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


@api_router.get("/storms/zones")
async def storm_zones(lat: float = LOURDES_LAT, lon: float = LOURDES_LON, radius_km: float = RADIUS_KM):
    return await fetch_storm_zones(lat, lon, radius_km)


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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

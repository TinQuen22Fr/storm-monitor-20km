"""Blitzortung.org realtime lightning WebSocket listener.

Connects to the public Blitzortung WebSocket, decodes the custom LZW-like
compressed messages, filters strikes within a given radius of Lourdes,
and stores them in an in-memory ring buffer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import ssl
import time
from collections import deque
from typing import Deque, Dict, List, Optional

import websockets

logger = logging.getLogger(__name__)

# Servers
BO_SERVERS = [f"wss://ws{i}.blitzortung.org/" for i in range(1, 9)]

# Lourdes + collection radius (wider than display radius so we see storms approaching)
LOURDES_LAT = 43.0951
LOURDES_LON = -0.0434
COLLECT_RADIUS_KM = 300.0  # Sud-Ouest élargi : couvre Toulouse, Bordeaux, Perpignan, Catalogne

MAX_STRIKES = 20000  # Keep last N strikes in memory
STRIKE_TTL_S = 24 * 3600  # Prune strikes older than 24h
PERSIST_TTL_DAYS = 30  # Rétention MongoDB (purge auto via index TTL)
FLUSH_INTERVAL_S = 10  # Écriture Mongo groupée (batch) — ménage le SSD


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bo_decode(b: str) -> str:
    """Port of Blitzortung's JS LZW-variant decoder.

    Standard LZW where codepoints < 256 are literals and codepoints >= 256
    are dictionary entries starting at 256. Works on unicode characters
    emitted by the Blitzortung server.
    """
    if not b:
        return ""
    e: Dict[int, str] = {}
    d = list(b)
    c = d[0]
    f = c
    g: List[str] = [c]
    h = 256
    for i in range(1, len(d)):
        code = ord(d[i])
        if code < 256:
            cur = d[i]
        elif code in e:
            cur = e[code]
        else:
            cur = f + c
        g.append(cur)
        c = cur[0]
        e[h] = f + c
        h += 1
        f = cur
    return "".join(g)


class StrikeStore:
    def __init__(self) -> None:
        self._buf: Deque[Dict] = deque(maxlen=MAX_STRIKES)
        self._lock = asyncio.Lock()

    async def add(self, strike: Dict, persist: bool = True) -> None:
        async with self._lock:
            self._buf.append(strike)
        if persist and not strike.get("simulated"):
            _pending.append(strike)

    async def recent(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        since_ts: Optional[float] = None,
        until_ts: Optional[float] = None,
    ) -> List[Dict]:
        """Return strikes within radius_km of (lat,lon).

        since_ts / until_ts are epoch-seconds bounds (inclusive lower, exclusive upper
        for until_ts). Used to anchor trajectory/approach analysis on a past cursor.
        """
        now = time.time()
        cutoff = since_ts if since_ts is not None else now - STRIKE_TTL_S
        async with self._lock:
            items = list(self._buf)
        out: List[Dict] = []
        for s in items:
            if s["ts"] < cutoff:
                continue
            if until_ts is not None and s["ts"] > until_ts:
                continue
            d = _haversine_km(lat, lon, s["lat"], s["lon"])
            if d <= radius_km:
                out.append({**s, "distance_km": round(d, 2)})
        return out


store = StrikeStore()

# ---------- Persistance MongoDB (batch + TTL 30 jours) ----------
_col = None
_pending: List[Dict] = []
_flush_task: Optional[asyncio.Task] = None


async def init_db(db) -> None:
    """Active la persistance Mongo : index TTL, rechargement 24 h, flusher batch."""
    global _col, _flush_task
    _col = db["strikes"]
    await _col.create_index("dt", expireAfterSeconds=PERSIST_TTL_DAYS * 24 * 3600)
    await _col.create_index("ts")
    cutoff = time.time() - STRIKE_TTL_S
    n = 0
    cursor = _col.find({"ts": {"$gte": cutoff}}, {"_id": 0, "dt": 0}).sort("ts", 1).limit(MAX_STRIKES)
    async for doc in cursor:
        await store.add(doc, persist=False)
        n += 1
    logger.info("Lightning: %d strikes des dernières 24h rechargés depuis MongoDB", n)
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.get_event_loop().create_task(_flush_loop())


async def _flush_loop() -> None:
    """Écrit les impacts en attente par paquets (1 write/10 s au lieu de 1/impact)."""
    from datetime import datetime as _dt, timezone as _tz
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_S)
        if not _pending or _col is None:
            continue
        batch = _pending[:]
        del _pending[: len(batch)]
        docs = [{**s, "dt": _dt.fromtimestamp(s["ts"], tz=_tz.utc)} for s in batch]
        try:
            await _col.insert_many(docs, ordered=False)
        except Exception as e:
            logger.warning("Lightning: flush Mongo échoué (%s) — %d strikes ré-empilés", e, len(batch))
            _pending.extend(batch)


async def strikes_between(
    lat: float, lon: float, radius_km: float,
    since_ts: float, until_ts: Optional[float] = None,
) -> List[Dict]:
    """Impacts persistés (MongoDB, jusqu'à 30 j) dans un rayon — historique multi-jours."""
    if _col is None:
        return []
    q: Dict = {"ts": {"$gte": since_ts}}
    if until_ts is not None:
        q["ts"]["$lte"] = until_ts
    out: List[Dict] = []
    async for doc in _col.find(q, {"_id": 0, "lat": 1, "lon": 1, "ts": 1}):
        if _haversine_km(lat, lon, doc["lat"], doc["lon"]) <= radius_km:
            out.append(doc)
    return out


# Debug counters
_total_received = 0
_total_in_region = 0
_last_msg_ts: Optional[float] = None
_decode_errors = 0
_sample_raw: Optional[str] = None


def _parse_strike(payload: Dict) -> Optional[Dict]:
    """Convert Blitzortung payload to internal format. Returns None if invalid."""
    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
        # `time` is nanoseconds since epoch
        t_ns = payload.get("time") or payload.get("t") or 0
        ts = float(t_ns) / 1e9 if t_ns else time.time()
        return {
            "lat": lat,
            "lon": lon,
            "ts": ts,
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
            "region": payload.get("region"),
            "status": payload.get("status"),
        }
    except (TypeError, ValueError):
        return None


async def _listen_forever(simulated_only: bool = False) -> None:
    """Main listener loop with reconnect & fallback to simulated strikes if WS unreachable."""
    if simulated_only:
        await _simulate_strikes_loop()
        return

    backoff = 2.0
    servers = list(BO_SERVERS)
    random.shuffle(servers)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    while True:
        for url in servers:
            try:
                logger.info("Blitzortung: connecting to %s", url)
                async with websockets.connect(
                    url,
                    origin="https://map.blitzortung.org",
                    open_timeout=15,
                    ping_interval=20,
                    ping_timeout=20,
                    ssl=ssl_ctx,
                ) as ws:
                    await ws.send(json.dumps({"a": 111}))
                    backoff = 2.0
                    global _total_received, _total_in_region, _last_msg_ts, _decode_errors, _sample_raw
                    async for msg in ws:
                        _last_msg_ts = time.time()
                        if isinstance(msg, bytes):
                            try:
                                msg = msg.decode("utf-8", errors="ignore")
                            except Exception:
                                continue
                        if _sample_raw is None:
                            _sample_raw = msg[:500]
                        try:
                            decoded = _bo_decode(msg)
                            data = json.loads(decoded)
                        except Exception as exc:
                            _decode_errors += 1
                            if _decode_errors <= 3:
                                logger.warning("Blitzortung decode error (%s): raw head=%r", exc, msg[:80])
                            continue
                        _total_received += 1
                        strike = _parse_strike(data)
                        if not strike:
                            continue
                        # Filter to collection region
                        d = _haversine_km(LOURDES_LAT, LOURDES_LON, strike["lat"], strike["lon"])
                        if d <= COLLECT_RADIUS_KM:
                            _total_in_region += 1
                            await store.add(strike)
            except Exception as e:
                logger.warning("Blitzortung WS error on %s: %s", url, e)
                await asyncio.sleep(min(backoff, 60))
                backoff = min(backoff * 1.7, 60)


async def _simulate_strikes_loop() -> None:
    """Dev-only fallback: occasionally inject a simulated strike near Lourdes."""
    while True:
        await asyncio.sleep(60)
        if random.random() < 0.15:
            lat = LOURDES_LAT + (random.random() - 0.5) * 0.3
            lon = LOURDES_LON + (random.random() - 0.5) * 0.3
            await store.add({
                "lat": lat,
                "lon": lon,
                "ts": time.time(),
                "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "region": 2,
                "status": 0,
                "simulated": True,
            })


_task: Optional[asyncio.Task] = None


def start(simulated_only: bool = False) -> None:
    global _task
    if _task and not _task.done():
        return
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_listen_forever(simulated_only=simulated_only))


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None


def status() -> Dict:
    return {
        "running": _task is not None and not _task.done(),
        "strikes_received": _total_received,
        "strikes_in_region": _total_in_region,
        "last_message_at": _last_msg_ts,
        "decode_errors": _decode_errors,
        "collect_radius_km": COLLECT_RADIUS_KM,
    }

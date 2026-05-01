"""Tests for the /api/replay/events burst-detection endpoint."""
from __future__ import annotations

import asyncio
import os
import sys
import time

import requests
from httpx import ASGITransport, AsyncClient

# Make backend importable
sys.path.insert(0, "/app/backend")


def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)


_load_frontend_env()
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


# ---------------- Public endpoint smoke tests ----------------
class TestReplayEventsPublic:
    def test_endpoint_returns_200_and_shape(self):
        r = requests.get(f"{BASE_URL}/api/replay/events", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "source_window_h" in data
        assert data["source_window_h"] == 24
        assert isinstance(data["events"], list)

    def test_accepts_query_params(self):
        r = requests.get(
            f"{BASE_URL}/api/replay/events",
            params={"lat": 43.0951, "lon": -0.0434, "radius_km": 70,
                    "min_strikes": 5, "gap_min": 15},
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        for ev in body["events"]:
            assert ev["id"].startswith("ev-")
            assert isinstance(ev["start_ts"], int)
            assert isinstance(ev["end_ts"], int)

    def test_invalid_param_type_422(self):
        r = requests.get(f"{BASE_URL}/api/replay/events?lat=abc", timeout=15)
        assert r.status_code == 422


# ---------------- ASGI in-process burst-detection tests ----------------
async def _inject_and_call(strikes_to_add, params=None):
    import lightning as L
    from server import app

    original = list(L.store._buf)
    L.store._buf.clear()
    try:
        for s in strikes_to_add:
            await L.store.add(s)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/replay/events", params=params or {"lat": 43.0951, "lon": -0.0434})
        return r.status_code, r.json()
    finally:
        L.store._buf.clear()
        for s in original:
            L.store._buf.append(s)


class TestBurstDetection:
    def test_detects_two_bursts_ignores_isolated_strike(self):
        now = time.time()
        strikes = []
        # Burst 1: 12 strikes/14.7 min, ~2h ago
        for i in range(12):
            strikes.append({"lat": 43.0 + 0.002 * i, "lon": -0.05, "ts": now - 7200 + i * 80})
        # Isolated strike
        strikes.append({"lat": 43.0, "lon": -0.05, "ts": now - 1800})
        # Burst 2: 8 strikes/8.2 min, ~1h ago
        for i in range(8):
            strikes.append({"lat": 43.1 + 0.001 * i, "lon": 0.0, "ts": now - 3600 + i * 70})

        status, data = asyncio.run(_inject_and_call(strikes))
        assert status == 200
        assert data["source_window_h"] == 24
        events = data["events"]
        assert len(events) == 2, f"Expected 2 events, got {len(events)}: {events}"

        for ev in events:
            assert ev["id"].startswith("ev-")
            assert ev["end_ts"] >= ev["start_ts"]
            assert ev["duration_min"] >= 5.0
            assert ev["strike_count"] >= 5
            assert ev["peak_count_10min"] >= 1
            assert isinstance(ev["center_lat"], float)
            assert isinstance(ev["center_lon"], float)
            assert "max_distance_km" in ev

        # Sort order: by (-peak_count_10min, -strike_count, -start_ts)
        sorted_check = sorted(
            events, key=lambda e: (-e["peak_count_10min"], -e["strike_count"], -e["start_ts"])
        )
        assert events == sorted_check

    def test_short_burst_below_5_min_excluded(self):
        now = time.time()
        # 6 strikes in 2 min -> excluded (< 5 min)
        strikes = [{"lat": 43.0 + 0.001 * i, "lon": -0.05, "ts": now - 1000 + i * 20}
                   for i in range(6)]
        status, data = asyncio.run(_inject_and_call(strikes))
        assert status == 200
        assert data["events"] == []

    def test_below_min_strikes_excluded(self):
        now = time.time()
        # 4 strikes (< 5) over 10 min
        strikes = [{"lat": 43.0, "lon": -0.05, "ts": now - 1200 + i * 200} for i in range(4)]
        status, data = asyncio.run(_inject_and_call(strikes))
        assert status == 200
        assert data["events"] == []

    def test_event_id_format_and_centroid(self):
        now = time.time()
        # Single tight burst
        strikes = [{"lat": 43.05 + 0.001 * i, "lon": -0.10, "ts": now - 3600 + i * 60}
                   for i in range(10)]
        status, data = asyncio.run(_inject_and_call(strikes))
        assert status == 200
        events = data["events"]
        assert len(events) == 1
        ev = events[0]
        assert ev["id"] == f"ev-{ev['start_ts']}"
        # centroid lat ~ avg of 43.050..43.059 ≈ 43.0545, rounded 4
        assert 43.05 <= ev["center_lat"] <= 43.06
        # 4 decimal rounding
        assert ev["center_lat"] == round(ev["center_lat"], 4)
        assert ev["center_lon"] == round(ev["center_lon"], 4)

"""
Iteration 32 - Validates the 3 recent changes:
1. /api/storms/zones = strictly 25 zones (5x5) for any radius, no cache
2. /api/weather/wind-grid = strictly 25 arrows, source='live'
3. Regression on other weather endpoints (severe cached, current, forecast, history, grid)
"""
import os
import time
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    envp = "/app/frontend/.env"
    if os.path.exists(envp):
        for line in open(envp):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_url()


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- Zones ----------
def test_zones_radius_20_returns_25(s):
    r = s.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 20}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    zones = data.get("zones") or data.get("data") or data
    if isinstance(data, dict) and "zones" in data:
        zones = data["zones"]
    assert isinstance(zones, list), f"zones is not list: {type(zones)} - {data}"
    assert len(zones) == 25, f"Expected 25 zones for radius=20, got {len(zones)}"
    assert data.get("source") == "live", f"source={data.get('source')}"


def test_zones_radius_60_returns_25(s):
    r = s.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 60}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    zones = data.get("zones", data)
    assert len(zones) == 25, f"Expected 25 zones for radius=60, got {len(zones)}"


def test_zones_no_cache_fetched_at_changes(s):
    r1 = s.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 20}, timeout=30)
    time.sleep(1.5)
    r2 = s.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 20}, timeout=30)
    assert r1.status_code == 200 and r2.status_code == 200
    f1 = r1.json().get("fetched_at")
    f2 = r2.json().get("fetched_at")
    assert f1 and f2, f"fetched_at missing: {f1} {f2}"
    assert f1 != f2, f"fetched_at identical → cache detected: {f1} == {f2}"


# ---------- Wind grid ----------
def test_wind_grid_25_arrows_live(s):
    r = s.get(f"{BASE_URL}/api/weather/wind-grid", params={"radius_km": 20}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    arrows = data.get("arrows", data.get("wind", []))
    assert len(arrows) == 25, f"Expected 25 wind arrows, got {len(arrows)}"
    assert data.get("source") == "live", f"source={data.get('source')}"


# ---------- Severe (cache 48h) ----------
def test_severe_48h(s):
    r = s.get(f"{BASE_URL}/api/weather/severe", params={"hours": 48}, timeout=45)
    assert r.status_code == 200, r.text
    data = r.json()
    hourly = data.get("hourly") or data.get("data") or []
    assert len(hourly) >= 40, f"Expected ~48 hours, got {len(hourly)}"
    # max_hail_score should be present in at least one entry
    keys = set()
    if hourly:
        keys = set(hourly[0].keys())
    assert any("hail" in k for k in keys) or "max_hail_score" in data, f"No hail data: {keys}"


# ---------- Standard weather endpoints ----------
@pytest.mark.parametrize("path", [
    "/api/weather/current",
    "/api/weather/forecast",
    "/api/weather/history",
    "/api/weather/history-days",
])
def test_weather_endpoints(s, path):
    r = s.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


# ---------- Severe grid (France bulk) ----------
def test_severe_grid_cape(s):
    r = s.get(f"{BASE_URL}/api/weather/severe/grid", params={"param": "cape"}, timeout=45)
    # Accept 200 or 503 (rate limit)
    assert r.status_code in (200, 503), f"{r.status_code}: {r.text[:200]}"


def test_severe_grid_status(s):
    r = s.get(f"{BASE_URL}/api/weather/severe/grid/status", timeout=15)
    assert r.status_code == 200, r.text

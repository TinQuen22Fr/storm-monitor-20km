"""Phase 35 — Bulk Fetch & Local Storage architecture conformance tests.

Validates the 5 spec points from the user:
  1. Single bulk Open-Meteo call covering all params × all hours × all locs
  2. Local persistent storage in /app/backend/cache/grid_bulk.json
  3. Slider scrubbing emits ZERO upstream HTTP calls
  4. Response time < 250 ms in preview env
  5. NO sleep/retry in the map component code path

Plus: /status endpoint + restart-from-disk persistence.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"
CACHE_FILE = Path("/app/backend/cache/grid_bulk.json")
BACKEND_LOG = Path("/var/log/supervisor/backend.err.log")
SEVERE_PY = Path("/app/backend/severe.py")

PARAMS = ["t2m", "t850", "soil_t", "cape", "freezing_level",
          "jet_speed", "vv700", "shear_0_6km", "hail_score"]


def _tail_log_size():
    """Return current size of the backend error log (where httpx INFO lines go)."""
    try:
        return BACKEND_LOG.stat().st_size
    except FileNotFoundError:
        return 0


def _count_openmeteo_calls_since(offset):
    """Count httpx 'HTTP Request: GET https://api.open-meteo.com' lines in log since offset bytes."""
    if not BACKEND_LOG.exists():
        return 0, ""
    with BACKEND_LOG.open("rb") as f:
        f.seek(offset)
        chunk = f.read().decode("utf-8", errors="ignore")
    pattern = re.compile(r"HTTP Request: GET https?://api\.open-meteo\.com", re.IGNORECASE)
    matches = pattern.findall(chunk)
    return len(matches), chunk


def _reset_backend_with_clean_cache():
    """Remove cache file and restart backend (cold start scenario)."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    subprocess.run(["supervisorctl", "restart", "backend"], check=False, capture_output=True)
    # Wait for backend to come up
    for _ in range(30):
        try:
            r = requests.get(f"{API}/health", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError("backend did not come back up")


def _restart_backend_keep_cache():
    subprocess.run(["supervisorctl", "restart", "backend"], check=False, capture_output=True)
    for _ in range(30):
        try:
            r = requests.get(f"{API}/health", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError("backend did not come back up")


# --------------------------------------------------------------------------- #
# Point 5 — NO sleep / retry in map component code path
# --------------------------------------------------------------------------- #
def test_point5_no_sleep_in_bulk_functions():
    """severe.py bulk functions must contain no asyncio.sleep / time.sleep."""
    src = SEVERE_PY.read_text(encoding="utf-8")
    # Verify the bulk section (after Phase 35 marker) has no sleep
    bulk_section_start = src.find("# Bulk fetch architecture (Phase 35")
    assert bulk_section_start > 0, "Phase 35 bulk section marker missing"
    bulk_section = src[bulk_section_start:]
    assert "asyncio.sleep" not in bulk_section, "asyncio.sleep found in bulk section"
    assert "time.sleep" not in bulk_section, "time.sleep found in bulk section"


# --------------------------------------------------------------------------- #
# Point 1 — Single bulk upstream call on cold start
# --------------------------------------------------------------------------- #
def test_point1_single_bulk_call_on_cold_start():
    _reset_backend_with_clean_cache()
    offset_before = _tail_log_size()
    t0 = time.time()
    r = requests.get(f"{API}/weather/severe/grid", params={"param": "t850", "hour": 0}, timeout=60)
    dt = time.time() - t0
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
    body = r.json()
    assert body.get("source") == "bulk", f"source={body.get('source')}"
    assert len(body.get("values", [])) == 192, f"len(values)={len(body.get('values', []))}"
    # Wait for upstream log lines to flush
    time.sleep(2)
    n_calls, chunk = _count_openmeteo_calls_since(offset_before)
    assert n_calls == 1, f"expected 1 upstream call, got {n_calls}\n--- log slice ---\n{chunk[-3000:]}"
    # Verify >=11 hourly variables in that single call
    m = re.search(r"hourly=([^\s&]+)", chunk)
    assert m, "hourly=... pattern not found in log line"
    # Open-Meteo URL is logged URL-encoded — %2C is the comma separator
    raw = m.group(1).replace("%2C", ",").replace("%2c", ",")
    hourly_vars = raw.split(",")
    assert len(hourly_vars) >= 11, f"only {len(hourly_vars)} hourly vars: {hourly_vars}"
    print(f"[cold-start] {dt:.2f}s, {len(hourly_vars)} hourly vars: {hourly_vars}")


# --------------------------------------------------------------------------- #
# Point 2 — Disk persistence with expected JSON structure
# --------------------------------------------------------------------------- #
def test_point2_disk_persistence_structure():
    assert CACHE_FILE.exists(), f"cache file missing: {CACHE_FILE}"
    size = CACHE_FILE.stat().st_size
    assert size > 100_000, f"cache file too small: {size} bytes"
    with CACHE_FILE.open() as f:
        data = json.load(f)
    for k in ["fetched_at", "run_iso", "n_hours", "n_locs",
              "times", "lats", "lons", "per_param", "units"]:
        assert k in data, f"missing key: {k}"
    per_param = data["per_param"]
    for p in PARAMS:
        assert p in per_param, f"missing param key in per_param: {p}"
    assert len(per_param) == 9, f"expected 9 params, got {len(per_param)}: {list(per_param)}"
    assert data["n_locs"] == 192
    assert data["n_hours"] >= 48


# --------------------------------------------------------------------------- #
# Points 3 + 4 — Burst test: zero upstream calls + <250 ms avg
# --------------------------------------------------------------------------- #
def test_point3_4_burst_no_upstream_and_fast():
    # warm up to be sure snapshot is in memory
    requests.get(f"{API}/weather/severe/grid", params={"param": "t850", "hour": 0}, timeout=10)
    time.sleep(1)
    offset_before = _tail_log_size()

    durations = []
    statuses = []
    sources = []
    n_values = []
    degraded_count = 0
    for i in range(50):
        param = PARAMS[i % len(PARAMS)]
        hour = i % 48
        t0 = time.time()
        r = requests.get(f"{API}/weather/severe/grid",
                         params={"param": param, "hour": hour}, timeout=10)
        dt = (time.time() - t0) * 1000
        durations.append(dt)
        statuses.append(r.status_code)
        if r.status_code == 200:
            b = r.json()
            sources.append(b.get("source"))
            n_values.append(len(b.get("values", [])))
            if b.get("degraded"):
                degraded_count += 1

    time.sleep(2)
    n_calls, chunk = _count_openmeteo_calls_since(offset_before)
    avg = sum(durations) / len(durations)
    mx = max(durations)
    print(f"[burst-50] avg={avg:.1f}ms max={mx:.1f}ms upstream_calls={n_calls}")
    print(f"[burst-50] sources unique: {set(sources)} n_values unique: {set(n_values)}")
    assert all(s == 200 for s in statuses), f"non-200 statuses: {set(statuses)}"
    assert n_calls == 0, f"expected 0 upstream calls during burst, got {n_calls}\n{chunk[-1500:]}"
    assert all(s == "bulk" for s in sources), f"non-bulk sources: {set(sources)}"
    assert all(n == 192 for n in n_values), f"unexpected values lengths: {set(n_values)}"
    assert degraded_count == 0, f"degraded responses: {degraded_count}"
    assert avg < 250, f"avg response time {avg:.1f}ms >= 250ms"
    assert mx < 1000, f"max response time {mx:.1f}ms >= 1000ms"


# --------------------------------------------------------------------------- #
# /status endpoint
# --------------------------------------------------------------------------- #
def test_status_endpoint():
    r = requests.get(f"{API}/weather/severe/grid/status", timeout=10)
    assert r.status_code == 200
    s = r.json()
    assert s.get("available") is True
    assert set(s.get("params", [])) == set(PARAMS)
    assert s.get("n_hours") >= 48
    assert s.get("n_locs") == 192
    assert s.get("fresh") is True
    assert s.get("in_memory") is True
    assert s.get("on_disk") is True
    assert 0 <= s.get("age_seconds", 99999) < 600
    fd = s.get("fetch_duration_s")
    assert fd is not None and 0.1 <= fd <= 30, f"fetch_duration_s={fd}"


# --------------------------------------------------------------------------- #
# Disk persistence on restart (no upstream call)
# --------------------------------------------------------------------------- #
def test_persistence_on_restart_no_upstream():
    assert CACHE_FILE.exists(), "cache file missing before restart"
    _restart_backend_keep_cache()
    offset_before = _tail_log_size()
    t0 = time.time()
    r = requests.get(f"{API}/weather/severe/grid",
                     params={"param": "cape", "hour": 5}, timeout=10)
    dt = (time.time() - t0) * 1000
    assert r.status_code == 200
    assert r.json().get("source") == "bulk"
    time.sleep(2)
    n_calls, chunk = _count_openmeteo_calls_since(offset_before)
    assert n_calls == 0, f"expected 0 upstream calls after restart, got {n_calls}\n{chunk[-1500:]}"
    assert dt < 1500, f"after-restart response too slow: {dt:.1f}ms"
    print(f"[after-restart] {dt:.1f}ms upstream_calls={n_calls}")

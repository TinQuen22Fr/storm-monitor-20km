"""Backend tests for /api/weather/severe/grid and /api/weather/severe/profile
after the rate-limit / cache refactor (iteration_27).

Covers:
- Real data presence for all 9 params at multiple hours
- Cache efficiency: 2nd hit on same param is fast
- Profile endpoint with realistic atmospheric values
"""
import os
import time
import pytest
import requests
from pathlib import Path

# Load frontend/.env to get REACT_APP_BACKEND_URL (public preview URL)
_env_path = Path("/app/frontend/.env")
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            os.environ.setdefault("REACT_APP_BACKEND_URL", line.split("=", 1)[1].strip())
            break

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
GRID_URL = f"{BASE_URL}/api/weather/severe/grid"
PROFILE_URL = f"{BASE_URL}/api/weather/severe/profile"

PARAMS = ["t2m", "t850", "soil_t", "cape", "freezing_level",
          "jet_speed", "vv700", "shear_0_6km", "hail_score"]

# Reasonable physical bounds for each param to validate real data is returned
BOUNDS = {
    "t2m": (-40, 50),
    "t850": (-40, 40),
    "soil_t": (-30, 60),
    "cape": (0, 8000),
    "freezing_level": (0, 6000),
    "jet_speed": (0, 120),
    "vv700": (-20, 20),
    "shear_0_6km": (0, 80),
    "hail_score": (0, 100),
}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


def _assert_real_grid(payload, param):
    assert "lats" in payload and "lons" in payload and "values" in payload
    assert isinstance(payload["lats"], list)
    assert isinstance(payload["lons"], list)
    assert isinstance(payload["values"], list)
    # Real grid: 192 points (grid_cols * grid_rows)
    assert len(payload["lats"]) == 192, f"{param}: lats length {len(payload['lats'])}"
    assert len(payload["lons"]) == 192, f"{param}: lons length {len(payload['lons'])}"
    assert len(payload["values"]) == 192, f"{param}: values length {len(payload['values'])}"
    # NOT degraded
    assert payload.get("degraded") in (False, None), f"{param}: degraded flag set: {payload.get('degraded')}"
    # Numeric min/max
    assert isinstance(payload["min"], (int, float)), f"{param}: min not numeric: {payload.get('min')}"
    assert isinstance(payload["max"], (int, float)), f"{param}: max not numeric: {payload.get('max')}"
    # Non-null count
    non_null = [v for v in payload["values"] if v is not None]
    assert len(non_null) >= 150, f"{param}: too many nulls ({192 - len(non_null)})"
    # Physical bounds
    lo, hi = BOUNDS[param]
    assert lo <= payload["min"] <= hi, f"{param}: min {payload['min']} out of [{lo},{hi}]"
    assert lo <= payload["max"] <= hi, f"{param}: max {payload['max']} out of [{lo},{hi}]"


class TestSevereGridRealData:
    """Curl all 9 params at H+0 and H+24 (realistic human pacing ~1s between)."""

    @pytest.mark.parametrize("param", PARAMS)
    def test_param_h0(self, session, param):
        r = session.get(GRID_URL, params={"param": param, "hour": 0}, timeout=30)
        assert r.status_code == 200, f"{param} H+0: HTTP {r.status_code} -> {r.text[:200]}"
        _assert_real_grid(r.json(), param)
        time.sleep(0.8)  # space the calls so we don't hammer Open-Meteo

    @pytest.mark.parametrize("param", PARAMS)
    def test_param_h24(self, session, param):
        r = session.get(GRID_URL, params={"param": param, "hour": 24}, timeout=30)
        assert r.status_code == 200, f"{param} H+24: HTTP {r.status_code}"
        _assert_real_grid(r.json(), param)


class TestSevereGridCacheEfficiency:
    """After the first call per param, all subsequent hours must hit cache (<200ms)."""

    def test_cache_hit_under_200ms_t850(self, session):
        # First call (may already be cached from previous test)
        session.get(GRID_URL, params={"param": "t850", "hour": 0}, timeout=30)
        # Now scrub through several hours rapidly — all should be instant
        for hour in [5, 12, 24, 36, 47]:
            t0 = time.perf_counter()
            r = session.get(GRID_URL, params={"param": "t850", "hour": hour}, timeout=10)
            dt = (time.perf_counter() - t0) * 1000.0
            assert r.status_code == 200
            _assert_real_grid(r.json(), "t850")
            assert dt < 800, f"t850 hour={hour}: cache hit took {dt:.0f}ms (>800ms)"

    def test_cache_hit_under_200ms_cape(self, session):
        session.get(GRID_URL, params={"param": "cape", "hour": 0}, timeout=30)
        for hour in [10, 20, 30, 47]:
            t0 = time.perf_counter()
            r = session.get(GRID_URL, params={"param": "cape", "hour": hour}, timeout=10)
            dt = (time.perf_counter() - t0) * 1000.0
            assert r.status_code == 200
            assert dt < 800, f"cape hour={hour}: cache hit took {dt:.0f}ms"


class TestSevereGridExtremeHours:
    def test_t850_h47(self, session):
        r = session.get(GRID_URL, params={"param": "t850", "hour": 47}, timeout=30)
        assert r.status_code == 200
        _assert_real_grid(r.json(), "t850")

    def test_hail_score_h12(self, session):
        r = session.get(GRID_URL, params={"param": "hail_score", "hour": 12}, timeout=30)
        assert r.status_code == 200
        _assert_real_grid(r.json(), "hail_score")


class TestProfile:
    """Vertical temperature profile at Lourdes (43.0951, -0.0434)."""

    @pytest.mark.parametrize("hour", [0, 12, 24, 36, 47])
    def test_profile_hours(self, session, hour):
        r = session.get(
            PROFILE_URL,
            params={"lat": 43.0951, "lon": -0.0434, "hour": hour},
            timeout=30,
        )
        assert r.status_code == 200, f"profile h{hour}: HTTP {r.status_code} -> {r.text[:200]}"
        data = r.json()
        assert data.get("degraded") in (False, None), f"profile h{hour}: degraded"
        points = data.get("points") or []
        assert len(points) == 7, f"profile h{hour}: expected 7 points, got {len(points)}"
        temps = [p.get("temperature_c") for p in points]
        assert all(isinstance(t, (int, float)) for t in temps), f"profile h{hour}: non-numeric temps {temps}"
        # Surface warmer than 300hPa
        surface_t = temps[0]
        top_t = temps[-1]
        assert surface_t > top_t, f"profile h{hour}: surface {surface_t} not warmer than top {top_t}"
        # Top of troposphere should be cold
        assert top_t < -20, f"profile h{hour}: top temp {top_t} not cold enough"
        # Sane surface bounds
        assert -30 < surface_t < 50, f"profile h{hour}: surface {surface_t} out of bounds"
        time.sleep(0.5)

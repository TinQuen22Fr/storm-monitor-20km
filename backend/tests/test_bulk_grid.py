"""Test bulk grid endpoint - Phase 35 (Bulk Fetch & Local Storage)"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Try frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestBulkGridEndpoint:
    """Tests for GET /api/weather/severe/grid/bulk"""

    def test_bulk_returns_200(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:200]}"

    def test_bulk_payload_shape(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        assert r.status_code == 200
        d = r.json()

        required_keys = {
            "fetched_at", "run_iso", "bbox", "grid_cols", "grid_rows",
            "n_locs", "n_hours", "times", "lats", "lons", "per_param", "units",
        }
        missing = required_keys - set(d.keys())
        assert not missing, f"Missing keys: {missing}"

        assert d["grid_cols"] == 16
        assert d["grid_rows"] == 12
        assert d["n_locs"] == 192
        assert d["n_hours"] >= 47, f"Expected ~48 hours, got {d['n_hours']}"
        assert len(d["times"]) == d["n_hours"]
        assert len(d["lats"]) == 192
        assert len(d["lons"]) == 192

    def test_per_param_has_9_keys(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        d = r.json()
        expected_params = {
            "t2m", "t850", "soil_t", "cape", "freezing_level",
            "jet_speed", "vv700", "shear_0_6km", "hail_score",
        }
        got = set(d["per_param"].keys())
        assert expected_params == got, f"Param mismatch: missing={expected_params-got}, extra={got-expected_params}"

        # Each matrix is n_hours × n_locs
        for p in expected_params:
            matrix = d["per_param"][p]
            assert len(matrix) == d["n_hours"], f"{p}: expected {d['n_hours']} rows, got {len(matrix)}"
            assert len(matrix[0]) == d["n_locs"], f"{p}: expected {d['n_locs']} cols, got {len(matrix[0])}"

    def test_bulk_second_call_uses_cache(self, api_client):
        # Warmup
        api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        # Time the cached call
        t0 = time.time()
        r = api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        dt = time.time() - t0
        assert r.status_code == 200
        # Cached calls should be < 2s (network roundtrip dominated)
        assert dt < 5.0, f"Cached bulk call too slow: {dt:.2f}s"

    def test_units_present(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        d = r.json()
        assert "units" in d
        assert d["units"].get("t2m") == "°C"
        assert d["units"].get("jet_speed") == "m/s"


class TestLegacyGridEndpoint:
    """Legacy endpoint must still work for backwards compat but should not be required."""

    def test_legacy_grid_still_responds(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/weather/severe/grid",
            params={"param": "t2m", "hour": 0},
            timeout=60,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("param") == "t2m"
        assert "values" in d


class TestBulkStatus:
    def test_status_after_bulk(self, api_client):
        api_client.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=60)
        r = api_client.get(f"{BASE_URL}/api/weather/severe/grid/status", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("available") is True
        assert d.get("n_locs") == 192

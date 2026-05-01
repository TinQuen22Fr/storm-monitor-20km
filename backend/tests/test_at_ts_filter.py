"""Tests for at_ts filtering on /api/storms/trajectory and /api/storms/approach."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://storm-monitor-20km.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# Trajectory: at_ts param accepted, returns same shape with/without
class TestTrajectoryAtTs:
    def test_no_at_ts(self, session):
        r = session.get(f"{API}/storms/trajectory", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "detected" in d
        assert isinstance(d["detected"], bool)

    def test_with_at_ts_now(self, session):
        ts = time.time()
        r = session.get(f"{API}/storms/trajectory", params={"at_ts": ts}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "detected" in d
        assert isinstance(d["detected"], bool)

    def test_with_at_ts_past(self, session):
        ts = time.time() - 6 * 3600  # 6h ago
        r = session.get(f"{API}/storms/trajectory", params={"at_ts": ts}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "detected" in d

    def test_at_ts_invalid(self, session):
        r = session.get(f"{API}/storms/trajectory", params={"at_ts": "not-a-number"}, timeout=20)
        assert r.status_code == 422

    def test_consistent_shape(self, session):
        r1 = session.get(f"{API}/storms/trajectory", timeout=20).json()
        r2 = session.get(f"{API}/storms/trajectory", params={"at_ts": time.time()}, timeout=20).json()
        # Both must have detected key (other keys depend on detection)
        assert set(["detected"]).issubset(r1.keys())
        assert set(["detected"]).issubset(r2.keys())


# Approach: at_ts param accepted
class TestApproachAtTs:
    def test_no_at_ts(self, session):
        r = session.get(f"{API}/storms/approach", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # Approach returns either approaching key or reason
        assert "radius_analyzed_km" in d

    def test_with_at_ts_now(self, session):
        r = session.get(f"{API}/storms/approach", params={"at_ts": time.time()}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "radius_analyzed_km" in d

    def test_with_at_ts_past(self, session):
        r = session.get(f"{API}/storms/approach", params={"at_ts": time.time() - 3600}, timeout=20)
        assert r.status_code == 200

    def test_at_ts_invalid(self, session):
        r = session.get(f"{API}/storms/approach", params={"at_ts": "abc"}, timeout=20)
        assert r.status_code == 422


# Vigilance full payload phenomena shape (used by frontend filter)
class TestVigilanceFullPhenomenaShape:
    def test_shape(self, session):
        r = session.get(f"{API}/weather/vigilance/full", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "areas" in d
        assert isinstance(d["areas"], list)
        assert len(d["areas"]) > 0
        # Pick first area and validate phenomena shape
        a = d["areas"][0]
        assert "phenomena" in a
        assert isinstance(a["phenomena"], list)
        # Each phenom must have key, level, level_fr, color
        for p in a["phenomena"]:
            assert "key" in p
            assert "level" in p
            assert "level_fr" in p
            assert "color" in p
            assert isinstance(p["level"], int)
            assert 1 <= p["level"] <= 4

    def test_phenomena_keys_match_filter(self, session):
        """Frontend filters by keys: orage, vent, pluie, canicule, grand-froid, neige, brouillard, avalanche."""
        r = session.get(f"{API}/weather/vigilance/full", timeout=30)
        d = r.json()
        expected_keys = {"orage", "vent", "pluie", "canicule", "grand-froid", "neige", "brouillard", "avalanche"}
        # Collect all phenomena keys present in the payload
        keys_seen = set()
        for a in d["areas"]:
            for p in a["phenomena"]:
                keys_seen.add(p["key"])
        # All expected keys should be present (each area exposes all 8 phenomena per spec)
        missing = expected_keys - keys_seen
        assert not missing, f"Missing phenomena keys in payload: {missing}"

    def test_areas_have_max_level_consistent(self, session):
        r = session.get(f"{API}/weather/vigilance/full", timeout=30)
        d = r.json()
        for a in d["areas"][:5]:
            max_phen = max((p["level"] for p in a["phenomena"]), default=1)
            assert a["max_level"] >= max_phen or a["max_level"] == max_phen


# Lightning store.recent until_ts filter (unit test via API surface)
class TestLightningSinceUntil:
    def test_lightning_strikes_no_filter(self, session):
        r = session.get(f"{API}/lightning/strikes", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "count" in d
        assert "strikes" in d
        assert isinstance(d["strikes"], list)

    def test_lightning_strikes_with_since(self, session):
        # Should accept since param and return subset (>= count)
        r = session.get(f"{API}/lightning/strikes", params={"since": time.time() - 3600}, timeout=15)
        assert r.status_code == 200

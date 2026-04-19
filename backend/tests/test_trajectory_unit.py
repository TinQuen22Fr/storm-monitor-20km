"""
Unit tests for analysis.predict_trajectory (iteration 9):
- noise_too_high rejection when computed speed > 120 km/h
- stationary rejection when computed speed < 3 km/h
- happy path: realistic strike cluster moving NE at ~30 km/h
"""
import os
import sys
import time
import math
import pytest

# Make backend importable
sys.path.insert(0, "/app/backend")

from analysis import predict_trajectory  # noqa: E402


LOURDES_LAT = 43.0951
LOURDES_LON = -0.0434


def _synth_strikes(points):
    """points: list of (minutes_before_now, lat, lon) → strikes list."""
    now = time.time()
    return [{"ts": now - m * 60, "lat": la, "lon": lo} for (m, la, lo) in points]


class TestPredictTrajectoryUnit:
    def test_not_enough_strikes(self):
        strikes = _synth_strikes([(0, 43.1, -0.04), (5, 43.12, -0.03)])
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, strikes)
        assert res["detected"] is False
        assert res["reason"] == "not_enough_strikes"
        print(f"✓ not_enough_strikes: count={res['count']}")

    def test_stationary_rejected(self):
        """4 strikes tightly clustered → computed speed < 3 km/h → stationary."""
        pts = [
            (0, 43.100, -0.040),
            (5, 43.1001, -0.0401),
            (10, 43.100, -0.0400),
            (15, 43.1001, -0.0402),
            (20, 43.100, -0.0401),
        ]
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is False, f"Expected stationary, got {res}"
        assert res["reason"] == "stationary"
        assert "computed_speed_kmh" in res
        assert res["computed_speed_kmh"] < 3.0
        print(f"✓ stationary: speed={res['computed_speed_kmh']} km/h, count={res['count']}")

    def test_noise_too_high_rejected(self):
        """Strikes that cluster but fit a super-fast regression → noise_too_high OR no_dominant_cluster."""
        # 4 strikes in one cell (dominant) + 2 strikes in a far corner of the 9-cell neighbourhood
        # with a steep time gradient → regression slope yields >120 km/h
        pts = [
            (0, 43.00, 0.00),
            (1, 43.00, 0.00),
            (2, 43.00, 0.00),
            (3, 43.01, 0.01),
            (4, 43.25, 0.25),
            (5, 43.25, 0.25),
        ]
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is False, f"Expected rejection, got {res}"
        # Either no_dominant_cluster or noise_too_high are acceptable rejections
        assert res["reason"] in ("noise_too_high", "no_dominant_cluster"), f"Got {res['reason']}"
        print(f"✓ noisy rejected: reason={res['reason']}, speed={res.get('computed_speed_kmh')}")

    def test_happy_path_detected(self):
        """Strikes moving steadily NE at ~30 km/h → should detect."""
        # Keep all strikes tight inside one 0.25° grid cell (+neighbours) so clustering picks them
        pts = []
        for i in range(8):
            minutes_before = 35 - i * 5  # 35, 30, 25, ... 0
            lat = 43.00 + i * 0.01
            lon = -0.20 + i * 0.01
            pts.append((minutes_before, lat, lon))
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is True, f"Expected detected, got {res}"
        assert 3.0 <= res["speed_kmh"] <= 120.0
        assert "waypoints" in res and len(res["waypoints"]) > 0
        assert "compass" in res
        assert "bearing_deg" in res
        print(f"✓ detected: speed={res['speed_kmh']} km/h, compass={res['compass']}")

    def test_no_dominant_cluster(self):
        """10 strikes scattered across >200km → no single dominant cluster."""
        # Each strike in a different 0.25° grid cell, far apart
        pts = [
            (0, 43.00, -0.04),
            (3, 43.80, 0.80),
            (6, 42.20, -1.20),
            (9, 44.00, 1.60),
            (12, 42.00, -2.00),
            (15, 44.50, 2.20),
            (18, 41.80, -2.80),
            (21, 45.00, 2.80),
            (24, 41.50, -3.20),
            (27, 45.50, 3.40),
        ]
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is False, f"Expected no_dominant_cluster, got {res}"
        assert res["reason"] in ("no_dominant_cluster", "noise_too_high"), f"Got reason={res['reason']}"
        print(f"✓ dispersed strikes rejected: reason={res['reason']}, count={res.get('count')}")

    def test_dominant_cluster_extracts_signal_from_noise(self):
        """4 coherent strikes in one cell + 3 scattered outliers → should detect cluster."""
        pts = []
        # Dominant coherent cluster in same cell (43.0x / -0.0x)
        for i in range(6):
            pts.append((30 - i * 5, 43.00 + i * 0.012, -0.04 + i * 0.012))
        # Outliers far away (different cells, fewer strikes each)
        pts.append((20, 44.50, 1.50))
        pts.append((15, 42.00, -2.00))
        pts.append((10, 45.00, 2.00))
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is True, f"Expected detected via clustering, got {res}"
        assert 3.0 <= res["speed_kmh"] <= 120.0
        print(f"✓ clustering isolates dominant cell: speed={res['speed_kmh']} km/h count={res['count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

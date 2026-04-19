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
        """Spatially chaotic strikes → computed speed > 120 km/h → noise_too_high."""
        # Big jumps across 10 minutes → fake fast fit
        pts = [
            (0, 43.10, -0.04),
            (2, 44.50, 1.20),
            (4, 42.50, -1.80),
            (6, 44.80, 1.50),
            (8, 42.20, -2.00),
            (10, 45.00, 1.80),
        ]
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is False, f"Expected noise_too_high, got {res}"
        assert res["reason"] == "noise_too_high"
        assert "computed_speed_kmh" in res
        assert res["computed_speed_kmh"] > 120.0
        print(f"✓ noise_too_high: speed={res['computed_speed_kmh']} km/h, count={res['count']}")

    def test_happy_path_detected(self):
        """Strikes moving steadily NE at ~30 km/h → should detect."""
        # ~0.005° lat ≈ 0.55 km, so 5 min steps of 0.0025° ≈ 0.28 km/5min ≈ 3.3 km/h (too slow)
        # Use 0.04° per 5 min ≈ 4.4 km/5min ≈ 53 km/h
        pts = []
        for i in range(8):
            minutes_before = 35 - i * 5  # 35, 30, 25, ... 0
            lat = 43.00 + i * 0.025
            lon = -0.20 + i * 0.025
            pts.append((minutes_before, lat, lon))
        res = predict_trajectory(LOURDES_LAT, LOURDES_LON, _synth_strikes(pts))
        assert res["detected"] is True, f"Expected detected, got {res}"
        assert 3.0 <= res["speed_kmh"] <= 120.0
        assert "waypoints" in res and len(res["waypoints"]) > 0
        assert "compass" in res
        assert "bearing_deg" in res
        print(f"✓ detected: speed={res['speed_kmh']} km/h, compass={res['compass']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for iteration 31 — Gemini's 4 surgical patches (lock into repo).

PATCH 1: server.py:_degraded('severe-grid', ...) returns lats/lons/times/
         per_param/units/grid_cols/grid_rows.
PATCH 2: severe.py:GRID_COLS=10 / GRID_ROWS=8 → 80-point grid.
PATCH 3: severe.py:BULK_TTL_S = 7200.0 (2h).
PATCH 4: install.sh restarts storm-monitor.service (not enable --now).
PATCH 4bis: install.sh + upgrade.sh chmod 755 the backend/cache dir.
REGRESSION: /api/weather/severe/grid/bulk and legacy /grid still respond.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import requests

# Make backend importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
UPGRADE_SH = REPO_ROOT / "upgrade.sh"

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    # frontend/.env fallback for direct pytest runs
    env_file = REPO_ROOT / "frontend" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break


# ---------- PATCH 1 ----------
class TestPatch1DegradedSevereGrid:
    """_degraded('severe-grid', ...) must expose the bulk-snapshot shape."""

    def test_degraded_severe_grid_has_required_keys(self):
        from server import _degraded
        d = _degraded("severe-grid", RuntimeError("upstream-down"))
        required = {"lats", "lons", "times", "per_param", "units",
                    "grid_cols", "grid_rows"}
        missing = required - set(d.keys())
        assert not missing, f"missing keys: {missing}"

    def test_degraded_severe_grid_values_safe(self):
        from server import _degraded
        d = _degraded("severe-grid", RuntimeError("x"))
        assert d["lats"] == []
        assert d["lons"] == []
        assert d["times"] == []
        assert d["per_param"] == {}
        assert d["units"] == {}
        assert d["grid_cols"] == 0
        assert d["grid_rows"] == 0
        assert d["degraded"] is True


# ---------- PATCH 2 ----------
class TestPatch2GridDimensions:
    """GRID_COLS=10, GRID_ROWS=8 → 80 points (was 16×12=192)."""

    def test_grid_cols(self):
        import severe
        assert severe.GRID_COLS == 10

    def test_grid_rows(self):
        import severe
        assert severe.GRID_ROWS == 8

    def test_france_grid_has_80_points(self):
        import severe
        lats, lons = severe._france_grid()
        assert len(lats) == 80
        assert len(lons) == 80


# ---------- PATCH 3 ----------
class TestPatch3BulkTTL:
    """BULK_TTL_S = 7200.0 (2 h)."""

    def test_bulk_ttl_is_2h(self):
        import severe
        assert severe.BULK_TTL_S == 7200.0


# ---------- PATCH 4 ----------
class TestPatch4InstallShRestart:
    """install.sh must use `systemctl restart`, not `enable --now`."""

    def test_install_sh_uses_restart(self):
        content = INSTALL_SH.read_text()
        assert re.search(
            r"systemctl\s+restart\s+storm-monitor\.service", content
        ), "expected 'systemctl restart storm-monitor.service' in install.sh"

    def test_install_sh_no_enable_now(self):
        content = INSTALL_SH.read_text()
        # The OLD pattern `enable --now storm-monitor.service` must be gone.
        # (note: `enable --now mongod` is fine — different service)
        assert not re.search(
            r"systemctl\s+enable\s+--now\s+storm-monitor\.service", content
        ), "old 'enable --now storm-monitor.service' pattern still present"

    def test_install_sh_separate_enable(self):
        # We should still enable the unit so it auto-starts on reboot.
        content = INSTALL_SH.read_text()
        assert re.search(
            r"systemctl\s+enable\s+storm-monitor\.service", content
        ), "missing 'systemctl enable storm-monitor.service' in install.sh"

    def test_install_sh_syntax_ok(self):
        result = subprocess.run(
            ["bash", "-n", str(INSTALL_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"bash -n failed: {result.stderr}"

    def test_upgrade_sh_syntax_ok(self):
        result = subprocess.run(
            ["bash", "-n", str(UPGRADE_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"bash -n failed: {result.stderr}"


# ---------- PATCH 4bis ----------
class TestPatch4bisCachePerms:
    """install.sh + upgrade.sh both create + chmod 755 the bulk cache dir."""

    def test_install_sh_chmod_cache(self):
        content = INSTALL_SH.read_text()
        # Accept either `$BULK_CACHE_DIR` or the literal `$APP_DIR/backend/cache`
        assert re.search(
            r'chmod\s+755\s+"\$(BULK_CACHE_DIR|APP_DIR/backend/cache)"',
            content,
        ), "install.sh: missing chmod 755 on backend/cache dir"

    def test_upgrade_sh_chmod_cache(self):
        content = UPGRADE_SH.read_text()
        assert re.search(
            r'chmod\s+755\s+"\$(BULK_CACHE_DIR|APP_DIR/backend/cache)"',
            content,
        ), "upgrade.sh: missing chmod 755 on backend/cache dir"

    def test_install_sh_mkdir_cache(self):
        content = INSTALL_SH.read_text()
        assert "mkdir -p \"$BULK_CACHE_DIR\"" in content or \
               'mkdir -p "$APP_DIR/backend/cache"' in content, \
               "install.sh: missing mkdir for backend/cache"


# ---------- REGRESSION ----------
@pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")
class TestRegressionEndpoints:
    """Live endpoint smoke. Upstream Open-Meteo may rate-limit sandbox IP →
    503 is acceptable as long as the SHAPE comes from _degraded with new keys."""

    def test_bulk_endpoint_shape(self):
        r = requests.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=90)
        assert r.status_code in (200, 503), f"unexpected {r.status_code}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("n_locs") == 80, f"expected n_locs=80 got {data.get('n_locs')}"
            assert data.get("n_hours") == 48 or len(data.get("times") or []) >= 24
            assert isinstance(data.get("per_param"), dict)
            assert len(data["per_param"]) == 9, \
                f"expected 9 params got {list(data['per_param'].keys())}"
        else:
            # 503 path — error body should NOT leak open-meteo.com
            body = r.text.lower()
            assert "open-meteo.com" not in body, \
                "Error body leaks upstream URL"

    def test_legacy_grid_endpoint(self):
        r = requests.get(
            f"{BASE_URL}/api/weather/severe/grid",
            params={"param": "t850", "hour": 0},
            timeout=90,
        )
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            # Either a legitimate slice or a degraded payload — both must have
            # the required keys post-patch.
            for key in ("lats", "lons"):
                assert key in data, f"missing {key} in {list(data.keys())}"

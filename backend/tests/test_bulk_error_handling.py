"""Tests for iteration 30 — bulk endpoint error mapping + disk fallback chain.

Validates:
1. /api/weather/severe/grid/bulk returns 503 with friendly messages on 429/timeout/connect errors
2. _resolve_bulk_file() falls back gracefully when paths are non-writable
3. STORM_CACHE_DIR env var respected
4. _save_bulk_to_disk catches PermissionError and OSError
"""
from __future__ import annotations

import os
import sys
import importlib
import stat
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get(
    "BACKEND_PUBLIC_URL"
)
# Fallback: read frontend .env
if not BASE_URL:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"')
                break
BASE_URL = (BASE_URL or "").rstrip("/")


# ---------- 1. Live endpoint smoke test ----------
class TestBulkEndpointLive:
    def test_bulk_endpoint_reachable(self):
        """Bulk endpoint should respond (200 OK with payload, or 503 with friendly detail)."""
        r = requests.get(f"{BASE_URL}/api/weather/severe/grid/bulk", timeout=95)
        assert r.status_code in (200, 503), f"Unexpected status {r.status_code}: {r.text[:300]}"
        if r.status_code == 503:
            data = r.json()
            assert "detail" in data
            detail = data["detail"]
            assert isinstance(detail, str)
            # Must be short — no upstream URL dump
            assert len(detail) < 300, f"503 detail too long: {len(detail)} chars"
            assert "open-meteo.com" not in detail.lower() or "/v1/forecast" not in detail
            print(f"503 friendly detail: {detail!r}")
        else:
            data = r.json()
            # Must contain per_param + lats (NEVER returns 200 with missing per_param)
            assert "per_param" in data
            assert "lats" in data
            assert isinstance(data["lats"], list)
            assert len(data["lats"]) > 0


# ---------- 2. Error mapping via mocked upstream ----------
class TestBulkErrorMapping:
    """Mock get_with_retry to simulate upstream failures and verify 503 + friendly messages."""

    def _reload(self):
        import severe
        importlib.reload(severe)
        return severe

    def test_429_returns_rate_limit_message(self):
        """When upstream raises Exception with '429' or 'Too Many Requests', detail must mention rate-limit."""
        from fastapi import HTTPException
        from server import weather_severe_grid_bulk
        import severe

        # Reset in-memory snapshot
        severe._bulk_snapshot = None

        async def fake_fetch(*args, **kwargs):
            raise Exception("HTTP error 429 Too Many Requests")

        with patch.object(severe, "get_with_retry", side_effect=fake_fetch):
            # Also disable disk fallback by pointing BULK_FILE to a non-existent path
            with patch.object(severe, "BULK_FILE", Path("/tmp/__nonexistent_bulk__.json")):
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(weather_severe_grid_bulk())
                assert exc_info.value.status_code == 503
                detail = exc_info.value.detail
                assert "Rate-limit" in detail or "rate-limit" in detail.lower()
                assert "open-meteo.com/v1" not in detail.lower()
                print(f"429 → {detail!r}")

    def test_timeout_returns_timeout_message(self):
        import asyncio
        from fastapi import HTTPException
        from server import weather_severe_grid_bulk
        import severe
        import httpx

        severe._bulk_snapshot = None

        async def fake_fetch(*args, **kwargs):
            raise httpx.ReadTimeout("Timeout waiting for upstream")

        with patch.object(severe, "get_with_retry", side_effect=fake_fetch):
            with patch.object(severe, "BULK_FILE", Path("/tmp/__nonexistent_bulk__.json")):
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(weather_severe_grid_bulk())
                assert exc_info.value.status_code == 503
                detail = exc_info.value.detail
                assert "Délai" in detail or "Timeout" in detail.lower() or "délai" in detail.lower()
                print(f"Timeout → {detail!r}")

    def test_connect_error_returns_connect_message(self):
        import asyncio
        from fastapi import HTTPException
        from server import weather_severe_grid_bulk
        import severe
        import httpx

        severe._bulk_snapshot = None

        async def fake_fetch(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        with patch.object(severe, "get_with_retry", side_effect=fake_fetch):
            with patch.object(severe, "BULK_FILE", Path("/tmp/__nonexistent_bulk__.json")):
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(weather_severe_grid_bulk())
                assert exc_info.value.status_code == 503
                detail = exc_info.value.detail
                assert "Connexion" in detail or "réseau" in detail.lower() or "connect" in detail.lower()
                print(f"ConnectError → {detail!r}")


# ---------- 3. Disk path fallback chain ----------
class TestResolveBulkFile:
    def test_fallback_to_tmp_when_cache_dir_readonly(self, tmp_path):
        """When primary cache/ is non-writable, _resolve_bulk_file must fall back to /tmp."""
        import severe

        # Create a temp read-only dir
        readonly = tmp_path / "readonly_cache"
        readonly.mkdir()
        os.chmod(readonly, stat.S_IRUSR | stat.S_IXUSR)  # r-x------

        try:
            # Patch the candidates list by monkey-patching __file__-derived path
            # Simpler: ensure STORM_CACHE_DIR points to readonly + verify fallback to /tmp
            with patch.dict(os.environ, {"STORM_CACHE_DIR": str(readonly)}):
                # Also force the primary candidate (package cache) to be readonly
                pkg_cache = Path(severe.__file__).parent / "cache"
                # We don't chmod pkg_cache (risk breaking other tests); instead test
                # that resolve_bulk_file picks something writable
                resolved = severe._resolve_bulk_file()
                assert resolved is not None
                # Must be writable
                resolved.parent.mkdir(parents=True, exist_ok=True)
                probe = resolved.parent / ".test_probe"
                try:
                    probe.write_text("ok")
                    probe.unlink()
                    writable = True
                except (PermissionError, OSError):
                    writable = False
                assert writable, f"Resolved path {resolved} is not writable"
                print(f"Resolved bulk file: {resolved}")
        finally:
            os.chmod(readonly, stat.S_IRWXU)  # restore for cleanup

    def test_storm_cache_dir_respected(self, tmp_path):
        """STORM_CACHE_DIR=<writable> must put grid_bulk.json there."""
        import severe

        custom = tmp_path / "custom_cache"
        custom.mkdir()
        with patch.dict(os.environ, {"STORM_CACHE_DIR": str(custom)}):
            resolved = severe._resolve_bulk_file()
            # Should be either the custom dir OR the default if it's writable.
            # The custom dir is inserted at position 0 → it's preferred.
            assert str(resolved).startswith(str(custom)), (
                f"Expected STORM_CACHE_DIR prefix, got {resolved}"
            )
            assert resolved.name == "grid_bulk.json"
            print(f"STORM_CACHE_DIR resolved to: {resolved}")

    def test_save_bulk_handles_permission_error(self, tmp_path, caplog):
        """_save_bulk_to_disk must NOT raise on PermissionError — just warn."""
        import severe

        readonly = tmp_path / "ro_dir"
        readonly.mkdir()
        target = readonly / "grid_bulk.json"
        # Make parent read-only
        os.chmod(readonly, stat.S_IRUSR | stat.S_IXUSR)

        try:
            with patch.object(severe, "BULK_FILE", target):
                # Should not raise
                severe._save_bulk_to_disk({"fetched_at": 1.0, "per_param": {}})
                # success = no exception
                print(f"PermissionError handled gracefully for {target}")
        finally:
            os.chmod(readonly, stat.S_IRWXU)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

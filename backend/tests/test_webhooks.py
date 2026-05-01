"""Tests for Discord/Telegram webhooks feature.

Covers:
  - GET /api/webhooks/status (no secrets leaked, defaults)
  - POST /api/webhooks/test (auth required, returns null channels when unconfigured)
  - webhooks.py module: _discord_url, _telegram_config, _check_cooldown, dispatch, status
  - regressions: /api/push/test, /api/replay/events, /api/weather/vigilance
"""
import asyncio
import importlib
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path("/app/backend")
sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # frontend env file holds the public URL
    env_file = Path("/app/frontend/.env").read_text()
    for line in env_file.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"')
            break
BASE_URL = BASE_URL.rstrip("/")

EMAIL = "test@lourdes.fr"
PASSWORD = "storm123"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        # try register
        api.post(f"{BASE_URL}/api/auth/register", json={"email": EMAIL, "password": PASSWORD, "name": "Storm Tester"})
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture
def webhooks_mod():
    """Fresh module each test so cooldown state is isolated."""
    if "webhooks" in sys.modules:
        del sys.modules["webhooks"]
    return importlib.import_module("webhooks")


# ---------- API: status ----------
class TestWebhooksStatusEndpoint:
    def test_status_no_auth_required(self, api):
        r = api.get(f"{BASE_URL}/api/webhooks/status")
        assert r.status_code == 200
        d = r.json()
        # Required fields
        for k in ["discord_enabled", "telegram_enabled", "cooldown_s", "app_url", "active_cooldowns"]:
            assert k in d, f"missing field {k}"
        assert isinstance(d["discord_enabled"], bool)
        assert isinstance(d["telegram_enabled"], bool)
        assert isinstance(d["cooldown_s"], int)
        assert d["cooldown_s"] == 900
        assert d["app_url"] == "https://storm-monitor.quentin-astro.fr"
        assert isinstance(d["active_cooldowns"], dict)

    def test_status_no_secret_leaked(self, api):
        r = api.get(f"{BASE_URL}/api/webhooks/status")
        text = r.text.lower()
        # Ensure no env-var-style leakage
        for forbidden in ["telegram_bot_token", "discord_webhook_url", "bot_token", "chat_id"]:
            assert forbidden not in text
        # Ensure no token/secret values exposed
        assert "https://discord.com/api/webhooks/" not in r.text or r.json()["discord_enabled"] is False


# ---------- API: test (auth) ----------
class TestWebhooksTestEndpoint:
    def test_test_requires_auth(self, api):
        r = api.post(f"{BASE_URL}/api/webhooks/test")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_test_with_auth_returns_null_channels(self, api, auth_token):
        # Assumes Discord/Telegram NOT configured in env (default)
        r = api.post(
            f"{BASE_URL}/api/webhooks/test",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("tag") == "test"
        # When nothing is configured both should be None
        assert d.get("discord") is None
        assert d.get("telegram") is None


# ---------- Module: _discord_url ----------
class TestDiscordUrl:
    def test_empty_returns_none(self, monkeypatch, webhooks_mod):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        assert webhooks_mod._discord_url() is None

    def test_invalid_prefix_returns_none(self, monkeypatch, webhooks_mod):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://evil.com/api/webhooks/123/abc")
        assert webhooks_mod._discord_url() is None

    def test_valid_prefix_returns_url(self, monkeypatch, webhooks_mod):
        url = "https://discord.com/api/webhooks/999999/invalidtoken"
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", url)
        assert webhooks_mod._discord_url() == url


# ---------- Module: _telegram_config ----------
class TestTelegramConfig:
    def test_missing_both_returns_none(self, monkeypatch, webhooks_mod):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert webhooks_mod._telegram_config() is None

    def test_only_token_returns_none(self, monkeypatch, webhooks_mod):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert webhooks_mod._telegram_config() is None

    def test_only_chat_returns_none(self, monkeypatch, webhooks_mod):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        assert webhooks_mod._telegram_config() is None

    def test_both_set_returns_tuple(self, monkeypatch, webhooks_mod):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        assert webhooks_mod._telegram_config() == ("fake-token", "12345")


# ---------- Module: cooldown via dispatch ----------
class TestCooldown:
    def test_dispatch_cooldown_skipped_on_second_call(self, monkeypatch, webhooks_mod):
        # No channels configured — first call should still register the cooldown timestamp
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(
                webhooks_mod.dispatch("t", "b", "storm-active")
            )
            # 1st call: full dispatch, both channels None
            assert r1.get("tag") == "storm-active"
            assert "skipped" not in r1
            # 2nd call same tag: throttled
            r2 = loop.run_until_complete(
                webhooks_mod.dispatch("t", "b", "storm-active")
            )
            assert r2 == {"skipped": "cooldown", "tag": "storm-active"}
        finally:
            loop.close()

    def test_dispatch_force_bypasses_cooldown(self, monkeypatch, webhooks_mod):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(webhooks_mod.dispatch("t", "b", "lightning-strike"))
            # forced second call must not be skipped
            r = loop.run_until_complete(
                webhooks_mod.dispatch("t", "b", "lightning-strike", force=True)
            )
            assert "skipped" not in r
            assert r.get("tag") == "lightning-strike"
        finally:
            loop.close()

    def test_active_cooldowns_exposed_in_status(self, monkeypatch, webhooks_mod):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(webhooks_mod.dispatch("t", "b", "vigilance-orange"))
            st = webhooks_mod.status()
            assert "vigilance-orange" in st["active_cooldowns"]
            remain = st["active_cooldowns"]["vigilance-orange"]
            assert 0 < remain <= 900
        finally:
            loop.close()


# ---------- Module: _send_discord / _send_telegram error capture ----------
class TestSendErrors:
    def test_send_discord_invalid_token_captures_error(self, monkeypatch, webhooks_mod):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/999999/invalidtoken")
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(webhooks_mod._send_discord("t", "b", "test"))
            assert r is not None
            assert r.get("ok") is False
            # Either status from Discord (401/404) or transport error
            assert "status" in r or "error" in r
        finally:
            loop.close()

    def test_send_telegram_invalid_token_captures_error(self, monkeypatch, webhooks_mod):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:fake-invalid-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999999")
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(webhooks_mod._send_telegram("t", "b", "test"))
            assert r is not None
            assert r.get("ok") is False
            assert "status" in r or "error" in r
        finally:
            loop.close()


# ---------- Module: dispatch signature compatibility with all watcher tags ----------
class TestDispatchTags:
    @pytest.mark.parametrize("tag", [
        "storm-active", "lightning-strike", "storm-approach",
        "vigilance-orange", "vigilance-rouge",
    ])
    def test_dispatch_each_alert_tag(self, monkeypatch, webhooks_mod, tag):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(webhooks_mod.dispatch("Title", "Body", tag, force=True))
            assert r.get("tag") == tag
            assert "skipped" not in r
            assert r.get("discord") is None
            assert r.get("telegram") is None
        finally:
            loop.close()


# ---------- Regression: existing endpoints still work ----------
class TestRegressions:
    def test_push_test_requires_auth(self, api):
        r = api.post(f"{BASE_URL}/api/push/test")
        assert r.status_code in (401, 403)

    def test_push_test_with_auth(self, api, auth_token):
        r = api.post(f"{BASE_URL}/api/push/test",
                     headers={"Authorization": f"Bearer {auth_token}"})
        assert r.status_code == 200
        d = r.json()
        # send_to_all returns {"sent":..., "failed":..., ...}
        assert isinstance(d, dict)

    def test_replay_events(self, api):
        r = api.get(f"{BASE_URL}/api/replay/events")
        assert r.status_code == 200
        d = r.json()
        assert "events" in d
        assert isinstance(d["events"], list)

    def test_replay_video_validation(self, api):
        # No demo + no strikes should give 400 (not 500)
        r = api.post(f"{BASE_URL}/api/replay/video",
                     json={"start_ts": 0, "end_ts": 1})
        assert r.status_code in (400, 404, 422)

    def test_weather_vigilance(self, api):
        r = api.get(f"{BASE_URL}/api/weather/vigilance")
        assert r.status_code == 200
        d = r.json()
        # Should have departements and overall_level
        assert "departements" in d or "overall_level" in d or "degraded" in d

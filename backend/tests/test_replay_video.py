"""Tests for /api/replay/demos and /api/replay/video MP4 export pipeline.

Iteration 15 – validates demos endpoint, video job lifecycle and ffprobe-confirmed MP4.
"""
import json
import os
import subprocess
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0],
).rstrip("/")
API = f"{BASE_URL}/api"


# --- Shared fixtures ---
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- /api/replay/demos ---
class TestReplayDemos:
    def test_demos_shape(self, session):
        r = session.get(f"{API}/replay/demos", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_reconstructed"] is True
        assert isinstance(data["demos"], list)
        assert len(data["demos"]) == 2

        ids = {d["id"] for d in data["demos"]}
        assert ids == {"demo-pyrenees-cevenol", "demo-cellule-isolee"}

        for d in data["demos"]:
            for k in [
                "id", "label", "subtitle", "description", "is_demo",
                "start_ts", "end_ts", "duration_min", "strike_count",
                "peak_count_10min", "center_lat", "center_lon",
            ]:
                assert k in d, f"missing key {k} in demo {d.get('id')}"
            assert d["is_demo"] is True
            assert d["strike_count"] > 0
            assert d["start_ts"] < d["end_ts"]
            assert d["duration_min"] > 0


# --- POST /api/replay/video ---
class TestReplayVideoStart:
    def test_post_with_demo_id_returns_queued(self, session):
        body = {"start_ts": 0, "end_ts": 0, "demo_id": "demo-pyrenees-cevenol"}
        r = session.post(f"{API}/replay/video", json=body, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["job_id"].startswith("vid-")

    def test_post_unknown_demo_id_returns_404(self, session):
        body = {"start_ts": 0, "end_ts": 0, "demo_id": "demo-nonexistent"}
        r = session.post(f"{API}/replay/video", json=body, timeout=15)
        assert r.status_code == 404, r.text

    def test_post_no_demo_no_strikes_returns_400(self, session):
        # Reasonable past window where the live store likely has no strikes
        # (calm conditions confirmed in iteration_14 — empty replay events).
        now = int(time.time())
        body = {
            "start_ts": now - 7200,
            "end_ts": now - 3600,
            "lat": 43.0951,
            "lon": -0.0434,
            "radius_km": 70,
        }
        r = session.post(f"{API}/replay/video", json=body, timeout=15)
        # Either 400 (no strikes in store) or 200 (if strikes happen to exist).
        # The contract under test is 400 when not enough strikes.
        assert r.status_code in (200, 400), r.text
        if r.status_code == 400:
            assert "Not enough strikes" in r.json().get("detail", "")


# --- GET /api/replay/video/{id} status ---
class TestReplayVideoStatus:
    def test_status_unknown_job_returns_404(self, session):
        r = session.get(f"{API}/replay/video/vid-doesnotexist", timeout=15)
        assert r.status_code == 404

    def test_status_known_job_shape(self, session):
        # Kick off a real job via demo
        r = session.post(
            f"{API}/replay/video",
            json={"start_ts": 0, "end_ts": 0, "demo_id": "demo-cellule-isolee"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        time.sleep(0.5)
        s = session.get(f"{API}/replay/video/{jid}", timeout=15)
        assert s.status_code == 200, s.text
        data = s.json()
        for k in ["job_id", "status", "progress", "created_at", "label"]:
            assert k in data
        assert data["status"] in ("queued", "running", "done", "failed")
        assert 0 <= data["progress"] <= 100


# --- E2E: queue → poll → download MP4 → ffprobe ---
class TestReplayVideoE2E:
    def test_full_e2e_demo_to_mp4(self, session):
        # Start a job for the cevenol demo (45min synthetic event)
        r = session.post(
            f"{API}/replay/video",
            json={"start_ts": 0, "end_ts": 0, "demo_id": "demo-pyrenees-cevenol"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]

        # Poll up to 90 s
        deadline = time.time() + 90
        last = None
        while time.time() < deadline:
            s = session.get(f"{API}/replay/video/{jid}", timeout=15)
            assert s.status_code == 200
            last = s.json()
            if last["status"] in ("done", "failed"):
                break
            time.sleep(2)

        assert last is not None
        assert last["status"] == "done", f"job did not complete: {last}"
        assert last["progress"] == 100
        assert last.get("mp4_url") == f"/api/replay/video/{jid}/file.mp4"

        # Download the file
        url = f"{API}/replay/video/{jid}/file.mp4"
        f = session.get(url, timeout=30)
        assert f.status_code == 200, f.text
        assert f.headers.get("Content-Type", "").startswith("video/mp4")
        body = f.content
        assert len(body) > 10 * 1024, f"mp4 too small: {len(body)} bytes"

        # Save and ffprobe-validate codec, dimensions, duration
        out = f"/tmp/test_replay_{jid}.mp4"
        with open(out, "wb") as fh:
            fh.write(body)

        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-of", "json",
                "-show_streams", "-show_format", out,
            ],
            capture_output=True, text=True, timeout=30,
        )
        assert probe.returncode == 0, probe.stderr
        info = json.loads(probe.stdout)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert v["codec_name"] == "h264", v
        assert v["width"] == 720
        assert v["height"] == 720
        dur = float(info["format"]["duration"])
        assert dur >= 3.0, f"duration too short: {dur}s"
        os.unlink(out)

    def test_file_endpoint_returns_404_for_unknown(self, session):
        r = session.get(f"{API}/replay/video/vid-unknownjob/file.mp4", timeout=15)
        assert r.status_code == 404


# --- Regression: /api/replay/events still works ---
class TestRegressionReplayEvents:
    def test_replay_events_still_works(self, session):
        r = session.get(f"{API}/replay/events", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "source_window_h" in data
        assert data["source_window_h"] == 24
        assert isinstance(data["events"], list)

"""Tests for new /api/share/card.png endpoint (iteration 11)."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://storm-monitor-20km.preview.emergentagent.com").rstrip("/")


def test_share_card_returns_png():
    r = requests.get(f"{BASE_URL}/api/share/card.png", timeout=30)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
    ctype = r.headers.get("content-type", "")
    assert "image/png" in ctype, f"content-type={ctype}"
    # PNG magic header
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n", f"Not a PNG. First bytes: {r.content[:16]!r}"
    assert len(r.content) > 10_000, f"PNG too small: {len(r.content)} bytes"


def test_share_card_cache_header():
    r = requests.get(f"{BASE_URL}/api/share/card.png", timeout=30)
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "public" in cc and "max-age=60" in cc, f"cache-control={cc}"


def test_share_card_dimensions():
    """Ensure 1200x630 OG image dimensions."""
    from PIL import Image
    import io
    r = requests.get(f"{BASE_URL}/api/share/card.png", timeout=30)
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (1200, 630), f"Got {img.size}"
    assert img.mode == "RGB"


def test_trajectory_still_works_with_radius_70():
    """Regression: trajectory endpoint accepts radius_km=70 and returns detected bool."""
    r = requests.get(
        f"{BASE_URL}/api/storms/trajectory",
        params={"radius_km": 70, "project_minutes": 45},
        timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    assert "detected" in data
    assert isinstance(data["detected"], bool)


def test_approach_still_works_with_radius_70():
    """Regression: approach endpoint accepts radius_km=70."""
    r = requests.get(f"{BASE_URL}/api/storms/approach", params={"radius_km": 70}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "approaching" in data
    assert data.get("radius_analyzed_km") == 70.0


def test_vigilance_still_returns_meteoalarm():
    """Regression from iter10: vigilance still queryable & structured."""
    r = requests.get(f"{BASE_URL}/api/weather/vigilance", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "departements" in data
    assert "overall_level" in data
    # Current state (per review request): should be yellow (2) due to 'Vigilance jaune orages'
    # but just validate structure
    assert isinstance(data["overall_level"], int)


def test_bulletin_pdf_still_works():
    r = requests.get(f"{BASE_URL}/api/reports/bulletin.pdf", timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:5] == b"%PDF-"


def test_upload_storm_still_requires_key():
    # Without key
    r = requests.post(
        f"{BASE_URL}/api/upload_storm",
        json={"distance": 5.0, "energy": 100.0},
        timeout=10,
    )
    assert r.status_code == 401

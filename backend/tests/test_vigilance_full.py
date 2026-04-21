"""
Backend API tests for /api/weather/vigilance/full (Iteration 12)
Tests: full France + Andorra vigilance (MeteoAlarm), shape, dept 65 jaune,
Andorra presence, INSEE->NUTS3 mapping, regression on original /vigilance.
"""
import os
import time
import pytest
import requests

def _load_backend_url():
    url = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
    if url:
        return url
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip().rstrip('/')
    except Exception:
        pass
    return ''

BASE_URL = _load_backend_url()


@pytest.fixture(scope="module")
def full_data():
    r = requests.get(f"{BASE_URL}/api/weather/vigilance/full", timeout=30)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    return r.json()


class TestVigilanceFullShape:
    """Top-level structure of /api/weather/vigilance/full"""

    def test_top_level_keys(self, full_data):
        for k in ["updated_at", "source", "source_label", "source_url", "disclaimer",
                  "phenomena_meta", "levels_meta", "areas",
                  "overall_level", "overall_level_fr", "overall_color", "overall_label"]:
            assert k in full_data, f"Missing key: {k}"

    def test_source_is_meteoalarm(self, full_data):
        assert full_data["source"] == "meteoalarm", f"source={full_data['source']}"

    def test_areas_count_at_least_100(self, full_data):
        # 96 metro depts + 5 DOM + Andorra = 102
        assert len(full_data["areas"]) >= 100, f"areas={len(full_data['areas'])}"

    def test_area_fields(self, full_data):
        for a in full_data["areas"][:5]:
            for k in ["id", "name", "country", "max_level", "max_level_fr", "phenomena"]:
                assert k in a, f"Area missing key {k}: {a}"
            assert 1 <= a["max_level"] <= 4
            assert a["max_level_fr"] in ("vert", "jaune", "orange", "rouge")


class TestHautesPyrenees:
    """Hautes-Pyrenees (id=65) specific checks"""

    def test_dept_65_present(self, full_data):
        d65 = next((a for a in full_data["areas"] if a.get("id") == "65"), None)
        assert d65 is not None, "Dept 65 missing"
        assert d65["country"] == "FR"

    def test_dept_65_yellow_for_orages(self, full_data):
        d65 = next((a for a in full_data["areas"] if a.get("id") == "65"), None)
        assert d65 is not None
        # Live feed currently shows jaune for orages
        orage = next((p for p in d65["phenomena"] if p["key"] == "orage"), None)
        assert orage is not None, "No 'orage' phenomenon for dept 65"
        # Live expectation per task: level=2 (jaune)
        assert orage["level"] == 2, f"Expected jaune (2) for dept 65 orages, got {orage['level']}"
        assert orage["level_fr"] == "jaune"
        assert orage["color"] == "#F59E0B"
        assert d65["max_level"] == 2


class TestAndorra:
    """Andorra (id=AD) via feeds-andorra"""

    def test_andorra_present(self, full_data):
        ad = next((a for a in full_data["areas"] if a.get("id") == "AD"), None)
        assert ad is not None, "Andorra missing from areas"
        assert ad["country"] == "AD"
        assert ad["name"] in ("Andorre", "Andorra", "Principat d'Andorra") or "ndor" in ad["name"]

    def test_andorra_has_phenomena(self, full_data):
        ad = next((a for a in full_data["areas"] if a.get("id") == "AD"), None)
        assert ad is not None
        assert isinstance(ad["phenomena"], list)
        assert len(ad["phenomena"]) >= 1
        assert 1 <= ad["max_level"] <= 4


class TestInseeNuts3Mapping:
    """INSEE -> NUTS3 mapping correctness"""

    def test_known_insee_to_nuts3(self):
        import sys
        sys.path.insert(0, '/app/backend')
        import vigilance as v
        expected = {
            "09": "FR621",   # Ariège
            "65": "FR626",   # Hautes-Pyrénées
            "33": "FR612",   # Gironde
            "31": "FR623",   # Haute-Garonne
            "64": "FR615",   # Pyrénées-Atlantiques
            "66": "FR815",   # Pyrénées-Orientales
        }
        for insee, nuts in expected.items():
            assert v.INSEE_TO_NUTS3.get(insee) == nuts, \
                f"INSEE {insee} -> {v.INSEE_TO_NUTS3.get(insee)}, expected {nuts}"

    def test_insee_mapping_length(self):
        import sys
        sys.path.insert(0, '/app/backend')
        import vigilance as v
        # 96 metro + 5 DOM = 101
        assert len(v.INSEE_TO_NUTS3) >= 96


class TestVigilanceRegression:
    """Original /api/weather/vigilance still works"""

    def test_original_endpoint_still_works(self):
        r = requests.get(f"{BASE_URL}/api/weather/vigilance", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "departements" in data
        assert len(data["departements"]) == 7
        dept_ids = sorted([d["id"] for d in data["departements"]])
        assert dept_ids == ["09", "31", "32", "40", "64", "65", "66"]


class TestVigilanceFullCached:
    """Cache TTL 15 min"""

    def test_second_call_fast(self):
        requests.get(f"{BASE_URL}/api/weather/vigilance/full", timeout=30)  # warm
        start = time.time()
        r = requests.get(f"{BASE_URL}/api/weather/vigilance/full", timeout=30)
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 2.0, f"Cached took {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

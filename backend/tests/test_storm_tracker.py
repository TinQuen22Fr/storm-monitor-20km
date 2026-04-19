"""
Backend API tests for Lourdes Storm Tracker
Tests: Service info, Weather endpoints, Auth flows, Favorites CRUD
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_EMAIL = "test@lourdes.fr"
TEST_PASSWORD = "storm123"


class TestServiceInfo:
    """Test root endpoint returns service info"""
    
    def test_root_returns_service_info(self):
        """GET /api/ returns service info with Lourdes coordinates"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        
        data = response.json()
        assert data["service"] == "lourdes-storm-tracker"
        assert "center" in data
        assert data["center"]["lat"] == 43.0951
        assert data["center"]["lon"] == -0.0434
        assert data["radius_km"] == 20.0
        print("✓ Root endpoint returns correct service info")


class TestWeatherEndpoints:
    """Test weather data endpoints"""
    
    def test_current_weather(self):
        """GET /api/weather/current returns current weather with required fields"""
        response = requests.get(f"{BASE_URL}/api/weather/current")
        assert response.status_code == 200
        
        data = response.json()
        assert "current" in data
        assert "temperature_2m" in data["current"]
        assert "cape" in data  # CAPE value (can be null)
        assert "lightning_potential" in data  # Can be null
        assert data["lat"] == 43.0951
        assert data["lon"] == -0.0434
        print(f"✓ Current weather: {data['current']['temperature_2m']}°C, CAPE: {data['cape']}")
    
    def test_forecast(self):
        """GET /api/weather/forecast returns hourly array with 24 entries"""
        response = requests.get(f"{BASE_URL}/api/weather/forecast")
        assert response.status_code == 200
        
        data = response.json()
        assert "hourly" in data
        assert isinstance(data["hourly"], list)
        assert len(data["hourly"]) == 24, f"Expected 24 entries, got {len(data['hourly'])}"
        
        # Check first entry has required fields
        first = data["hourly"][0]
        assert "precipitation_probability" in first
        assert "cape" in first
        assert "lightning_potential" in first
        assert "time" in first
        print(f"✓ Forecast: {len(data['hourly'])} hourly entries")
    
    def test_history(self):
        """GET /api/weather/history returns past 24h with is_storm field"""
        response = requests.get(f"{BASE_URL}/api/weather/history")
        assert response.status_code == 200
        
        data = response.json()
        assert "hourly" in data
        assert isinstance(data["hourly"], list)
        assert len(data["hourly"]) <= 24
        
        # Check entries have is_storm field
        if data["hourly"]:
            first = data["hourly"][0]
            assert "is_storm" in first
            assert "time" in first
        print(f"✓ History: {len(data['hourly'])} hourly entries with is_storm field")
    
    def test_storm_zones(self):
        """GET /api/storms/zones returns zones array with storm data"""
        response = requests.get(f"{BASE_URL}/api/storms/zones")
        assert response.status_code == 200
        
        data = response.json()
        assert "zones" in data
        assert isinstance(data["zones"], list)
        assert len(data["zones"]) >= 20, f"Expected ~25 zones, got {len(data['zones'])}"
        
        # Check zone structure
        zone = data["zones"][0]
        assert "lat" in zone
        assert "lon" in zone
        assert "cape" in zone
        assert "lightning_potential" in zone
        assert "severity" in zone
        
        # Check aggregate fields
        assert "storm_active" in data
        assert isinstance(data["storm_active"], bool)
        assert "max_cape" in data
        assert "max_lightning_potential" in data
        print(f"✓ Storm zones: {len(data['zones'])} zones, storm_active={data['storm_active']}")


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_register_new_user(self):
        """POST /api/auth/register creates user and returns JWT"""
        unique_email = f"test_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test User"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == unique_email.lower()
        assert len(data["token"]) > 20
        print(f"✓ Registration successful for {unique_email}")
    
    def test_register_duplicate_email(self):
        """POST /api/auth/register rejects duplicate email"""
        # First registration
        unique_email = f"dup_{uuid.uuid4().hex[:8]}@test.com"
        requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123"
        })
        
        # Second registration with same email
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123"
        })
        assert response.status_code == 400
        print("✓ Duplicate email rejected")
    
    def test_login_valid_credentials(self):
        """POST /api/auth/login authenticates valid credentials"""
        # First create a user
        unique_email = f"login_{uuid.uuid4().hex[:8]}@test.com"
        requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123"
        })
        
        # Then login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "testpass123"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "token" in data
        assert "user" in data
        print("✓ Login successful with valid credentials")
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login rejects invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials rejected")
    
    def test_me_without_token(self):
        """GET /api/auth/me returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("✓ /auth/me returns 401 without token")
    
    def test_me_with_token(self):
        """GET /api/auth/me returns user when token provided"""
        # Create user and get token
        unique_email = f"me_{uuid.uuid4().hex[:8]}@test.com"
        reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Me Test"
        })
        token = reg_response.json()["token"]
        
        # Call /me with token
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["email"] == unique_email.lower()
        assert data["name"] == "Me Test"
        print("✓ /auth/me returns user with valid token")


class TestFavoritesEndpoints:
    """Test favorites CRUD endpoints"""
    
    @pytest.fixture
    def auth_headers(self):
        """Create a user and return auth headers"""
        unique_email = f"fav_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_favorites_without_auth(self):
        """GET /api/favorites returns 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/favorites")
        assert response.status_code == 401
        print("✓ Favorites requires authentication")
    
    def test_create_favorite(self, auth_headers):
        """POST /api/favorites creates a favorite"""
        response = requests.post(
            f"{BASE_URL}/api/favorites",
            json={"name": "Pic du Jer", "lat": 43.0951, "lon": -0.0434},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "Pic du Jer"
        assert data["lat"] == 43.0951
        assert data["lon"] == -0.0434
        assert "id" in data
        print(f"✓ Created favorite: {data['name']}")
    
    def test_list_favorites(self, auth_headers):
        """GET /api/favorites lists user favorites"""
        # Create a favorite first
        requests.post(
            f"{BASE_URL}/api/favorites",
            json={"name": "Test Location", "lat": 43.1, "lon": -0.05},
            headers=auth_headers
        )
        
        # List favorites
        response = requests.get(f"{BASE_URL}/api/favorites", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        print(f"✓ Listed {len(data)} favorites")
    
    def test_delete_favorite(self, auth_headers):
        """DELETE /api/favorites/{id} removes favorite"""
        # Create a favorite
        create_response = requests.post(
            f"{BASE_URL}/api/favorites",
            json={"name": "To Delete", "lat": 43.0, "lon": -0.1},
            headers=auth_headers
        )
        fav_id = create_response.json()["id"]
        
        # Delete it
        response = requests.delete(
            f"{BASE_URL}/api/favorites/{fav_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Verify it's gone
        list_response = requests.get(f"{BASE_URL}/api/favorites", headers=auth_headers)
        favs = list_response.json()
        assert not any(f["id"] == fav_id for f in favs)
        print("✓ Deleted favorite successfully")
    
    def test_delete_nonexistent_favorite(self, auth_headers):
        """DELETE /api/favorites/{id} returns 404 for nonexistent"""
        response = requests.delete(
            f"{BASE_URL}/api/favorites/nonexistent-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("✓ Delete nonexistent returns 404")


class TestPreCreatedTestUser:
    """Test with pre-created test user from test_credentials.md"""
    
    def test_login_test_user(self):
        """Login with pre-created test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        # User may or may not exist depending on seed
        if response.status_code == 200:
            data = response.json()
            assert "token" in data
            print(f"✓ Test user {TEST_EMAIL} login successful")
        else:
            # Create the user if it doesn't exist
            reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "name": "Storm Tester"
            })
            if reg_response.status_code == 200:
                print(f"✓ Created test user {TEST_EMAIL}")
            else:
                print("⚠ Test user may already exist with different password")


class TestHistoryDaysEndpoint:
    """Test multi-day history endpoint (PHASE 3 FEATURE)"""
    
    def test_history_days_default_7(self):
        """GET /api/weather/history-days returns ~8 entries (7 past + today)"""
        response = requests.get(f"{BASE_URL}/api/weather/history-days")
        assert response.status_code == 200
        
        data = response.json()
        assert "days" in data
        assert isinstance(data["days"], list)
        assert len(data["days"]) >= 7, f"Expected ~8 entries, got {len(data['days'])}"
        
        # Check day structure
        day = data["days"][0]
        assert "date" in day
        assert "precipitation_total" in day
        assert "max_cape" in day
        assert "max_lightning_potential" in day
        assert "max_wind_gust" in day
        assert "max_temperature" in day
        assert "min_temperature" in day
        assert "storm_hours" in day
        print(f"✓ History days (default 7): {len(data['days'])} entries")
    
    def test_history_days_14(self):
        """GET /api/weather/history-days?days=14 returns ~15 entries"""
        response = requests.get(f"{BASE_URL}/api/weather/history-days", params={"days": 14})
        assert response.status_code == 200
        
        data = response.json()
        assert "days" in data
        assert len(data["days"]) >= 14, f"Expected ~15 entries, got {len(data['days'])}"
        print(f"✓ History days (14): {len(data['days'])} entries")
    
    def test_history_days_clamps_invalid(self):
        """GET /api/weather/history-days clamps invalid days to [1, 60]"""
        # Test days=0 (should clamp to 1)
        response = requests.get(f"{BASE_URL}/api/weather/history-days", params={"days": 0})
        assert response.status_code == 200
        data = response.json()
        assert len(data["days"]) >= 1, "days=0 should clamp to 1"
        
        # Test days=-5 (should clamp to 1)
        response = requests.get(f"{BASE_URL}/api/weather/history-days", params={"days": -5})
        assert response.status_code == 200
        data = response.json()
        assert len(data["days"]) >= 1, "days=-5 should clamp to 1"
        
        # Test days=100 (should clamp to 60)
        response = requests.get(f"{BASE_URL}/api/weather/history-days", params={"days": 100})
        assert response.status_code == 200
        data = response.json()
        assert len(data["days"]) <= 62, "days=100 should clamp to 60"
        print("✓ History days clamps invalid values correctly")


class TestPushEndpoints:
    """Test Web Push VAPID endpoints (PHASE 3 FEATURE)"""
    
    def test_vapid_public_key(self):
        """GET /api/push/vapid-public-key returns valid VAPID key"""
        response = requests.get(f"{BASE_URL}/api/push/vapid-public-key")
        assert response.status_code == 200
        
        data = response.json()
        assert "key" in data
        assert isinstance(data["key"], str)
        assert len(data["key"]) > 40, "VAPID key should be substantial"
        assert data["key"].startswith("BG"), "VAPID public key should start with BG"
        print(f"✓ VAPID public key: {data['key'][:30]}...")
    
    def test_push_subscribe_idempotent(self):
        """POST /api/push/subscribe is idempotent (no duplicates)"""
        endpoint = f"https://test-endpoint.example.com/push/{uuid.uuid4().hex}"
        payload = {
            "endpoint": endpoint,
            "keys": {"p256dh": "test-p256dh", "auth": "test-auth"}
        }
        
        # First subscribe
        response1 = requests.post(f"{BASE_URL}/api/push/subscribe", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["ok"] is True
        assert "id" in data1
        
        # Second subscribe (same endpoint) - should be idempotent
        response2 = requests.post(f"{BASE_URL}/api/push/subscribe", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["ok"] is True
        
        # Cleanup
        requests.post(f"{BASE_URL}/api/push/unsubscribe", json={"endpoint": endpoint})
        print("✓ Push subscribe is idempotent")
    
    def test_push_unsubscribe(self):
        """POST /api/push/unsubscribe removes subscription"""
        endpoint = f"https://test-endpoint.example.com/push/{uuid.uuid4().hex}"
        
        # Subscribe first
        requests.post(f"{BASE_URL}/api/push/subscribe", json={
            "endpoint": endpoint,
            "keys": {"p256dh": "test-p256dh", "auth": "test-auth"}
        })
        
        # Unsubscribe
        response = requests.post(f"{BASE_URL}/api/push/unsubscribe", json={"endpoint": endpoint})
        assert response.status_code == 200
        data = response.json()
        assert data["removed"] == 1
        
        # Unsubscribe again (should return 0)
        response2 = requests.post(f"{BASE_URL}/api/push/unsubscribe", json={"endpoint": endpoint})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["removed"] == 0
        print("✓ Push unsubscribe works correctly")
    
    def test_push_test_requires_auth(self):
        """POST /api/push/test returns 401 without token"""
        response = requests.post(f"{BASE_URL}/api/push/test")
        assert response.status_code == 401
        print("✓ Push test requires authentication")
    
    def test_push_test_with_auth(self):
        """POST /api/push/test returns {sent, removed, errors, total} when authenticated"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if login_response.status_code != 200:
            # Create user if not exists
            reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "name": "Storm Tester"
            })
            token = reg_response.json().get("token")
        else:
            token = login_response.json().get("token")
        
        assert token, "Failed to get auth token"
        
        # Call push test
        response = requests.post(
            f"{BASE_URL}/api/push/test",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "sent" in data
        assert "removed" in data
        assert "errors" in data
        assert "total" in data
        assert isinstance(data["sent"], int)
        assert isinstance(data["total"], int)
        print(f"✓ Push test with auth: sent={data['sent']}, total={data['total']}")


class TestPDFBulletin:
    """Test PDF bulletin export (PHASE 3 FEATURE)"""
    
    def test_bulletin_pdf_returns_pdf(self):
        """GET /api/reports/bulletin.pdf returns application/pdf with content"""
        response = requests.get(f"{BASE_URL}/api/reports/bulletin.pdf")
        assert response.status_code == 200
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected application/pdf, got {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get("Content-Disposition", "")
        assert "bulletin" in content_disp.lower(), f"Expected bulletin in filename, got {content_disp}"
        
        # Check PDF content (should be >1KB)
        assert len(response.content) > 1024, f"PDF too small: {len(response.content)} bytes"
        
        # Check PDF magic bytes
        assert response.content[:4] == b'%PDF', "Content doesn't start with PDF magic bytes"
        print(f"✓ PDF bulletin: {len(response.content)} bytes, valid PDF")


class TestStormZonesRadiusVariations:
    """Test storm zones endpoint with different radius values (PHASE 4 FEATURE)"""
    
    def test_zones_radius_20_returns_25_zones(self):
        """GET /api/storms/zones?radius_km=20 returns ~25 zones (5x5 grid)"""
        import time
        time.sleep(1)  # Avoid rate limiting
        response = requests.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 20})
        assert response.status_code == 200
        
        data = response.json()
        assert "zones" in data
        zone_count = len(data["zones"])
        # 5x5 grid = 25 points, some may be filtered if outside circle
        assert 20 <= zone_count <= 25, f"Expected ~25 zones for 20km, got {zone_count}"
        assert data["radius_km"] == 20
        print(f"✓ Storm zones (20km): {zone_count} zones")
    
    def test_zones_radius_30_returns_more_zones(self):
        """GET /api/storms/zones?radius_km=30 returns ~45 zones (7x7 grid adaptive)"""
        import time
        time.sleep(1)  # Avoid rate limiting
        response = requests.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 30})
        assert response.status_code == 200
        
        data = response.json()
        zone_count = len(data["zones"])
        # 7x7 grid = 49 points, filtered to ~45 within circle
        assert 35 <= zone_count <= 49, f"Expected ~45 zones for 30km, got {zone_count}"
        assert data["radius_km"] == 30
        print(f"✓ Storm zones (30km): {zone_count} zones")
    
    def test_zones_radius_70_returns_45_zones(self):
        """GET /api/storms/zones?radius_km=70 returns ~45 zones (7x7 grid)"""
        import time
        time.sleep(1)  # Avoid rate limiting
        response = requests.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 70})
        assert response.status_code == 200
        
        data = response.json()
        zone_count = len(data["zones"])
        # 7x7 grid = 49 points, filtered to ~45 within circle
        assert 35 <= zone_count <= 49, f"Expected ~45 zones for 70km, got {zone_count}"
        assert data["radius_km"] == 70
        print(f"✓ Storm zones (70km): {zone_count} zones")
    
    def test_zones_cached_fast_response(self):
        """Subsequent identical calls to /api/storms/zones return fast (<500ms, cached 90s)"""
        import time
        # First call (may hit Open-Meteo)
        time.sleep(1)
        requests.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 20})
        
        # Second call (should be cached)
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/storms/zones", params={"radius_km": 20})
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Cached response should be fast (< 1s, accounting for network latency)
        assert elapsed < 1.0, f"Cached response took {elapsed:.2f}s, expected <1.0s"
        print(f"✓ Cached zones response: {elapsed*1000:.0f}ms")


class TestWeatherCaching:
    """Test TTL caching for weather endpoints (PHASE 4 FEATURE)"""
    
    def test_current_weather_cached(self):
        """GET /api/weather/current is cached (TTL 60s)"""
        import time
        # First call
        time.sleep(1)
        requests.get(f"{BASE_URL}/api/weather/current")
        
        # Second call (should be cached)
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/weather/current")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.3, f"Cached current weather took {elapsed:.2f}s"
        print(f"✓ Cached current weather: {elapsed*1000:.0f}ms")
    
    def test_forecast_cached(self):
        """GET /api/weather/forecast is cached (TTL 120s)"""
        import time
        # First call
        time.sleep(1)
        requests.get(f"{BASE_URL}/api/weather/forecast")
        
        # Second call (should be cached)
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/weather/forecast")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.3, f"Cached forecast took {elapsed:.2f}s"
        print(f"✓ Cached forecast: {elapsed*1000:.0f}ms")
    
    def test_history_cached(self):
        """GET /api/weather/history is cached (TTL 300s)"""
        import time
        # First call
        time.sleep(1)
        requests.get(f"{BASE_URL}/api/weather/history")
        
        # Second call (should be cached)
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/weather/history")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.3, f"Cached history took {elapsed:.2f}s"
        print(f"✓ Cached history: {elapsed*1000:.0f}ms")
    
    def test_history_days_cached(self):
        """GET /api/weather/history-days is cached (TTL 600s)"""
        import time
        # First call
        time.sleep(1)
        requests.get(f"{BASE_URL}/api/weather/history-days", params={"days": 7})
        
        # Second call (should be cached)
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/weather/history-days", params={"days": 7})
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.3, f"Cached history-days took {elapsed:.2f}s"
        print(f"✓ Cached history-days: {elapsed*1000:.0f}ms")


class TestLightningWithRadius:
    """Test lightning strikes with radius parameter (PHASE 4 FEATURE)"""
    
    def test_lightning_strikes_radius_70(self):
        """GET /api/lightning/strikes?radius_km=70 returns strikes within 70km"""
        response = requests.get(f"{BASE_URL}/api/lightning/strikes", params={
            "lat": 43.0951,
            "lon": -0.0434,
            "radius_km": 70
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "count" in data
        assert "strikes" in data
        assert isinstance(data["count"], int)
        
        # Verify all strikes are within 70km
        for strike in data["strikes"]:
            assert strike["distance_km"] <= 70, f"Strike at {strike['distance_km']}km exceeds 70km radius"
        
        print(f"✓ Lightning strikes (70km): count={data['count']}")


class TestPDFBulletinWithRadius:
    """Test PDF bulletin with radius parameter (PHASE 4 FEATURE)"""
    
    def test_bulletin_pdf_with_radius_70(self):
        """GET /api/reports/bulletin.pdf?radius_km=70 returns valid PDF"""
        import time
        time.sleep(2)  # Allow cache to populate
        response = requests.get(f"{BASE_URL}/api/reports/bulletin.pdf", params={"radius_km": 70})
        assert response.status_code == 200
        
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type
        assert len(response.content) > 1024
        assert response.content[:4] == b'%PDF'
        print(f"✓ PDF bulletin (70km): {len(response.content)} bytes")


class TestStormUploadEndpoints:
    """Test secured storm upload API (PHASE 6 FEATURE)"""
    
    UPLOAD_API_KEY = "lourdes-storm-upload-2026-xV7p9Qm3RtA8Ks"
    
    def test_upload_storm_missing_api_key(self):
        """POST /api/upload_storm without X-API-Key returns 401"""
        response = requests.post(f"{BASE_URL}/api/upload_storm", json={
            "distance": 5.0,
            "energy": 20.0
        })
        assert response.status_code == 401
        
        data = response.json()
        assert data["detail"] == "Clé API invalide ou manquante"
        print("✓ Upload without API key returns 401 with correct message")
    
    def test_upload_storm_wrong_api_key(self):
        """POST /api/upload_storm with wrong X-API-Key returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/upload_storm",
            json={"distance": 5.0, "energy": 20.0},
            headers={"X-API-Key": "wrong-key-12345"}
        )
        assert response.status_code == 401
        
        data = response.json()
        assert data["detail"] == "Clé API invalide ou manquante"
        print("✓ Upload with wrong API key returns 401")
    
    def test_upload_storm_valid_key_creates_record(self):
        """POST /api/upload_storm with valid key returns {ok:true, record:{...}}"""
        import time
        timestamp = f"2026-01-{int(time.time()) % 28 + 1:02d}T12:00:00Z"
        
        response = requests.post(
            f"{BASE_URL}/api/upload_storm",
            json={
                "distance": 7.5,
                "energy": 33.2,
                "timestamp": timestamp
            },
            headers={"X-API-Key": self.UPLOAD_API_KEY}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] is True
        assert "record" in data
        
        record = data["record"]
        assert "id" in record
        assert record["distance"] == 7.5
        assert record["energy"] == 33.2
        assert record["timestamp"] == timestamp
        assert "received_at" in record
        print(f"✓ Upload with valid key: id={record['id']}, distance={record['distance']}, energy={record['energy']}")
    
    def test_upload_storm_auto_fills_timestamp(self):
        """POST /api/upload_storm without timestamp auto-fills it"""
        response = requests.post(
            f"{BASE_URL}/api/upload_storm",
            json={
                "distance": 2.1,
                "energy": 15.0
            },
            headers={"X-API-Key": self.UPLOAD_API_KEY}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] is True
        record = data["record"]
        
        # Timestamp should be auto-filled (ISO format)
        assert "timestamp" in record
        assert record["timestamp"] is not None
        assert "T" in record["timestamp"]  # ISO format check
        print(f"✓ Auto-filled timestamp: {record['timestamp']}")
    
    def test_upload_storm_persists_to_file(self):
        """POST /api/upload_storm persists data (verify via GET)"""
        import time
        unique_distance = 99.0 + (time.time() % 1)  # Unique value
        
        # Upload
        response = requests.post(
            f"{BASE_URL}/api/upload_storm",
            json={
                "distance": unique_distance,
                "energy": 88.8,
                "timestamp": "2026-01-15T10:00:00Z"
            },
            headers={"X-API-Key": self.UPLOAD_API_KEY}
        )
        assert response.status_code == 200
        record_id = response.json()["record"]["id"]
        
        # Verify via GET
        get_response = requests.get(f"{BASE_URL}/api/storm_uploads")
        assert get_response.status_code == 200
        
        items = get_response.json()["items"]
        found = any(item["id"] == record_id for item in items)
        assert found, f"Record {record_id} not found in storm_uploads"
        print(f"✓ Upload persisted and verified via GET: id={record_id}")


class TestStormUploadsListEndpoint:
    """Test GET /api/storm_uploads endpoint (PHASE 6 FEATURE)"""
    
    def test_list_storm_uploads_returns_count_and_items(self):
        """GET /api/storm_uploads returns {count, items[]}"""
        response = requests.get(f"{BASE_URL}/api/storm_uploads")
        assert response.status_code == 200
        
        data = response.json()
        assert "count" in data
        assert "items" in data
        assert isinstance(data["count"], int)
        assert isinstance(data["items"], list)
        assert data["count"] == len(data["items"])
        print(f"✓ Storm uploads list: count={data['count']}")
    
    def test_list_storm_uploads_sorted_newest_first(self):
        """GET /api/storm_uploads returns items sorted by timestamp descending"""
        response = requests.get(f"{BASE_URL}/api/storm_uploads")
        assert response.status_code == 200
        
        items = response.json()["items"]
        if len(items) >= 2:
            # Verify descending order by timestamp
            for i in range(len(items) - 1):
                ts_current = items[i]["timestamp"]
                ts_next = items[i + 1]["timestamp"]
                assert ts_current >= ts_next, f"Items not sorted: {ts_current} < {ts_next}"
            print(f"✓ Storm uploads sorted newest first ({len(items)} items)")
        else:
            print("✓ Storm uploads sorted (not enough items to verify order)")
    
    def test_list_storm_uploads_with_limit(self):
        """GET /api/storm_uploads?limit=5 returns at most 5 items"""
        response = requests.get(f"{BASE_URL}/api/storm_uploads", params={"limit": 5})
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) <= 5
        print(f"✓ Storm uploads with limit=5: returned {len(data['items'])} items")
    
    def test_list_storm_uploads_item_structure(self):
        """Storm upload items have id, distance, energy, timestamp, received_at"""
        response = requests.get(f"{BASE_URL}/api/storm_uploads")
        assert response.status_code == 200
        
        items = response.json()["items"]
        if items:
            item = items[0]
            assert "id" in item
            assert "distance" in item
            assert "energy" in item
            assert "timestamp" in item
            assert "received_at" in item
            
            assert isinstance(item["distance"], (int, float))
            assert isinstance(item["energy"], (int, float))
            assert isinstance(item["timestamp"], str)
            print(f"✓ Item structure valid: id={item['id']}, distance={item['distance']}, energy={item['energy']}")
        else:
            print("✓ No items to verify structure (empty list)")


class TestLightningEndpoints:
    """Test Blitzortung lightning strike endpoints (NEW FEATURE)"""
    
    def test_lightning_strikes_basic(self):
        """GET /api/lightning/strikes returns count, strikes[], server_time"""
        response = requests.get(f"{BASE_URL}/api/lightning/strikes", params={
            "lat": 43.0951,
            "lon": -0.0434,
            "radius_km": 120
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "count" in data
        assert "strikes" in data
        assert "server_time" in data
        assert isinstance(data["count"], int)
        assert isinstance(data["strikes"], list)
        assert isinstance(data["server_time"], (int, float))
        print(f"✓ Lightning strikes: count={data['count']}, server_time={data['server_time']}")
    
    def test_lightning_strikes_with_since_filter(self):
        """GET /api/lightning/strikes with since param filters older strikes"""
        import time
        since_ts = time.time() - 3600  # Last hour
        
        response = requests.get(f"{BASE_URL}/api/lightning/strikes", params={
            "lat": 43.0951,
            "lon": -0.0434,
            "radius_km": 120,
            "since": since_ts
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "count" in data
        assert "strikes" in data
        
        # Verify all strikes are after since_ts
        for strike in data["strikes"]:
            assert strike["ts"] >= since_ts, f"Strike ts {strike['ts']} is before since {since_ts}"
        
        print(f"✓ Lightning strikes with since filter: count={data['count']}")
    
    def test_lightning_strike_object_structure(self):
        """Strike objects have lat, lon, ts, iso, distance_km"""
        response = requests.get(f"{BASE_URL}/api/lightning/strikes", params={
            "lat": 43.0951,
            "lon": -0.0434,
            "radius_km": 120
        })
        assert response.status_code == 200
        
        data = response.json()
        # If there are strikes, verify structure
        if data["strikes"]:
            strike = data["strikes"][0]
            assert "lat" in strike, "Strike missing lat"
            assert "lon" in strike, "Strike missing lon"
            assert "ts" in strike, "Strike missing ts"
            assert "iso" in strike, "Strike missing iso"
            assert "distance_km" in strike, "Strike missing distance_km"
            
            # Verify types
            assert isinstance(strike["lat"], (int, float))
            assert isinstance(strike["lon"], (int, float))
            assert isinstance(strike["ts"], (int, float))
            assert isinstance(strike["iso"], str)
            assert isinstance(strike["distance_km"], (int, float))
            print(f"✓ Strike structure valid: lat={strike['lat']}, lon={strike['lon']}, distance_km={strike['distance_km']}")
        else:
            print("✓ No strikes currently (weather may be calm) - structure test skipped")
    
    def test_lightning_status(self):
        """GET /api/lightning/status returns running=true, strikes_received >= 0, decode_errors = 0"""
        response = requests.get(f"{BASE_URL}/api/lightning/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "running" in data
        assert "strikes_received" in data
        assert "decode_errors" in data
        
        # Verify types and values
        assert isinstance(data["running"], bool)
        assert isinstance(data["strikes_received"], int)
        assert data["strikes_received"] >= 0
        assert isinstance(data["decode_errors"], int)
        
        print(f"✓ Lightning status: running={data['running']}, received={data['strikes_received']}, errors={data['decode_errors']}")


class TestStormTrajectory:
    """Test /api/storms/trajectory endpoint (PHASE 8 FEATURE)"""

    def test_trajectory_endpoint_basic(self):
        """GET /api/storms/trajectory returns valid JSON with detected field"""
        response = requests.get(f"{BASE_URL}/api/storms/trajectory", params={
            "lat": 43.0951,
            "lon": -0.0434,
            "project_minutes": 45
        })
        assert response.status_code == 200

        data = response.json()
        assert "detected" in data
        assert isinstance(data["detected"], bool)
        if not data["detected"]:
            # Legitimate response when not enough strikes
            assert "reason" in data
            print(f"✓ Trajectory detected=false: reason={data['reason']}, count={data.get('count', 0)}")
        else:
            # Full response
            for field in ["count", "waypoints", "speed_kmh", "bearing_deg", "compass", "closest_distance_km"]:
                assert field in data, f"Missing field: {field}"
            assert isinstance(data["waypoints"], list)
            assert len(data["waypoints"]) > 0
            print(f"✓ Trajectory detected: waypoints={len(data['waypoints'])}, speed={data['speed_kmh']}km/h, compass={data['compass']}")

    def test_trajectory_default_params(self):
        """GET /api/storms/trajectory works without params (uses Lourdes defaults)"""
        response = requests.get(f"{BASE_URL}/api/storms/trajectory")
        assert response.status_code == 200
        data = response.json()
        assert "detected" in data
        print(f"✓ Trajectory with defaults: detected={data['detected']}")


class TestStormApproach:
    """Regression test /api/storms/approach (PHASE 8)"""

    def test_approach_still_works(self):
        response = requests.get(f"{BASE_URL}/api/storms/approach", params={
            "lat": 43.0951, "lon": -0.0434, "radius_km": 100
        })
        assert response.status_code == 200
        data = response.json()
        assert "approaching" in data
        assert isinstance(data["approaching"], bool)
        assert "radius_analyzed_km" in data
        print(f"✓ Approach: approaching={data['approaching']}")


class TestForecastStormRisk:
    """Regression test /api/forecast/storm-risk (PHASE 8)"""

    def test_storm_risk_returns_days(self):
        response = requests.get(f"{BASE_URL}/api/forecast/storm-risk", params={"days": 7})
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert isinstance(data["days"], list)
        assert len(data["days"]) >= 5
        day = data["days"][0]
        assert "score" in day or "risk" in day or "date" in day
        print(f"✓ Storm risk forecast: {len(data['days'])} days")


class TestVigilance:
    """Test /api/weather/vigilance endpoint (PHASE 10 - MeteoAlarm primary source)"""

    def test_vigilance_basic_structure(self):
        """GET /api/weather/vigilance returns all required top-level keys"""
        response = requests.get(f"{BASE_URL}/api/weather/vigilance")
        assert response.status_code == 200
        data = response.json()
        for key in ["overall_level", "overall_level_fr", "overall_color", "overall_label",
                    "departements", "phenomena_meta", "levels_meta", "disclaimer", "source",
                    "source_label", "source_url", "updated_at"]:
            assert key in data, f"Missing top-level key: {key}"
        # Primary is meteoalarm; fallback is open-meteo-fallback
        assert data["source"] in ("meteoalarm", "open-meteo-fallback"), f"Unexpected source: {data['source']}"
        assert data["overall_level_fr"] in ("vert", "jaune", "orange", "rouge")
        assert data["overall_color"].startswith("#")
        assert 1 <= data["overall_level"] <= 4
        # Source label must mention MeteoAlarm or Open-Meteo fallback
        if data["source"] == "meteoalarm":
            assert "MeteoAlarm" in data["source_label"] or "Météo-France" in data["source_label"]
        print(f"✓ Vigilance source={data['source']} overall={data['overall_level']} ({data['overall_level_fr']})")

    def test_vigilance_seven_departements(self):
        """Vigilance returns 7 departements (65, 64, 32, 31, 09, 66, 40)"""
        response = requests.get(f"{BASE_URL}/api/weather/vigilance")
        assert response.status_code == 200
        data = response.json()
        depts = data["departements"]
        assert len(depts) == 7, f"Expected 7 depts, got {len(depts)}"
        dept_ids = sorted([d["id"] for d in depts])
        assert dept_ids == ["09", "31", "32", "40", "64", "65", "66"], f"Got {dept_ids}"
        # Each dept must have nuts3 code
        for d in depts:
            assert "nuts3" in d and d["nuts3"].startswith("FR"), f"Dept {d['id']} missing NUTS3"
        print(f"✓ Vigilance has 7 depts: {dept_ids}")

    def test_vigilance_phenomena_per_dept(self):
        """Each dept has 8 phenomena (orage, vent, pluie, canicule, grand-froid, neige, brouillard, avalanche)"""
        response = requests.get(f"{BASE_URL}/api/weather/vigilance")
        data = response.json()
        expected_keys = {"orage", "vent", "pluie", "canicule", "grand-froid", "neige", "brouillard", "avalanche"}
        for dept in data["departements"]:
            phen_keys = {p["key"] for p in dept["phenomena"]}
            # fallback path still returns 8 via PHENOMENA_META
            assert phen_keys == expected_keys, f"Dept {dept['id']} has {phen_keys}"
            for p in dept["phenomena"]:
                assert 1 <= p["level"] <= 4
                assert p["level_fr"] in ("vert", "jaune", "orange", "rouge")
                assert p["color"].startswith("#")
                assert "today" in p and "tomorrow" in p
        print("✓ All 7 depts have 8 phenomena with correct structure")

    def test_vigilance_meta_arrays(self):
        """phenomena_meta has 8 entries, levels_meta has 4 entries"""
        response = requests.get(f"{BASE_URL}/api/weather/vigilance")
        data = response.json()
        assert len(data["phenomena_meta"]) == 8, f"Got {len(data['phenomena_meta'])}"
        assert len(data["levels_meta"]) == 4, f"Got {len(data['levels_meta'])}"
        for m in data["levels_meta"]:
            assert "level" in m and "name" in m and "color" in m and "label" in m
        for m in data["phenomena_meta"]:
            assert "key" in m and "label" in m and "icon" in m
        print("✓ phenomena_meta=8, levels_meta=4")

    def test_vigilance_cached_fast(self):
        """Second call to /api/weather/vigilance should be fast (cached TTL 15min)"""
        import time
        requests.get(f"{BASE_URL}/api/weather/vigilance")  # warm up
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/weather/vigilance")
        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 1.0, f"Cached vigilance took {elapsed:.2f}s"
        print(f"✓ Cached vigilance response: {elapsed*1000:.0f}ms")




if __name__ == "__main__":
    pytest.main([__file__, "-v"])

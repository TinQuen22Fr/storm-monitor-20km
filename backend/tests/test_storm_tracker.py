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
                print(f"⚠ Test user may already exist with different password")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

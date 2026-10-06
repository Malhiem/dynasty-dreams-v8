"""
Iter 162 - Schedule Config Max 20 Bug Fix Tests

Tests that the schedule-config endpoint accepts values up to 20 for:
- intra_division_games
- intra_conference_games
- inter_conference_games

Previously capped at 10, now raised to 20.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"  # Existing roto league for testing

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestScheduleConfigMax20:
    """Test schedule-config endpoint accepts values up to 20."""

    def test_1_get_current_schedule_config(self, auth_headers):
        """Verify we can GET the current schedule config."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers
        )
        print(f"GET schedule-config status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert "intra_division_games" in data
        assert "intra_conference_games" in data
        assert "inter_conference_games" in data

    def test_2_put_inter_conference_12(self, auth_headers):
        """Test PUT with inter_conference_games=12 (previously capped at 10)."""
        payload = {
            "intra_division_games": 5,
            "intra_conference_games": 2,
            "inter_conference_games": 12
        }
        response = requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
            json=payload
        )
        print(f"PUT schedule-config (inter=12) status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("saved", {}).get("inter_conference_games") == 12

    def test_3_verify_persistence_inter_12(self, auth_headers):
        """Verify inter_conference_games=12 was persisted."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers
        )
        print(f"GET schedule-config (verify persistence) status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("inter_conference_games") == 12, f"Expected 12, got {data.get('inter_conference_games')}"

    def test_4_put_all_fields_at_20(self, auth_headers):
        """Test PUT with all fields at max value 20."""
        payload = {
            "intra_division_games": 20,
            "intra_conference_games": 20,
            "inter_conference_games": 20
        }
        response = requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
            json=payload
        )
        print(f"PUT schedule-config (all=20) status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        saved = data.get("saved", {})
        assert saved.get("intra_division_games") == 20
        assert saved.get("intra_conference_games") == 20
        assert saved.get("inter_conference_games") == 20

    def test_5_reject_value_above_20(self, auth_headers):
        """Test PUT with value above 20 is rejected with 400."""
        payload = {
            "intra_division_games": 5,
            "intra_conference_games": 2,
            "inter_conference_games": 21  # Above max
        }
        response = requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
            json=payload
        )
        print(f"PUT schedule-config (inter=21) status: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 400, f"Expected 400 for value > 20, got {response.status_code}"

    def test_6_reject_intra_division_above_20(self, auth_headers):
        """Test PUT with intra_division_games above 20 is rejected."""
        payload = {
            "intra_division_games": 25,  # Above max
            "intra_conference_games": 2,
            "inter_conference_games": 5
        }
        response = requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
            json=payload
        )
        print(f"PUT schedule-config (intra_div=25) status: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 400, f"Expected 400 for value > 20, got {response.status_code}"

    def test_7_accept_zero_values(self, auth_headers):
        """Test PUT with zero values is accepted (min is 0)."""
        payload = {
            "intra_division_games": 0,
            "intra_conference_games": 0,
            "inter_conference_games": 0
        }
        response = requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
            json=payload
        )
        print(f"PUT schedule-config (all=0) status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        saved = data.get("saved", {})
        assert saved.get("intra_division_games") == 0
        assert saved.get("intra_conference_games") == 0
        assert saved.get("inter_conference_games") == 0

    def test_8_restore_reasonable_defaults(self, auth_headers):
        """Restore reasonable defaults after testing."""
        payload = {
            "intra_division_games": 2,
            "intra_conference_games": 1,
            "inter_conference_games": 1
        }
        response = requests.put(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
            json=payload
        )
        print(f"PUT schedule-config (restore defaults) status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Scoring Format Feature Tests
Tests for the scoring format selection in League Administration → League Setup → Scoring System

Test Coverage:
1. GET /api/leagues/{id} returns scoring_format
2. PUT /api/leagues/{id} with scoring_format updates the league
3. Verify all 5 scoring formats can be saved: rotisserie, points, h2h-points, h2h-categories, h2h-each
4. Verify persistence after update (GET returns new value)
5. Error handling for invalid league ID
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

# Test league IDs from review request
STAT_CHASERS_ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"  # scoring_format=rotisserie
FROZEN_DYNASTY_LEAGUE_ID = "69e46af167999bfb85c3962a"  # scoring_format=head_to_head

# All valid scoring formats
SCORING_FORMATS = [
    "rotisserie",
    "points",
    "h2h-points",
    "h2h-categories",
    "h2h-each"
]


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    # Login returns access_token (not 'token')
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in response: {data}")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with authentication"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestScoringFormatAPI:
    """Test scoring format API endpoints"""

    def test_get_league_returns_scoring_format(self, auth_headers):
        """GET /api/leagues/{id} should return scoring_format field"""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "scoring_format" in data, f"scoring_format not in response: {data.keys()}"
        print(f"✓ GET league returns scoring_format: {data['scoring_format']}")

    def test_stat_chasers_roto_has_rotisserie_format(self, auth_headers):
        """Stat Chasers Roto league should have scoring_format=rotisserie"""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # The backend may store 'rotisserie' directly
        assert data["scoring_format"] in ["rotisserie", "roto"], \
            f"Expected rotisserie, got {data['scoring_format']}"
        print(f"✓ Stat Chasers Roto has scoring_format: {data['scoring_format']}")

    def test_frozen_dynasty_has_h2h_format(self, auth_headers):
        """Frozen Dynasty league should have scoring_format=head_to_head (maps to h2h-points in UI)"""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_LEAGUE_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Backend stores 'head_to_head', UI maps to 'h2h-points'
        assert data["scoring_format"] in ["head_to_head", "h2h-points", "h2h_points"], \
            f"Expected head_to_head or h2h-points, got {data['scoring_format']}"
        print(f"✓ Frozen Dynasty has scoring_format: {data['scoring_format']}")

    def test_update_scoring_format_to_points(self, auth_headers):
        """PUT /api/leagues/{id} with scoring_format='points' should update and persist"""
        # First, get current format
        get_response = requests.get(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        original_format = get_response.json()["scoring_format"]
        print(f"Original format: {original_format}")

        # Update to 'points'
        put_response = requests.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"scoring_format": "points"}
        )
        assert put_response.status_code == 200, f"PUT failed: {put_response.status_code} - {put_response.text}"
        put_data = put_response.json()
        assert put_data.get("scoring_format") == "points", \
            f"PUT response should have scoring_format=points, got {put_data.get('scoring_format')}"
        print(f"✓ PUT response shows scoring_format: {put_data.get('scoring_format')}")

        # Verify persistence with GET
        verify_response = requests.get(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["scoring_format"] == "points", \
            f"GET after PUT should return 'points', got {verify_data['scoring_format']}"
        print(f"✓ GET after PUT confirms persistence: {verify_data['scoring_format']}")

        # Restore original format
        restore_response = requests.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"scoring_format": original_format}
        )
        assert restore_response.status_code == 200
        print(f"✓ Restored original format: {original_format}")

    def test_update_scoring_format_all_formats(self, auth_headers):
        """Test that all 5 scoring formats can be saved"""
        # Get original format first
        get_response = requests.get(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        original_format = get_response.json()["scoring_format"]

        for fmt in SCORING_FORMATS:
            # Update to this format
            put_response = requests.put(
                f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
                headers=auth_headers,
                json={"scoring_format": fmt}
            )
            assert put_response.status_code == 200, \
                f"Failed to update to {fmt}: {put_response.status_code} - {put_response.text}"

            # Verify with GET
            verify_response = requests.get(
                f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
                headers=auth_headers
            )
            assert verify_response.status_code == 200
            assert verify_response.json()["scoring_format"] == fmt, \
                f"Expected {fmt}, got {verify_response.json()['scoring_format']}"
            print(f"✓ Format '{fmt}' saved and persisted successfully")

        # Restore original format
        requests.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"scoring_format": original_format}
        )
        print(f"✓ Restored original format: {original_format}")

    def test_update_same_format_no_change(self, auth_headers):
        """Clicking the same format that is already selected should work (idempotent)"""
        # Get current format
        get_response = requests.get(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        current_format = get_response.json()["scoring_format"]

        # Update to the same format
        put_response = requests.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers=auth_headers,
            json={"scoring_format": current_format}
        )
        # Should succeed (idempotent operation)
        assert put_response.status_code == 200, \
            f"Idempotent update failed: {put_response.status_code} - {put_response.text}"
        print(f"✓ Idempotent update to same format '{current_format}' succeeded")

    def test_update_nonexistent_league_returns_404(self, auth_headers):
        """PUT to non-existent league should return 404"""
        fake_league_id = "000000000000000000000000"
        put_response = requests.put(
            f"{BASE_URL}/api/leagues/{fake_league_id}",
            headers=auth_headers,
            json={"scoring_format": "points"}
        )
        assert put_response.status_code == 404, \
            f"Expected 404 for non-existent league, got {put_response.status_code}"
        print(f"✓ Non-existent league returns 404")

    def test_update_invalid_league_id_returns_error(self, auth_headers):
        """PUT with invalid league ID format should return error"""
        invalid_league_id = "invalid-id-format"
        put_response = requests.put(
            f"{BASE_URL}/api/leagues/{invalid_league_id}",
            headers=auth_headers,
            json={"scoring_format": "points"}
        )
        # Should return 400 or 422 for invalid ObjectId format
        assert put_response.status_code in [400, 422, 404], \
            f"Expected 400/422/404 for invalid league ID, got {put_response.status_code}"
        print(f"✓ Invalid league ID returns error: {put_response.status_code}")


class TestScoringFormatUnauthorized:
    """Test scoring format API without proper authorization"""

    def test_update_without_auth_returns_401(self):
        """PUT without authentication should return 401"""
        put_response = requests.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_LEAGUE_ID}",
            headers={"Content-Type": "application/json"},
            json={"scoring_format": "points"}
        )
        assert put_response.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {put_response.status_code}"
        print(f"✓ Unauthorized update returns: {put_response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

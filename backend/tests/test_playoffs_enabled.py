"""
Iter 232N.89 — Playoffs Enabled Toggle Tests

Tests the playoffs_enabled field on leagues:
- PUT /api/leagues/{id} with playoffs_enabled=false saves and returns the value
- PUT /api/leagues/{id} with playoffs_enabled=true restores it
- GET /api/leagues/{id} returns playoffs_enabled (defaults to true for legacy leagues)
- When playoffs_enabled=false, playoff validation is skipped (no errors for invalid playoff config)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

# Test league IDs from the review request
STAT_CHASERS_ROTO_ID = "69e46af167999bfb85c39629"
FROZEN_DYNASTY_ID = "69e46af167999bfb85c3962a"


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
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestPlayoffsEnabledBackend:
    """Backend API tests for playoffs_enabled toggle"""

    def test_get_league_returns_playoffs_enabled_default_true(self, api_client):
        """GET /api/leagues/{id} returns playoffs_enabled field, defaults to true"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        assert response.status_code == 200, f"GET league failed: {response.text}"

        data = response.json()
        # Field should exist in response
        assert "playoffs_enabled" in data, "playoffs_enabled field missing from response"
        # Default should be true for backward compatibility
        assert data["playoffs_enabled"] in [True, None], f"Expected playoffs_enabled to be True or None, got {data['playoffs_enabled']}"
        print(f"✓ GET league returns playoffs_enabled: {data['playoffs_enabled']}")

    def test_put_league_disable_playoffs(self, api_client):
        """PUT /api/leagues/{id} with playoffs_enabled=false saves the value"""
        # First, get current state
        get_response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        assert get_response.status_code == 200
        original_state = get_response.json().get("playoffs_enabled", True)

        # Disable playoffs
        response = api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"playoffs_enabled": False}
        )
        assert response.status_code == 200, f"PUT failed: {response.text}"

        data = response.json()
        assert data.get("playoffs_enabled") == False, f"Expected playoffs_enabled=False in response, got {data.get('playoffs_enabled')}"
        print(f"✓ PUT with playoffs_enabled=false returns: {data.get('playoffs_enabled')}")

        # Verify persistence with GET
        verify_response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data.get("playoffs_enabled") == False, f"GET after PUT shows: {verify_data.get('playoffs_enabled')}"
        print(f"✓ GET after PUT confirms playoffs_enabled=False persisted")

        # Restore original state
        api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"playoffs_enabled": original_state if original_state is not None else True}
        )

    def test_put_league_enable_playoffs(self, api_client):
        """PUT /api/leagues/{id} with playoffs_enabled=true restores playoffs"""
        # First disable
        api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"playoffs_enabled": False}
        )

        # Then enable
        response = api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"playoffs_enabled": True}
        )
        assert response.status_code == 200, f"PUT failed: {response.text}"

        data = response.json()
        assert data.get("playoffs_enabled") == True, f"Expected playoffs_enabled=True, got {data.get('playoffs_enabled')}"
        print(f"✓ PUT with playoffs_enabled=true returns: {data.get('playoffs_enabled')}")

        # Verify persistence
        verify_response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data.get("playoffs_enabled") == True, f"GET after PUT shows: {verify_data.get('playoffs_enabled')}"
        print(f"✓ GET after PUT confirms playoffs_enabled=True persisted")

    def test_playoffs_disabled_skips_validation(self, api_client):
        """When playoffs_enabled=false, playoff validation is skipped"""
        # Get current state to restore later
        get_response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        original_data = get_response.json()

        # Disable playoffs and set invalid playoff config (end before start)
        # This should NOT raise a validation error when playoffs are disabled
        response = api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={
                "playoffs_enabled": False,
                "playoff_start_week": 20,
                "playoff_end_week": 15,  # Invalid: end before start
            }
        )

        # Should succeed because validation is skipped when playoffs disabled
        assert response.status_code == 200, f"Expected 200 when playoffs disabled, got {response.status_code}: {response.text}"
        print(f"✓ Invalid playoff config accepted when playoffs_enabled=false")

        # Restore original state
        api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={
                "playoffs_enabled": original_data.get("playoffs_enabled", True),
                "playoff_start_week": original_data.get("playoff_start_week"),
                "playoff_end_week": original_data.get("playoff_end_week"),
            }
        )

    def test_playoffs_enabled_enforces_validation(self, api_client):
        """When playoffs_enabled=true, playoff validation IS enforced"""
        # Get current state
        get_response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        original_data = get_response.json()

        # Try to set invalid playoff config with playoffs enabled
        response = api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={
                "playoffs_enabled": True,
                "playoff_start_week": 20,
                "playoff_end_week": 15,  # Invalid: end before start
            }
        )

        # Should fail validation when playoffs are enabled
        assert response.status_code == 400, f"Expected 400 for invalid playoff config when enabled, got {response.status_code}"
        print(f"✓ Invalid playoff config rejected when playoffs_enabled=true")

        # Restore original state (in case it somehow succeeded)
        api_client.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={
                "playoffs_enabled": original_data.get("playoffs_enabled", True),
                "playoff_start_week": original_data.get("playoff_start_week"),
                "playoff_end_week": original_data.get("playoff_end_week"),
            }
        )

    def test_frozen_dynasty_league_playoffs_toggle(self, api_client):
        """Test playoffs toggle on Frozen Dynasty league"""
        # Get current state
        get_response = api_client.get(f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}")
        if get_response.status_code != 200:
            pytest.skip(f"Frozen Dynasty league not found: {get_response.status_code}")

        original_state = get_response.json().get("playoffs_enabled", True)

        # Toggle off
        response = api_client.put(
            f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}",
            json={"playoffs_enabled": False}
        )
        assert response.status_code == 200, f"PUT failed: {response.text}"
        assert response.json().get("playoffs_enabled") == False
        print(f"✓ Frozen Dynasty: playoffs disabled")

        # Toggle back on
        response = api_client.put(
            f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}",
            json={"playoffs_enabled": True}
        )
        assert response.status_code == 200
        assert response.json().get("playoffs_enabled") == True
        print(f"✓ Frozen Dynasty: playoffs re-enabled")

        # Restore original
        api_client.put(
            f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}",
            json={"playoffs_enabled": original_state if original_state is not None else True}
        )

    def test_playoffs_enabled_field_in_league_response_model(self, api_client):
        """Verify playoffs_enabled is properly included in LeagueResponse"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}")
        assert response.status_code == 200

        data = response.json()

        # Check that all playoff-related fields are present
        playoff_fields = [
            "playoffs_enabled",
            "playoff_teams",
            "playoff_start_week",
            "playoff_end_week",
            "playoff_rounds",
        ]

        for field in playoff_fields:
            assert field in data, f"Field '{field}' missing from league response"

        print(f"✓ All playoff fields present in response: {[f for f in playoff_fields if f in data]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

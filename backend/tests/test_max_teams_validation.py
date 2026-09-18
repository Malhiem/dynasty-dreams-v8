"""
Iter 157 — Test max_teams validation for rotisserie leagues.
Tests the 32-team cap without duplicate players and 100-team cap with duplicate players.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test leagues from seed data
STAT_CHASERS_ROTO_ID = "69e46af167999bfb85c39629"  # max_teams=14, allow_duplicate_players=false
FROZEN_DYNASTY_ID = "69e46af167999bfb85c3962a"     # max_teams=16, allow_duplicate_players=false


@pytest.fixture(scope="module")
def auth_session():
    """Authenticate and return session with auth cookies."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@dynastydreams.com",
        "password": "Admin123!"
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return session


class TestMaxTeamsValidation:
    """Test max_teams validation rules for PUT /api/leagues/{id}"""
    
    def test_max_teams_25_succeeds_without_duplicate_players(self, auth_session):
        """max_teams=25 should succeed (within 32 cap, no duplicate players)"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 25}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("max_teams") == 25, f"Expected max_teams=25, got {data.get('max_teams')}"
        print(f"✓ max_teams=25 succeeded without duplicate players")
    
    def test_max_teams_50_fails_without_duplicate_players(self, auth_session):
        """max_teams=50 WITHOUT allow_duplicate_players should return 400"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 50}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "max_teams > 32 requires allow_duplicate_players" in data.get("detail", ""), \
            f"Expected error about duplicate players, got: {data}"
        print(f"✓ max_teams=50 without duplicate players correctly returned 400")
    
    def test_max_teams_50_succeeds_with_duplicate_players(self, auth_session):
        """max_teams=50 WITH allow_duplicate_players=true should succeed"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 50, "allow_duplicate_players": True}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("max_teams") == 50, f"Expected max_teams=50, got {data.get('max_teams')}"
        assert data.get("allow_duplicate_players") == True, \
            f"Expected allow_duplicate_players=True, got {data.get('allow_duplicate_players')}"
        print(f"✓ max_teams=50 with duplicate players succeeded")
    
    def test_max_teams_101_fails_validation(self, auth_session):
        """max_teams=101 should return validation error (above 100 cap)"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 101, "allow_duplicate_players": True}
        )
        # Pydantic validation should reject values > 100
        assert response.status_code == 422, f"Expected 422 validation error, got {response.status_code}: {response.text}"
        print(f"✓ max_teams=101 correctly returned 422 validation error")
    
    def test_max_teams_32_boundary_without_duplicate_players(self, auth_session):
        """max_teams=32 should succeed (exactly at boundary, no duplicate players)"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 32, "allow_duplicate_players": False}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("max_teams") == 32, f"Expected max_teams=32, got {data.get('max_teams')}"
        print(f"✓ max_teams=32 boundary succeeded without duplicate players")
    
    def test_max_teams_33_fails_without_duplicate_players(self, auth_session):
        """max_teams=33 WITHOUT allow_duplicate_players should return 400"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 33, "allow_duplicate_players": False}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "max_teams > 32 requires allow_duplicate_players" in data.get("detail", ""), \
            f"Expected error about duplicate players, got: {data}"
        print(f"✓ max_teams=33 without duplicate players correctly returned 400")
    
    def test_max_teams_100_succeeds_with_duplicate_players(self, auth_session):
        """max_teams=100 WITH allow_duplicate_players=true should succeed (at max cap)"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 100, "allow_duplicate_players": True}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("max_teams") == 100, f"Expected max_teams=100, got {data.get('max_teams')}"
        print(f"✓ max_teams=100 with duplicate players succeeded")


class TestRestoreOriginalValues:
    """Restore original max_teams values after testing"""
    
    def test_restore_stat_chasers_roto(self, auth_session):
        """Restore Stat Chasers Roto to max_teams=14, allow_duplicate_players=false"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{STAT_CHASERS_ROTO_ID}",
            json={"max_teams": 14, "allow_duplicate_players": False}
        )
        assert response.status_code == 200, f"Failed to restore: {response.text}"
        data = response.json()
        assert data.get("max_teams") == 14, f"Expected max_teams=14, got {data.get('max_teams')}"
        assert data.get("allow_duplicate_players") == False, \
            f"Expected allow_duplicate_players=False, got {data.get('allow_duplicate_players')}"
        print(f"✓ Restored Stat Chasers Roto to max_teams=14, allow_duplicate_players=false")
    
    def test_restore_frozen_dynasty(self, auth_session):
        """Restore Frozen Dynasty to max_teams=16, allow_duplicate_players=false"""
        response = auth_session.put(
            f"{BASE_URL}/api/leagues/{FROZEN_DYNASTY_ID}",
            json={"max_teams": 16, "allow_duplicate_players": False}
        )
        assert response.status_code == 200, f"Failed to restore: {response.text}"
        data = response.json()
        assert data.get("max_teams") == 16, f"Expected max_teams=16, got {data.get('max_teams')}"
        print(f"✓ Restored Frozen Dynasty to max_teams=16, allow_duplicate_players=false")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

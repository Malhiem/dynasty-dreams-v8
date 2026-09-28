"""Iteration 169 - Team endpoint security tests.

Tests the security fix for three private-league team endpoints:
  - GET /api/teams/{team_id}/lineup
  - GET /api/teams/{team_id}/compliance
  - GET /api/teams/{team_id}/draft-picks

All three endpoints should:
  - Return 401 for unauthenticated requests
  - Return 401 for invalid/expired tokens
  - Return 404 for non-existent teams (when authenticated)
  - Return 200 for authenticated admin/member access
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"

# Non-existent team ID (valid ObjectId format but doesn't exist)
NON_EXISTENT_TEAM_ID = "000000000000000000000000"

# Invalid token for testing
INVALID_TOKEN = "invalidtoken123"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    # Token field is 'access_token' per the review request
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in login response: {data}")
    return token


@pytest.fixture(scope="module")
def existing_team_id(admin_token):
    """Get an existing team ID for positive tests."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Get teams from a specific league (Stat Chasers Roto)
    league_id = "69e46af167999bfb85c39629"
    response = requests.get(f"{BASE_URL}/api/teams?league_id={league_id}", headers=headers)
    if response.status_code != 200:
        pytest.skip(f"Could not fetch teams: {response.status_code}")
    teams = response.json()
    if isinstance(teams, dict):
        teams = teams.get("teams", [])
    if not teams:
        pytest.skip("No teams found for testing")
    # Return the first team's ID
    team = teams[0]
    return team.get("_id") or team.get("id")


class TestLineupEndpointSecurity:
    """Tests for GET /api/teams/{team_id}/lineup security."""

    def test_unauthenticated_request_returns_401(self):
        """Unauthenticated request to GET /api/teams/{team_id}/lineup returns 401."""
        # Use a placeholder team_id - the auth check should happen first
        response = requests.get(f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/lineup")
        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {response.status_code}: {response.text}"
        )
        print("PASS: Unauthenticated request to /lineup returns 401")

    def test_invalid_token_returns_401(self):
        """Request with invalid/expired token to GET /api/teams/{team_id}/lineup returns 401."""
        headers = {"Authorization": f"Bearer {INVALID_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/lineup",
            headers=headers,
        )
        assert response.status_code == 401, (
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"
        )
        print("PASS: Invalid token request to /lineup returns 401")

    def test_non_existent_team_returns_404(self, admin_token):
        """Authenticated request to GET /api/teams/{non_existent_id}/lineup returns 404."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/lineup",
            headers=headers,
        )
        assert response.status_code == 404, (
            f"Expected 404 for non-existent team, got {response.status_code}: {response.text}"
        )
        print("PASS: Non-existent team request to /lineup returns 404")

    def test_authenticated_admin_can_access(self, admin_token, existing_team_id):
        """Authenticated admin can access GET /api/teams/{team_id}/lineup and get 200."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{existing_team_id}/lineup",
            headers=headers,
        )
        assert response.status_code == 200, (
            f"Expected 200 for authenticated admin, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "team_id" in data or "lineup" in data, f"Unexpected response: {data}"
        print(f"PASS: Authenticated admin can access /lineup for team {existing_team_id}")


class TestComplianceEndpointSecurity:
    """Tests for GET /api/teams/{team_id}/compliance security."""

    def test_unauthenticated_request_returns_401(self):
        """Unauthenticated request to GET /api/teams/{team_id}/compliance returns 401."""
        response = requests.get(f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/compliance")
        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {response.status_code}: {response.text}"
        )
        print("PASS: Unauthenticated request to /compliance returns 401")

    def test_invalid_token_returns_401(self):
        """Request with invalid/expired token to GET /api/teams/{team_id}/compliance returns 401."""
        headers = {"Authorization": f"Bearer {INVALID_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/compliance",
            headers=headers,
        )
        assert response.status_code == 401, (
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"
        )
        print("PASS: Invalid token request to /compliance returns 401")

    def test_non_existent_team_returns_404(self, admin_token):
        """Authenticated request to GET /api/teams/{non_existent_id}/compliance returns 404."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/compliance",
            headers=headers,
        )
        assert response.status_code == 404, (
            f"Expected 404 for non-existent team, got {response.status_code}: {response.text}"
        )
        print("PASS: Non-existent team request to /compliance returns 404")

    def test_authenticated_admin_can_access(self, admin_token, existing_team_id):
        """Authenticated admin can access GET /api/teams/{team_id}/compliance and get 200."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{existing_team_id}/compliance",
            headers=headers,
        )
        assert response.status_code == 200, (
            f"Expected 200 for authenticated admin, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "team_id" in data or "compliant" in data, f"Unexpected response: {data}"
        print(f"PASS: Authenticated admin can access /compliance for team {existing_team_id}")


class TestDraftPicksEndpointSecurity:
    """Tests for GET /api/teams/{team_id}/draft-picks security."""

    def test_unauthenticated_request_returns_401(self):
        """Unauthenticated request to GET /api/teams/{team_id}/draft-picks returns 401."""
        response = requests.get(f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/draft-picks")
        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {response.status_code}: {response.text}"
        )
        print("PASS: Unauthenticated request to /draft-picks returns 401")

    def test_invalid_token_returns_401(self):
        """Request with invalid/expired token to GET /api/teams/{team_id}/draft-picks returns 401."""
        headers = {"Authorization": f"Bearer {INVALID_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/draft-picks",
            headers=headers,
        )
        assert response.status_code == 401, (
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"
        )
        print("PASS: Invalid token request to /draft-picks returns 401")

    def test_non_existent_team_returns_404(self, admin_token):
        """Authenticated request to GET /api/teams/{non_existent_id}/draft-picks returns 404."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{NON_EXISTENT_TEAM_ID}/draft-picks",
            headers=headers,
        )
        assert response.status_code == 404, (
            f"Expected 404 for non-existent team, got {response.status_code}: {response.text}"
        )
        print("PASS: Non-existent team request to /draft-picks returns 404")

    def test_authenticated_admin_can_access(self, admin_token, existing_team_id):
        """Authenticated admin can access GET /api/teams/{team_id}/draft-picks and get 200."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/teams/{existing_team_id}/draft-picks",
            headers=headers,
        )
        assert response.status_code == 200, (
            f"Expected 200 for authenticated admin, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "team_id" in data or "picks" in data, f"Unexpected response: {data}"
        print(f"PASS: Authenticated admin can access /draft-picks for team {existing_team_id}")


class TestExistingSecuredEndpointsStillWork:
    """Verify existing secured endpoints still work for authenticated admin."""

    def test_get_teams_with_league_id_returns_200_for_admin(self, admin_token):
        """Authenticated admin can access GET /api/teams?league_id=... and get 200."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        league_id = "69e46af167999bfb85c39629"
        response = requests.get(f"{BASE_URL}/api/teams?league_id={league_id}", headers=headers)
        assert response.status_code == 200, (
            f"Expected 200 for authenticated admin on /api/teams?league_id=..., got {response.status_code}: {response.text}"
        )
        print("PASS: Authenticated admin can access GET /api/teams?league_id=... and get 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

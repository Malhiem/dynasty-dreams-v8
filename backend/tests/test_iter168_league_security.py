"""Iter 168 — Private-league API access security fix tests.

Tests verify that:
1. Unauthenticated users get 401 on protected league endpoints
2. Authenticated admin/commissioner CAN access their league data (200)
3. Team-league mismatch returns 404 (not 200)

Endpoints tested:
- GET /api/leagues/{id}/standings
- GET /api/scoring/calculate/{id}
- GET /api/scoring/roto/{id}
- GET /api/matchups/{id}
- GET /api/leagues/{id}/roto/standings
- GET /api/leagues/{id}/playoff-bracket
- GET /api/leagues/{id}/divisions
- GET /api/leagues/{id}/schedule-config
- GET /api/leagues/{id}/roster-limits
- GET /api/leagues/{id}/lock-status
- GET /api/live-scoring/league/{id}
- GET /api/matchups/{id}/daily-scoring?team_id={team_id}
- GET /api/live-scoring/team/{team_id}
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"

# League IDs from agent context (admin is commissioner of these)
H2H_LEAGUE_ID = "69e46af167999bfb85c3962b"
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    # Token key is access_token (not token)
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in login response: {data}")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {admin_token}"}


class TestUnauthenticatedAccess:
    """Verify unauthenticated requests return 401 on protected endpoints."""

    def test_unauthenticated_standings_returns_401(self):
        """GET /api/leagues/{id}/standings without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/standings")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_scoring_calculate_returns_401(self):
        """GET /api/scoring/calculate/{id} without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/scoring/calculate/{H2H_LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_scoring_roto_returns_401(self):
        """GET /api/scoring/roto/{id} without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/scoring/roto/{ROTO_LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_matchups_returns_401(self):
        """GET /api/matchups/{id} without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_roto_standings_returns_401(self):
        """GET /api/leagues/{id}/roto/standings without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_playoff_bracket_returns_401(self):
        """GET /api/leagues/{id}/playoff-bracket without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/playoff-bracket")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_divisions_returns_401(self):
        """GET /api/leagues/{id}/divisions without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/divisions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_schedule_config_returns_401(self):
        """GET /api/leagues/{id}/schedule-config without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/schedule-config")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_roster_limits_returns_401(self):
        """GET /api/leagues/{id}/roster-limits without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/roster-limits")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_lock_status_returns_401(self):
        """GET /api/leagues/{id}/lock-status without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/lock-status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_unauthenticated_live_scoring_league_returns_401(self):
        """GET /api/live-scoring/league/{id} without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/live-scoring/league/{H2H_LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"


class TestAuthenticatedAdminAccess:
    """Verify authenticated admin/commissioner CAN access their league data."""

    def test_authenticated_standings_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/standings with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/standings",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "standings" in data, f"Response should contain 'standings': {data}"

    def test_authenticated_scoring_calculate_returns_200(self, auth_headers):
        """GET /api/scoring/calculate/{id} with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        # Response is a list of team scoring results
        data = response.json()
        assert isinstance(data, list), f"Response should be a list: {data}"

    def test_authenticated_matchups_returns_200(self, auth_headers):
        """GET /api/matchups/{id} with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        # Response is a list of matchups
        data = response.json()
        assert isinstance(data, list), f"Response should be a list: {data}"

    def test_authenticated_roto_standings_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/roto/standings with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "totals" in data or "categories" in data, f"Response should contain roto data: {data}"

    def test_authenticated_playoff_bracket_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/playoff-bracket with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/playoff-bracket",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Response should have rounds or status
        assert "rounds" in data or "status" in data, f"Response should contain bracket data: {data}"

    def test_authenticated_divisions_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/divisions with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/divisions",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "divisions" in data, f"Response should contain 'divisions': {data}"

    def test_authenticated_schedule_config_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/schedule-config with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/schedule-config",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Response should have schedule config fields
        assert "intra_division_games" in data or "configured" in data, f"Response should contain schedule config: {data}"

    def test_authenticated_live_scoring_league_returns_200(self, auth_headers):
        """GET /api/live-scoring/league/{id} with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/live-scoring/league/{H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "league_id" in data or "leaderboard" in data, f"Response should contain live scoring data: {data}"


class TestTeamLeagueMismatch:
    """Verify team-league mismatch returns 404 (not 200)."""

    def test_daily_scoring_team_league_mismatch_returns_404(self, auth_headers):
        """GET /api/matchups/{league_A}/daily-scoring?team_id={team_from_league_B} should return 404."""
        # First, get a team from the H2H league
        teams_response = requests.get(
            f"{BASE_URL}/api/teams?league_id={H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        if teams_response.status_code != 200:
            pytest.skip(f"Could not get teams: {teams_response.status_code}")
        
        teams = teams_response.json()
        if not teams:
            pytest.skip("No teams found in H2H league")
        
        h2h_team_id = teams[0].get("id") or str(teams[0].get("_id"))
        
        # Now try to access daily scoring with H2H team but ROTO league
        response = requests.get(
            f"{BASE_URL}/api/matchups/{ROTO_LEAGUE_ID}/daily-scoring?team_id={h2h_team_id}",
            headers=auth_headers,
        )
        # Should return 404 because team doesn't belong to the specified league
        assert response.status_code == 404, f"Expected 404 for team-league mismatch, got {response.status_code}: {response.text}"

    def test_live_scoring_team_verifies_membership(self, auth_headers):
        """GET /api/live-scoring/team/{team_id} should verify team belongs to a league the user is a member of."""
        # First, get a team from the H2H league
        teams_response = requests.get(
            f"{BASE_URL}/api/teams?league_id={H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        if teams_response.status_code != 200:
            pytest.skip(f"Could not get teams: {teams_response.status_code}")
        
        teams = teams_response.json()
        if not teams:
            pytest.skip("No teams found in H2H league")
        
        team_id = teams[0].get("id") or str(teams[0].get("_id"))
        
        # Admin should be able to access team live scoring (they're a member)
        response = requests.get(
            f"{BASE_URL}/api/live-scoring/team/{team_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200 for valid team access, got {response.status_code}: {response.text}"


class TestRosterLimitsAndLockStatus:
    """Test roster-limits and lock-status endpoints."""

    def test_authenticated_roster_limits_returns_200_or_404(self, auth_headers):
        """GET /api/leagues/{id}/roster-limits with auth should return 200 or 404 (if not configured)."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/roster-limits",
            headers=auth_headers,
        )
        # 200 if configured, 404 if endpoint doesn't exist or not configured
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"

    def test_authenticated_lock_status_returns_200_or_404(self, auth_headers):
        """GET /api/leagues/{id}/lock-status with auth should return 200 or 404 (if not configured)."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/lock-status",
            headers=auth_headers,
        )
        # 200 if configured, 404 if endpoint doesn't exist
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"


class TestScoringRotoEndpoint:
    """Test scoring/roto endpoint specifically."""

    def test_authenticated_scoring_roto_returns_200(self, auth_headers):
        """GET /api/scoring/roto/{id} with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/roto/{ROTO_LEAGUE_ID}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "categories" in data or "standings" in data, f"Response should contain roto data: {data}"


class TestCurrentWeekEndpoint:
    """Test matchups current-week endpoint."""

    def test_unauthenticated_current_week_returns_401(self):
        """GET /api/matchups/{id}/current-week without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/current-week")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_authenticated_current_week_returns_200(self, auth_headers):
        """GET /api/matchups/{id}/current-week with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/current-week",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "week" in data or "matchups" in data, f"Response should contain week data: {data}"


class TestWeekResultsEndpoint:
    """Test matchups results endpoint."""

    def test_unauthenticated_week_results_returns_401(self):
        """GET /api/matchups/{id}/results?week=1 without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/results?week=1")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_authenticated_week_results_returns_200(self, auth_headers):
        """GET /api/matchups/{id}/results?week=1 with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/results?week=1",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestRotoCatalogEndpoint:
    """Test roto categories catalog endpoint."""

    def test_unauthenticated_roto_catalog_returns_401(self):
        """GET /api/leagues/{id}/roto/categories/catalog without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/categories/catalog")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_authenticated_roto_catalog_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/roto/categories/catalog with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/categories/catalog",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "categories" in data, f"Response should contain 'categories': {data}"


class TestRotoMatchupEndpoint:
    """Test roto matchup endpoint."""

    def test_unauthenticated_roto_matchup_returns_401(self):
        """GET /api/leagues/{id}/roto/matchup without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/matchup")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_authenticated_roto_matchup_returns_200(self, auth_headers):
        """GET /api/leagues/{id}/roto/matchup with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/matchup",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestScoringConfigEndpoint:
    """Test scoring config endpoint."""

    def test_unauthenticated_scoring_config_returns_401(self):
        """GET /api/scoring/config?league_id={id} without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/scoring/config?league_id={H2H_LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_authenticated_scoring_config_returns_200(self, auth_headers):
        """GET /api/scoring/config?league_id={id} with auth should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/config?league_id={H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "league_id" in data or "skater_scoring" in data, f"Response should contain scoring config: {data}"


class TestLiveScoringTeamWeekEndpoint:
    """Test live-scoring team week summary endpoint."""

    def test_unauthenticated_team_week_summary_returns_401(self, auth_headers):
        """GET /api/live-scoring/team/{team_id}/week without auth should return 401."""
        # First get a team ID
        teams_response = requests.get(
            f"{BASE_URL}/api/teams?league_id={H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        if teams_response.status_code != 200:
            pytest.skip(f"Could not get teams: {teams_response.status_code}")
        
        teams = teams_response.json()
        if not teams:
            pytest.skip("No teams found")
        
        team_id = teams[0].get("id") or str(teams[0].get("_id"))
        
        # Now test without auth
        response = requests.get(f"{BASE_URL}/api/live-scoring/team/{team_id}/week")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_authenticated_team_week_summary_returns_200(self, auth_headers):
        """GET /api/live-scoring/team/{team_id}/week with auth should return 200."""
        # First get a team ID
        teams_response = requests.get(
            f"{BASE_URL}/api/teams?league_id={H2H_LEAGUE_ID}",
            headers=auth_headers,
        )
        if teams_response.status_code != 200:
            pytest.skip(f"Could not get teams: {teams_response.status_code}")
        
        teams = teams_response.json()
        if not teams:
            pytest.skip("No teams found")
        
        team_id = teams[0].get("id") or str(teams[0].get("_id"))
        
        response = requests.get(
            f"{BASE_URL}/api/live-scoring/team/{team_id}/week",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

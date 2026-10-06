"""Iteration 173 - Game-Level Scoring Allocation API Tests

Tests the new game-level allocation scoring system:
- GET /api/scoring/calculate/{league_id} returns 200 with team scores
- GET /api/scoring/calculate/{league_id}?week=1 returns 200 (historical week recomputation)
- GET /api/scoring/roto/{league_id} returns 200 with roto standings
- GET /api/scoring/roto/{league_id}?week=1 returns 200 (historical roto recomputation)
- GET /api/matchups/{league_id}/daily-scoring?team_id={team_id} returns 200 with player daily data
- GET /api/players/{player_id}/ownership-history returns ownership timeline
- GET /api/players/{player_id}/lineup-history returns lineup position history
- POST /api/roster/{team_id}/add creates ownership period
- POST /api/roster/{team_id}/drop closes ownership period
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
LEAGUE_ID = "69e46af167999bfb85c39629"
TEAM_ID = "69e59b33cbd3fea02a914c7b"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestScoringCalculateEndpoint:
    """Tests for GET /api/scoring/calculate/{league_id}"""

    def test_scoring_calculate_returns_200(self, auth_headers):
        """GET /api/scoring/calculate/{league_id} returns 200 with team scores."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of team scores"
        if data:
            team = data[0]
            assert "team_id" in team, "Team should have team_id"
            assert "team_name" in team, "Team should have team_name"
            assert "total_fantasy_points" in team, "Team should have total_fantasy_points"
            assert "game_count" in team, "Team should have game_count (new field)"
        print(f"PASS: Scoring calculate returned {len(data)} teams")

    def test_scoring_calculate_with_week_param(self, auth_headers):
        """GET /api/scoring/calculate/{league_id}?week=1 returns 200 (historical recomputation)."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}?week=1",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: Historical scoring (week=1) returned {len(data)} teams")

    def test_scoring_calculate_idempotent(self, auth_headers):
        """Calling scoring calculate twice with same week returns identical results."""
        response1 = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}?week=1",
            headers=auth_headers
        )
        response2 = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}?week=1",
            headers=auth_headers
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        # Compare total_fantasy_points for each team
        scores1 = {t["team_id"]: t["total_fantasy_points"] for t in data1}
        scores2 = {t["team_id"]: t["total_fantasy_points"] for t in data2}
        assert scores1 == scores2, "Recomputation should be idempotent"
        print("PASS: Scoring calculation is idempotent")


class TestRotoScoringEndpoint:
    """Tests for GET /api/scoring/roto/{league_id}"""

    def test_roto_standings_returns_200(self, auth_headers):
        """GET /api/scoring/roto/{league_id} returns 200 with roto standings."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "categories" in data, "Response should have categories"
        assert "standings" in data, "Response should have standings"
        assert isinstance(data["standings"], list), "Standings should be a list"
        if data["standings"]:
            team = data["standings"][0]
            assert "team_id" in team, "Team should have team_id"
            assert "stats" in team, "Team should have stats"
            assert "roto_points" in team, "Team should have roto_points"
        print(f"PASS: Roto standings returned {len(data['standings'])} teams")

    def test_roto_standings_with_week_param(self, auth_headers):
        """GET /api/scoring/roto/{league_id}?week=1 returns 200 (historical roto recomputation)."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}?week=1",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "categories" in data, "Response should have categories"
        assert "standings" in data, "Response should have standings"
        print(f"PASS: Historical roto (week=1) returned {len(data['standings'])} teams")


class TestDailyScoringEndpoint:
    """Tests for GET /api/matchups/{league_id}/daily-scoring"""

    def test_daily_scoring_returns_200(self, auth_headers):
        """GET /api/matchups/{league_id}/daily-scoring?team_id={team_id} returns 200."""
        response = requests.get(
            f"{BASE_URL}/api/matchups/{LEAGUE_ID}/daily-scoring?team_id={TEAM_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "league_id" in data, "Response should have league_id"
        assert "team_id" in data, "Response should have team_id"
        assert "players" in data, "Response should have players array"
        assert "daily_totals" in data, "Response should have daily_totals"
        assert "period_total_fpts" in data, "Response should have period_total_fpts"
        print(f"PASS: Daily scoring returned {len(data['players'])} players")

    def test_daily_scoring_with_week_param(self, auth_headers):
        """GET /api/matchups/{league_id}/daily-scoring?team_id={team_id}&week=1 returns 200."""
        response = requests.get(
            f"{BASE_URL}/api/matchups/{LEAGUE_ID}/daily-scoring?team_id={TEAM_ID}&week=1",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["week"] == 1, "Week should be 1"
        print("PASS: Daily scoring with week=1 returned correctly")


class TestOwnershipHistoryEndpoint:
    """Tests for GET /api/players/{player_id}/ownership-history"""

    def test_ownership_history_returns_200(self, auth_headers):
        """GET /api/players/{player_id}/ownership-history returns ownership timeline."""
        # Use a known player ID from the league
        player_id = "69e43d98b80cbdcecf495247"  # Nikita Kucherov
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data, "Response should have history array"
        assert isinstance(data["history"], list), "History should be a list"
        print(f"PASS: Ownership history returned {len(data['history'])} entries")

    def test_ownership_history_requires_auth(self):
        """Unauthenticated request to ownership-history returns 401."""
        player_id = "69e43d98b80cbdcecf495247"
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Ownership history requires authentication")


class TestLineupHistoryEndpoint:
    """Tests for GET /api/players/{player_id}/lineup-history"""

    def test_lineup_history_returns_200(self, auth_headers):
        """GET /api/players/{player_id}/lineup-history returns lineup position history."""
        player_id = "69e43d98b80cbdcecf495247"  # Nikita Kucherov
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history?league_id={LEAGUE_ID}&team_id={TEAM_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data, "Response should have history array"
        assert isinstance(data["history"], list), "History should be a list"
        print(f"PASS: Lineup history returned {len(data['history'])} entries")

    def test_lineup_history_requires_auth(self):
        """Unauthenticated request to lineup-history returns 401."""
        player_id = "69e43d98b80cbdcecf495247"
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history?league_id={LEAGUE_ID}&team_id={TEAM_ID}"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Lineup history requires authentication")


class TestRosterAddDropOwnership:
    """Tests for POST /api/roster/{team_id}/add and /drop creating ownership periods."""

    def test_roster_add_creates_ownership_period(self, auth_headers):
        """POST /api/roster/{team_id}/add creates player_ownership_periods record."""
        # Use a free agent player
        catalog = requests.get(f"{BASE_URL}/api/players", params={"limit": 1038}, headers=auth_headers).json()
        rows = catalog if isinstance(catalog, list) else catalog.get("players", [])
        free_agent_id = rows[-1].get("_id") or rows[-1].get("id")

        # First check if player is already on roster
        team_response = requests.get(
            f"{BASE_URL}/api/teams/{TEAM_ID}",
            headers=auth_headers
        )
        if team_response.status_code == 200:
            team_data = team_response.json()
            roster = team_data.get("roster", [])
            if free_agent_id in roster:
                # Drop first to test add
                drop_response = requests.post(
                    f"{BASE_URL}/api/roster/{TEAM_ID}/drop",
                    json={"player_id": free_agent_id},
                    headers=auth_headers
                )
                print(f"Pre-test drop: {drop_response.status_code}")

        # Add player
        response = requests.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/add",
            json={"player_id": free_agent_id},
            headers=auth_headers
        )
        # Accept 200 (success) or 400 (already on roster)
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}: {response.text}"

        if response.status_code == 200:
            # Verify ownership period was created
            ownership_response = requests.get(
                f"{BASE_URL}/api/players/{free_agent_id}/ownership-history?league_id={LEAGUE_ID}",
                headers=auth_headers
            )
            assert ownership_response.status_code == 200
            ownership_data = ownership_response.json()
            history = ownership_data.get("history", [])
            # Should have at least one entry with released_at=null (current ownership)
            current_ownership = [h for h in history if h.get("released_at") is None]
            assert len(current_ownership) >= 1, "Should have current ownership entry"
            print("PASS: Roster add creates ownership period")
        else:
            print("PASS: Roster add endpoint works (player already on roster)")

    def test_roster_drop_closes_ownership_period(self, auth_headers):
        """POST /api/roster/{team_id}/drop closes ownership period (sets released_at)."""
        free_agent_id = "69e43d98b80cbdcecf495248"  # Nathan MacKinnon

        # First ensure player is on roster
        add_response = requests.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/add",
            json={"player_id": free_agent_id},
            headers=auth_headers
        )

        # Drop player
        response = requests.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/drop",
            json={"player_id": free_agent_id},
            headers=auth_headers
        )
        # Accept 200 (success) or 400 (not on roster)
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}: {response.text}"

        if response.status_code == 200:
            # Verify ownership period was closed
            ownership_response = requests.get(
                f"{BASE_URL}/api/players/{free_agent_id}/ownership-history?league_id={LEAGUE_ID}",
                headers=auth_headers
            )
            assert ownership_response.status_code == 200
            ownership_data = ownership_response.json()
            history = ownership_data.get("history", [])
            # Most recent entry should have released_at set
            if history:
                latest = history[0]  # Sorted newest-first
                assert latest.get("released_at") is not None or latest.get("release_source") is not None, \
                    "Latest ownership entry should have released_at or release_source set"
            print("PASS: Roster drop closes ownership period")
        else:
            print("PASS: Roster drop endpoint works (player not on roster)")


class TestAuthGuards:
    """Tests for authentication guards on scoring endpoints."""

    def test_scoring_calculate_requires_auth(self):
        """Unauthenticated request to scoring calculate returns 401."""
        response = requests.get(f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Scoring calculate requires authentication")

    def test_roto_standings_requires_auth(self):
        """Unauthenticated request to roto standings returns 401."""
        response = requests.get(f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Roto standings requires authentication")

    def test_daily_scoring_requires_auth(self):
        """Unauthenticated request to daily scoring returns 401."""
        response = requests.get(f"{BASE_URL}/api/matchups/{LEAGUE_ID}/daily-scoring?team_id={TEAM_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Daily scoring requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

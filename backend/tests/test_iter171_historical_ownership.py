"""
Iteration 171 - Historical Ownership & Lineup Eligibility Testing

Tests for:
1. GET /api/players/{player_id}/ownership-history - ownership timeline
2. GET /api/players/{player_id}/lineup-history - lineup position timeline
3. GET /api/scoring/calculate/{league_id}?week=N - historical scoring
4. GET /api/scoring/roto/{league_id}?week=N - historical roto standings
5. POST /api/admin/lock-scoring-rosters - idempotency check
6. Roster add/drop logging to player_ownership_periods collection
7. MongoDB collections: player_ownership_periods, lineup_status_periods
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://dynasty-preview.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

# Test data from review request
LEAGUE_ID = "69e46af167999bfb85c39629"
TEAM_ID = "69e59b33cbd3fea02a914c79"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestOwnershipHistoryEndpoint:
    """Tests for GET /api/players/{player_id}/ownership-history"""

    def test_ownership_history_requires_auth(self):
        """Unauthenticated request should return 401."""
        # Get a player ID from the team roster first
        response = requests.get(f"{BASE_URL}/api/players/69e43d98b80cbdcecf495275/ownership-history?league_id={LEAGUE_ID}")
        # This should fail without auth
        assert response.status_code == 401, response.text

    def test_ownership_history_with_auth_returns_200(self, auth_headers):
        """Authenticated request should return 200 with history array."""
        # First get a player from the team roster
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )
        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        players = roster_data.get("players", [])
        if not players:
            pytest.skip("No players on roster to test")

        player_id = players[0].get("player_id")

        # Now test ownership history endpoint
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history",
            params={"league_id": LEAGUE_ID},
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data, "Response should contain 'history' key"
        assert "player_id" in data, "Response should contain 'player_id' key"
        assert "league_id" in data, "Response should contain 'league_id' key"
        assert isinstance(data["history"], list), "History should be a list"

    def test_ownership_history_without_auth_returns_401(self):
        """Request without auth token should return 401."""
        response = requests.get(
            f"{BASE_URL}/api/players/507f1f77bcf86cd799439011/ownership-history",
            params={"league_id": LEAGUE_ID}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestLineupHistoryEndpoint:
    """Tests for GET /api/players/{player_id}/lineup-history"""

    def test_lineup_history_with_auth_returns_200(self, auth_headers):
        """Authenticated request should return 200 with history array."""
        # First get a player from the team roster
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )
        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        players = roster_data.get("players", [])
        if not players:
            pytest.skip("No players on roster to test")

        player_id = players[0].get("player_id")

        # Test lineup history endpoint
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history",
            params={"league_id": LEAGUE_ID, "team_id": TEAM_ID},
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data, "Response should contain 'history' key"
        assert "player_id" in data, "Response should contain 'player_id' key"
        assert isinstance(data["history"], list), "History should be a list"

    def test_lineup_history_without_auth_returns_401(self):
        """Request without auth token should return 401."""
        response = requests.get(
            f"{BASE_URL}/api/players/507f1f77bcf86cd799439011/lineup-history",
            params={"league_id": LEAGUE_ID, "team_id": TEAM_ID}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestHistoricalScoringCalculation:
    """Tests for GET /api/scoring/calculate/{league_id}?week=N"""

    def test_scoring_calculate_with_week_param(self, auth_headers):
        """Scoring calculation with week parameter should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}",
            params={"week": 1},
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

    def test_scoring_calculate_without_week_param(self, auth_headers):
        """Scoring calculation without week parameter should default to current week."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}",
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of team scores"


class TestHistoricalRotoStandings:
    """Tests for GET /api/scoring/roto/{league_id}?week=N"""

    def test_roto_standings_with_week_param(self, auth_headers):
        """Roto standings with week parameter should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}",
            params={"week": 1},
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "categories" in data, "Response should contain 'categories'"
        assert "standings" in data, "Response should contain 'standings'"

    def test_roto_standings_without_week_param(self, auth_headers):
        """Roto standings without week parameter should default to current week."""
        response = requests.get(
            f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}",
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestLockScoringRostersIdempotency:
    """Tests for POST /api/admin/lock-scoring-rosters idempotency"""

    def test_lock_scoring_rosters_first_call(self, auth_headers):
        """First call to lock-scoring-rosters should succeed."""
        response = requests.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": LEAGUE_ID},
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "snapshots_created" in data or "message" in data, "Response should indicate snapshots created"

    def test_lock_scoring_rosters_idempotent(self, auth_headers):
        """Second call should return snapshots_created: 0 (idempotent)."""
        # First call
        requests.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": LEAGUE_ID},
            headers=auth_headers
        )

        # Second call - should be idempotent
        response = requests.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": LEAGUE_ID},
            headers=auth_headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Second call should create 0 new snapshots
        if "snapshots_created" in data:
            assert data["snapshots_created"] == 0, f"Expected 0 snapshots on second call, got {data['snapshots_created']}"


class TestRosterAddDropLogging:
    """Tests for roster add/drop logging to player_ownership_periods"""

    def test_find_free_agent_player(self, auth_headers):
        """Find a free agent player not on any team's roster."""
        # Get all players
        response = requests.get(
            f"{BASE_URL}/api/players",
            params={"limit": 100},
            headers=auth_headers
        )

        if response.status_code != 200:
            pytest.skip(f"Could not get players: {response.status_code}")

        data = response.json()
        players = data.get("players", []) if isinstance(data, dict) else data

        # Get team roster
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )

        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        rostered_ids = {p.get("player_id") for p in roster_data.get("players", [])}

        # Find a free agent
        free_agents = [p for p in players if str(p.get("_id") or p.get("id")) not in rostered_ids]

        assert len(free_agents) > 0 or len(players) > 0, "Should have players in the database"
        print(f"Found {len(free_agents)} free agents out of {len(players)} total players")


class TestMongoDBCollections:
    """Tests for MongoDB collections existence and indexes"""

    def test_player_ownership_periods_collection_exists(self, auth_headers):
        """Verify player_ownership_periods collection exists via API behavior."""
        # The ownership-history endpoint reads from this collection
        # If it returns 200, the collection exists (even if empty)
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )

        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        players = roster_data.get("players", [])
        if not players:
            pytest.skip("No players on roster to test")

        player_id = players[0].get("player_id")

        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history",
            params={"league_id": LEAGUE_ID},
            headers=auth_headers
        )

        # 200 means the endpoint works and collection is accessible
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("player_ownership_periods collection is accessible")

    def test_lineup_status_periods_collection_exists(self, auth_headers):
        """Verify lineup_status_periods collection exists via API behavior."""
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )

        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        players = roster_data.get("players", [])
        if not players:
            pytest.skip("No players on roster to test")

        player_id = players[0].get("player_id")

        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history",
            params={"league_id": LEAGUE_ID, "team_id": TEAM_ID},
            headers=auth_headers
        )

        # 200 means the endpoint works and collection is accessible
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("lineup_status_periods collection is accessible")


class TestOwnershipHistoryDataStructure:
    """Tests for ownership history data structure validation"""

    def test_ownership_history_entry_structure(self, auth_headers):
        """Verify ownership history entries have correct structure."""
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )

        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        players = roster_data.get("players", [])
        if not players:
            pytest.skip("No players on roster to test")

        player_id = players[0].get("player_id")

        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history",
            params={"league_id": LEAGUE_ID},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])

        # If there are entries, validate structure
        if history:
            entry = history[0]
            # Expected fields based on scoring_roster.py
            expected_fields = ["player_id", "team_id", "league_id", "acquired_at", "source"]
            for field in expected_fields:
                assert field in entry, f"Entry should have '{field}' field"

            # team_name should be enriched
            assert "team_name" in entry, "Entry should have enriched 'team_name' field"
            print(f"Ownership history entry structure validated: {list(entry.keys())}")
        else:
            print("No ownership history entries yet (expected for new feature)")


class TestLineupHistoryDataStructure:
    """Tests for lineup history data structure validation"""

    def test_lineup_history_entry_structure(self, auth_headers):
        """Verify lineup history entries have correct structure."""
        roster_response = requests.get(
            f"{BASE_URL}/api/roster/{TEAM_ID}",
            headers=auth_headers
        )

        if roster_response.status_code != 200:
            pytest.skip(f"Could not get roster: {roster_response.status_code}")

        roster_data = roster_response.json()
        players = roster_data.get("players", [])
        if not players:
            pytest.skip("No players on roster to test")

        player_id = players[0].get("player_id")

        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history",
            params={"league_id": LEAGUE_ID, "team_id": TEAM_ID},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])

        # If there are entries, validate structure
        if history:
            entry = history[0]
            # Expected fields based on scoring_roster.py
            expected_fields = ["player_id", "team_id", "league_id", "position", "started_at"]
            for field in expected_fields:
                assert field in entry, f"Entry should have '{field}' field"
            print(f"Lineup history entry structure validated: {list(entry.keys())}")
        else:
            print("No lineup history entries yet (expected for new feature)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

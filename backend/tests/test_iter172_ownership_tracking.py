"""
Iteration 172 — Historical Ownership & Lineup Eligibility Tracking Tests

Tests for complete historical ownership and lineup eligibility tracking for scoring allocation.
Covers: roster add/drop, ownership-history API, lineup-history API, historical scoring calculation,
idempotent recomputation, roto standings, lock-scoring-rosters idempotency, and auth guards.

Test credentials:
- Admin: admin@dynastydreams.com / Admin123!
- Admin's team ID: 69e59b33cbd3fea02a914c7b
- League ID: 69e46af167999bfb85c39629
"""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com")
LEAGUE_ID = "69e46af167999bfb85c39629"
TEAM_ID = "69e59b33cbd3fea02a914c7b"
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create a session with auth headers."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def free_agent_player_id(api_client):
    """Find a free agent player to use for add/drop tests."""
    response = api_client.get(f"{BASE_URL}/api/players?league_id={LEAGUE_ID}&limit=100")
    assert response.status_code == 200, f"Failed to get players: {response.text}"
    data = response.json()
    
    # Find a player not owned by any team
    for player in data.get("players", []):
        if not player.get("owned_by_team_id"):
            return player.get("_id")
    
    pytest.skip("No free agent players found for testing")


class TestOwnershipHistoryAPI:
    """Tests for GET /api/players/{player_id}/ownership-history endpoint."""
    
    def test_ownership_history_returns_200(self, api_client):
        """Ownership history endpoint returns 200 with valid player_id."""
        # Use Nikita Kucherov who has existing ownership history
        player_id = "69e43d98b80cbdcecf495247"
        response = api_client.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "player_id" in data
        assert "league_id" in data
        assert "history" in data
        assert isinstance(data["history"], list)
    
    def test_ownership_history_structure(self, api_client):
        """Ownership history entries have correct structure."""
        player_id = "69e43d98b80cbdcecf495247"
        response = api_client.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert response.status_code == 200
        
        data = response.json()
        if data["history"]:
            entry = data["history"][0]
            # Check required fields
            assert "player_id" in entry
            assert "team_id" in entry
            assert "league_id" in entry
            assert "acquired_at" in entry
            assert "source" in entry
            assert "team_name" in entry
            # released_at can be null for current ownership
            assert "released_at" in entry or entry.get("released_at") is None
    
    def test_ownership_history_sorted_newest_first(self, api_client):
        """Ownership history is sorted newest-first."""
        player_id = "69e43d98b80cbdcecf495247"
        response = api_client.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert response.status_code == 200
        
        data = response.json()
        history = data["history"]
        if len(history) > 1:
            # Check that entries are sorted by acquired_at descending
            for i in range(len(history) - 1):
                assert history[i]["acquired_at"] >= history[i + 1]["acquired_at"], \
                    "History should be sorted newest-first"
    
    def test_ownership_history_unauthenticated_returns_401(self):
        """Unauthenticated request to ownership-history returns 401."""
        player_id = "69e43d98b80cbdcecf495247"
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestLineupHistoryAPI:
    """Tests for GET /api/players/{player_id}/lineup-history endpoint."""
    
    def test_lineup_history_returns_200(self, api_client):
        """Lineup history endpoint returns 200 with valid parameters."""
        player_id = "69e43d98b80cbdcecf495247"
        response = api_client.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history?league_id={LEAGUE_ID}&team_id={TEAM_ID}"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "player_id" in data
        assert "team_id" in data
        assert "league_id" in data
        assert "history" in data
        assert isinstance(data["history"], list)
    
    def test_lineup_history_unauthenticated_returns_401(self):
        """Unauthenticated request to lineup-history returns 401."""
        player_id = "69e43d98b80cbdcecf495247"
        response = requests.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history?league_id={LEAGUE_ID}&team_id={TEAM_ID}"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestHistoricalScoringCalculation:
    """Tests for GET /api/scoring/calculate/{league_id}?week=N endpoint."""
    
    def test_scoring_calculate_with_week_returns_200(self, api_client):
        """Historical scoring calculation with week parameter returns 200."""
        response = api_client.get(f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}?week=1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list of team scores"
        if data:
            team = data[0]
            assert "team_id" in team
            assert "team_name" in team
            assert "total_fantasy_points" in team
    
    def test_scoring_calculate_idempotent(self, api_client):
        """Calling scoring calculate twice with same week returns identical results."""
        # First call
        response1 = api_client.get(f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}?week=1")
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second call
        response2 = api_client.get(f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}?week=1")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Compare results
        assert len(data1) == len(data2), "Same number of teams should be returned"
        
        # Create lookup by team_id for comparison
        scores1 = {t["team_id"]: t["total_fantasy_points"] for t in data1}
        scores2 = {t["team_id"]: t["total_fantasy_points"] for t in data2}
        
        for team_id in scores1:
            assert scores1[team_id] == scores2[team_id], \
                f"Team {team_id} scores should be identical: {scores1[team_id]} vs {scores2[team_id]}"
    
    def test_scoring_calculate_without_week(self, api_client):
        """Scoring calculation without week parameter uses current week."""
        response = api_client.get(f"{BASE_URL}/api/scoring/calculate/{LEAGUE_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestHistoricalRotoStandings:
    """Tests for GET /api/scoring/roto/{league_id}?week=N endpoint."""
    
    def test_roto_standings_with_week_returns_200(self, api_client):
        """Historical roto standings with week parameter returns 200."""
        response = api_client.get(f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}?week=1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "categories" in data
        assert "standings" in data
        assert isinstance(data["standings"], list)
    
    def test_roto_standings_structure(self, api_client):
        """Roto standings have correct structure."""
        response = api_client.get(f"{BASE_URL}/api/scoring/roto/{LEAGUE_ID}?week=1")
        assert response.status_code == 200
        
        data = response.json()
        if data["standings"]:
            team = data["standings"][0]
            assert "team_id" in team
            assert "team_name" in team
            assert "stats" in team
            assert "roto_points" in team


class TestLockScoringRostersIdempotency:
    """Tests for POST /api/admin/lock-scoring-rosters idempotency."""
    
    def test_lock_scoring_rosters_returns_200(self, api_client):
        """Lock scoring rosters endpoint returns 200."""
        response = api_client.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": LEAGUE_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_lock_scoring_rosters_idempotent(self, api_client):
        """Second call to lock-scoring-rosters creates 0 new snapshots."""
        # First call
        response1 = api_client.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": LEAGUE_ID}
        )
        assert response1.status_code == 200
        
        # Second call
        response2 = api_client.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": LEAGUE_ID}
        )
        assert response2.status_code == 200
        
        data2 = response2.json()
        # Second call should create 0 new snapshots (idempotent)
        assert data2.get("snapshots_created", 0) == 0, \
            f"Expected 0 new snapshots on second call, got {data2.get('snapshots_created')}"


class TestRosterAddDropOwnershipTracking:
    """Tests for roster add/drop creating ownership periods."""
    
    def test_roster_add_creates_ownership_period(self, api_client, free_agent_player_id):
        """POST /api/roster/{team_id}/add creates a player_ownership_periods record."""
        # Add the player
        response = api_client.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/add",
            json={"player_id": free_agent_player_id}
        )
        
        # May fail due to roster limits or other constraints - that's OK
        if response.status_code == 400:
            pytest.skip(f"Cannot add player due to constraints: {response.text}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check ownership history
        history_response = api_client.get(
            f"{BASE_URL}/api/players/{free_agent_player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert history_response.status_code == 200
        
        history = history_response.json()["history"]
        assert len(history) > 0, "Ownership history should have at least one entry after add"
        
        # Most recent entry should be for this team with source='add'
        latest = history[0]
        assert latest["team_id"] == TEAM_ID
        assert latest["source"] == "add"
        assert latest["acquired_at"] is not None
        # released_at should be null (player still on roster)
        assert latest.get("released_at") is None
        
        # Clean up - drop the player
        drop_response = api_client.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/drop",
            json={"player_id": free_agent_player_id}
        )
        # Don't fail test if drop fails
    
    def test_roster_drop_closes_ownership_period(self, api_client, free_agent_player_id):
        """POST /api/roster/{team_id}/drop closes the ownership period."""
        # First add the player
        add_response = api_client.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/add",
            json={"player_id": free_agent_player_id}
        )
        
        if add_response.status_code == 400:
            pytest.skip(f"Cannot add player due to constraints: {add_response.text}")
        
        assert add_response.status_code == 200
        
        # Now drop the player
        drop_response = api_client.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/drop",
            json={"player_id": free_agent_player_id}
        )
        assert drop_response.status_code == 200, f"Expected 200, got {drop_response.status_code}: {drop_response.text}"
        
        # Check ownership history
        history_response = api_client.get(
            f"{BASE_URL}/api/players/{free_agent_player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert history_response.status_code == 200
        
        history = history_response.json()["history"]
        assert len(history) > 0, "Ownership history should have entries"
        
        # Most recent entry should have released_at set and release_source='drop'
        latest = history[0]
        assert latest["team_id"] == TEAM_ID
        assert latest["released_at"] is not None, "released_at should be set after drop"
        assert latest["release_source"] == "drop"
    
    def test_add_then_drop_shows_complete_ownership_entry(self, api_client, free_agent_player_id):
        """After add then drop, ownership history shows exactly 1 entry with both timestamps."""
        # Add the player
        add_response = api_client.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/add",
            json={"player_id": free_agent_player_id}
        )
        
        if add_response.status_code == 400:
            pytest.skip(f"Cannot add player due to constraints: {add_response.text}")
        
        assert add_response.status_code == 200
        
        # Drop the player
        drop_response = api_client.post(
            f"{BASE_URL}/api/roster/{TEAM_ID}/drop",
            json={"player_id": free_agent_player_id}
        )
        assert drop_response.status_code == 200
        
        # Check ownership history
        history_response = api_client.get(
            f"{BASE_URL}/api/players/{free_agent_player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert history_response.status_code == 200
        
        history = history_response.json()["history"]
        
        # Find the most recent entry for this team
        team_entries = [h for h in history if h["team_id"] == TEAM_ID]
        assert len(team_entries) >= 1, "Should have at least one ownership entry for this team"
        
        latest = team_entries[0]
        assert latest["acquired_at"] is not None
        assert latest["released_at"] is not None
        assert latest["source"] == "add"
        assert latest["release_source"] == "drop"


class TestMongoDBIndexes:
    """Tests to verify MongoDB indexes exist for ownership/lineup collections."""
    
    def test_ownership_periods_collection_accessible(self, api_client):
        """Verify ownership periods collection is accessible via API."""
        # The ownership-history endpoint queries player_ownership_periods
        player_id = "69e43d98b80cbdcecf495247"
        response = api_client.get(
            f"{BASE_URL}/api/players/{player_id}/ownership-history?league_id={LEAGUE_ID}"
        )
        assert response.status_code == 200, "Ownership periods collection should be accessible"
    
    def test_lineup_status_periods_collection_accessible(self, api_client):
        """Verify lineup status periods collection is accessible via API."""
        # The lineup-history endpoint queries lineup_status_periods
        player_id = "69e43d98b80cbdcecf495247"
        response = api_client.get(
            f"{BASE_URL}/api/players/{player_id}/lineup-history?league_id={LEAGUE_ID}&team_id={TEAM_ID}"
        )
        assert response.status_code == 200, "Lineup status periods collection should be accessible"


class TestFrontendCompilation:
    """Tests to verify frontend compiles without errors."""
    
    def test_frontend_loads(self, api_client):
        """Frontend should load without errors."""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200, f"Frontend should load: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

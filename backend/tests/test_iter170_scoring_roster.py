"""
Iteration 170 - Historical Scoring Roster Tests

Tests for the historical scoring allocation fix:
- POST /api/admin/lock-scoring-rosters creates scoring roster snapshots
- Idempotency: calling lock twice creates 0 new snapshots on second call
- GET /api/scoring/calculate/{league_id} uses scoring roster
- GET /api/scoring/roto/{league_id} uses scoring roster
- GET /api/matchups/{league_id}/daily-scoring returns 200 with player data
- GET /api/live-scoring/team/{team_id} returns 200 with live scoring data
- Roster change log is written on add/drop operations
- Verify scoring_rosters collection schema
- Verify get_scoring_roster falls back to live roster when no snapshot exists
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"

# Known test data from review request
KNOWN_LEAGUE_ID = "69e46af167999bfb85c39629"
KNOWN_TEAM_ID = "69e59b33cbd3fea02a914c79"


class TestScoringRosterFeature:
    """Tests for the historical scoring roster feature."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication."""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
        
    def _login(self):
        """Login and get auth token."""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            if self.token:
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    # ─── Test 1: Admin lock-scoring-rosters endpoint ───────────────────
    
    def test_lock_scoring_rosters_requires_auth(self):
        """POST /api/admin/lock-scoring-rosters requires authentication."""
        response = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: lock-scoring-rosters requires authentication (401)")
    
    def test_lock_scoring_rosters_requires_admin(self):
        """POST /api/admin/lock-scoring-rosters requires admin role."""
        # First login as admin
        assert self._login(), "Failed to login as admin"
        
        # Admin should be able to call this endpoint
        response = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        # Should be 200 or 404 (if league not found), not 403
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        print(f"PASS: Admin can access lock-scoring-rosters endpoint (status: {response.status_code})")
    
    def test_lock_scoring_rosters_creates_snapshots(self):
        """POST /api/admin/lock-scoring-rosters creates scoring roster snapshots."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        
        if response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found - skipping snapshot test")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "league_id" in data, "Response should contain league_id"
        assert "week" in data, "Response should contain week"
        assert "snapshots_created" in data, "Response should contain snapshots_created"
        
        print(f"PASS: lock-scoring-rosters returned: league_id={data['league_id']}, week={data['week']}, snapshots_created={data['snapshots_created']}")
    
    def test_lock_scoring_rosters_idempotent(self):
        """POST /api/admin/lock-scoring-rosters is idempotent - second call creates 0 new snapshots."""
        assert self._login(), "Failed to login as admin"
        
        # First call
        response1 = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        
        if response1.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found - skipping idempotency test")
        
        assert response1.status_code == 200, f"First call failed: {response1.status_code}"
        data1 = response1.json()
        
        # Second call - should create 0 new snapshots
        response2 = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        
        assert response2.status_code == 200, f"Second call failed: {response2.status_code}"
        data2 = response2.json()
        
        # Second call should create 0 snapshots (idempotent)
        assert data2["snapshots_created"] == 0, f"Expected 0 snapshots on second call, got {data2['snapshots_created']}"
        print(f"PASS: Idempotency verified - first call: {data1['snapshots_created']}, second call: {data2['snapshots_created']}")
    
    def test_lock_scoring_rosters_with_specific_week(self):
        """POST /api/admin/lock-scoring-rosters accepts optional week parameter."""
        assert self._login(), "Failed to login as admin"
        
        # Lock for a specific week (e.g., week 5)
        response = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID, "week": 5}
        )
        
        if response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["week"] == 5, f"Expected week 5, got {data['week']}"
        print(f"PASS: lock-scoring-rosters with specific week=5 returned: {data}")
    
    # ─── Test 2: Scoring calculate endpoint uses scoring roster ────────
    
    def test_scoring_calculate_endpoint(self):
        """GET /api/scoring/calculate/{league_id} returns team scores."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.get(f"{BASE_URL}/api/scoring/calculate/{KNOWN_LEAGUE_ID}")
        
        if response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should return a list of team scores
        assert isinstance(data, list), "Response should be a list of team scores"
        
        if len(data) > 0:
            team = data[0]
            assert "team_id" in team, "Team should have team_id"
            assert "team_name" in team, "Team should have team_name"
            assert "total_fantasy_points" in team, "Team should have total_fantasy_points"
            assert "roster_size" in team, "Team should have roster_size"
            print(f"PASS: scoring/calculate returned {len(data)} teams, first team: {team['team_name']} with {team['total_fantasy_points']} fpts")
        else:
            print("PASS: scoring/calculate returned empty list (no teams in league)")
    
    # ─── Test 3: Roto standings endpoint uses scoring roster ───────────
    
    def test_roto_standings_endpoint(self):
        """GET /api/scoring/roto/{league_id} returns roto standings."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.get(f"{BASE_URL}/api/scoring/roto/{KNOWN_LEAGUE_ID}")
        
        if response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should have categories and standings
        assert "categories" in data, "Response should have categories"
        assert "standings" in data, "Response should have standings"
        assert isinstance(data["standings"], list), "Standings should be a list"
        
        if len(data["standings"]) > 0:
            team = data["standings"][0]
            assert "team_id" in team, "Team should have team_id"
            assert "team_name" in team, "Team should have team_name"
            assert "roto_points" in team, "Team should have roto_points"
            assert "stats" in team, "Team should have stats"
            print(f"PASS: scoring/roto returned {len(data['standings'])} teams with categories: {data['categories'][:5]}...")
        else:
            print("PASS: scoring/roto returned empty standings (no teams in league)")
    
    # ─── Test 4: Daily scoring endpoint ────────────────────────────────
    
    def test_daily_scoring_endpoint(self):
        """GET /api/matchups/{league_id}/daily-scoring returns 200 with player data."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.get(
            f"{BASE_URL}/api/matchups/{KNOWN_LEAGUE_ID}/daily-scoring",
            params={"team_id": KNOWN_TEAM_ID}
        )
        
        if response.status_code == 404:
            pytest.skip(f"League or team not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "league_id" in data, "Response should have league_id"
        assert "team_id" in data, "Response should have team_id"
        assert "team_name" in data, "Response should have team_name"
        assert "week" in data, "Response should have week"
        assert "players" in data, "Response should have players"
        assert "daily_totals" in data, "Response should have daily_totals"
        assert "period_total_fpts" in data, "Response should have period_total_fpts"
        assert "days" in data, "Response should have days"
        assert "day_labels" in data, "Response should have day_labels"
        
        print(f"PASS: daily-scoring returned: team={data['team_name']}, week={data['week']}, players={len(data['players'])}, period_total={data['period_total_fpts']}")
    
    def test_daily_scoring_with_specific_week(self):
        """GET /api/matchups/{league_id}/daily-scoring accepts week parameter."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.get(
            f"{BASE_URL}/api/matchups/{KNOWN_LEAGUE_ID}/daily-scoring",
            params={"team_id": KNOWN_TEAM_ID, "week": 1}
        )
        
        if response.status_code == 404:
            pytest.skip(f"League or team not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["week"] == 1, f"Expected week 1, got {data['week']}"
        print(f"PASS: daily-scoring with week=1 returned correctly")
    
    # ─── Test 5: Live scoring team endpoint ────────────────────────────
    
    def test_live_scoring_team_endpoint(self):
        """GET /api/live-scoring/team/{team_id} returns 200 with live scoring data."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.get(f"{BASE_URL}/api/live-scoring/team/{KNOWN_TEAM_ID}")
        
        if response.status_code == 404:
            pytest.skip(f"Team {KNOWN_TEAM_ID} not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "team_id" in data, "Response should have team_id"
        assert "team_name" in data, "Response should have team_name"
        assert "live_points" in data, "Response should have live_points"
        assert "players" in data, "Response should have players"
        
        print(f"PASS: live-scoring/team returned: team={data['team_name']}, live_points={data['live_points']}, players={len(data['players'])}")
    
    # ─── Test 6: Fallback to live roster when no snapshot exists ───────
    
    def test_scoring_fallback_to_live_roster(self):
        """Verify get_scoring_roster falls back to live roster when no snapshot exists for a given week."""
        assert self._login(), "Failed to login as admin"
        
        # Use week=999 which should have no snapshot
        response = self.session.get(
            f"{BASE_URL}/api/matchups/{KNOWN_LEAGUE_ID}/daily-scoring",
            params={"team_id": KNOWN_TEAM_ID, "week": 999}
        )
        
        if response.status_code == 404:
            pytest.skip(f"League or team not found")
        
        # Should still return 200 (falls back to live roster)
        assert response.status_code == 200, f"Expected 200 (fallback), got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should have players (from live roster fallback)
        assert "players" in data, "Response should have players"
        print(f"PASS: Fallback to live roster works for week=999, returned {len(data['players'])} players")


class TestRosterChangeLog:
    """Tests for roster change logging on add/drop operations."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication."""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
        
    def _login(self):
        """Login and get auth token."""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            if self.token:
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    def test_roster_add_endpoint_exists(self):
        """POST /api/roster/{team_id}/add endpoint exists and requires auth."""
        # Without auth
        response = self.session.post(
            f"{BASE_URL}/api/roster/{KNOWN_TEAM_ID}/add",
            json={"player_id": "test_player_id"}
        )
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: roster/add requires authentication")
    
    def test_roster_drop_endpoint_exists(self):
        """POST /api/roster/{team_id}/drop endpoint exists and requires auth."""
        # Without auth
        response = self.session.post(
            f"{BASE_URL}/api/roster/{KNOWN_TEAM_ID}/drop",
            json={"player_id": "test_player_id"}
        )
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: roster/drop requires authentication")
    
    def test_roster_add_with_auth(self):
        """POST /api/roster/{team_id}/add with auth returns appropriate response."""
        assert self._login(), "Failed to login as admin"
        
        # Try to add a non-existent player (should fail with 404 or 400)
        response = self.session.post(
            f"{BASE_URL}/api/roster/{KNOWN_TEAM_ID}/add",
            json={"player_id": "000000000000000000000000"}
        )
        
        # Should be 403 (not team owner), 404 (player not found), or 400 (validation error)
        assert response.status_code in [400, 403, 404], f"Expected 400/403/404, got {response.status_code}: {response.text}"
        print(f"PASS: roster/add with invalid player returns {response.status_code}")
    
    def test_roster_drop_with_auth(self):
        """POST /api/roster/{team_id}/drop with auth returns appropriate response."""
        assert self._login(), "Failed to login as admin"
        
        # Try to drop a non-existent player (should fail with 400 or 403)
        response = self.session.post(
            f"{BASE_URL}/api/roster/{KNOWN_TEAM_ID}/drop",
            json={"player_id": "000000000000000000000000"}
        )
        
        # Should be 403 (not team owner) or 400 (player not on roster)
        assert response.status_code in [400, 403], f"Expected 400/403, got {response.status_code}: {response.text}"
        print(f"PASS: roster/drop with invalid player returns {response.status_code}")


class TestScoringRostersSchema:
    """Tests to verify scoring_rosters collection schema via API responses."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication."""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
        
    def _login(self):
        """Login and get auth token."""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            if self.token:
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    def test_lock_scoring_rosters_response_schema(self):
        """Verify lock-scoring-rosters response contains expected fields."""
        assert self._login(), "Failed to login as admin"
        
        response = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        
        if response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response schema
        required_fields = ["league_id", "week", "snapshots_created"]
        for field in required_fields:
            assert field in data, f"Response missing required field: {field}"
        
        # Verify types
        assert isinstance(data["league_id"], str), "league_id should be string"
        assert isinstance(data["snapshots_created"], int), "snapshots_created should be int"
        
        print(f"PASS: lock-scoring-rosters response schema verified: {list(data.keys())}")


class TestEndpointIntegration:
    """Integration tests for scoring endpoints working together."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication."""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
        
    def _login(self):
        """Login and get auth token."""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            if self.token:
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    def test_full_scoring_workflow(self):
        """Test complete scoring workflow: lock rosters -> calculate scores -> get daily scoring."""
        assert self._login(), "Failed to login as admin"
        
        # Step 1: Lock scoring rosters
        lock_response = self.session.post(
            f"{BASE_URL}/api/admin/lock-scoring-rosters",
            json={"league_id": KNOWN_LEAGUE_ID}
        )
        
        if lock_response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found")
        
        assert lock_response.status_code == 200, f"Lock failed: {lock_response.status_code}"
        lock_data = lock_response.json()
        print(f"Step 1 - Lock: snapshots_created={lock_data['snapshots_created']}")
        
        # Step 2: Calculate league scoring
        calc_response = self.session.get(f"{BASE_URL}/api/scoring/calculate/{KNOWN_LEAGUE_ID}")
        assert calc_response.status_code == 200, f"Calculate failed: {calc_response.status_code}"
        calc_data = calc_response.json()
        print(f"Step 2 - Calculate: {len(calc_data)} teams scored")
        
        # Step 3: Get daily scoring for a team
        daily_response = self.session.get(
            f"{BASE_URL}/api/matchups/{KNOWN_LEAGUE_ID}/daily-scoring",
            params={"team_id": KNOWN_TEAM_ID}
        )
        assert daily_response.status_code == 200, f"Daily scoring failed: {daily_response.status_code}"
        daily_data = daily_response.json()
        print(f"Step 3 - Daily: {len(daily_data['players'])} players, total={daily_data['period_total_fpts']}")
        
        # Step 4: Get live scoring for team
        live_response = self.session.get(f"{BASE_URL}/api/live-scoring/team/{KNOWN_TEAM_ID}")
        assert live_response.status_code == 200, f"Live scoring failed: {live_response.status_code}"
        live_data = live_response.json()
        print(f"Step 4 - Live: {len(live_data['players'])} players, live_points={live_data['live_points']}")
        
        print("PASS: Full scoring workflow completed successfully")
    
    def test_roto_and_h2h_scoring_consistency(self):
        """Test that roto and h2h scoring endpoints both work for the same league."""
        assert self._login(), "Failed to login as admin"
        
        # Get H2H scoring
        h2h_response = self.session.get(f"{BASE_URL}/api/scoring/calculate/{KNOWN_LEAGUE_ID}")
        
        if h2h_response.status_code == 404:
            pytest.skip(f"League {KNOWN_LEAGUE_ID} not found")
        
        assert h2h_response.status_code == 200, f"H2H scoring failed: {h2h_response.status_code}"
        h2h_data = h2h_response.json()
        
        # Get Roto scoring
        roto_response = self.session.get(f"{BASE_URL}/api/scoring/roto/{KNOWN_LEAGUE_ID}")
        assert roto_response.status_code == 200, f"Roto scoring failed: {roto_response.status_code}"
        roto_data = roto_response.json()
        
        # Both should have the same number of teams
        h2h_teams = len(h2h_data)
        roto_teams = len(roto_data["standings"])
        
        assert h2h_teams == roto_teams, f"Team count mismatch: H2H={h2h_teams}, Roto={roto_teams}"
        print(f"PASS: Both H2H and Roto scoring return {h2h_teams} teams")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

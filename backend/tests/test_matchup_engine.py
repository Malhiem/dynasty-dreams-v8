"""
Test Matchup Simulation Engine - Dynasty Dreams Iteration 5
Tests: Schedule generation, matchup retrieval, week simulation, standings updates
"""
import uuid
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
TEST_USER_EMAIL = "matchup_test_user@test.com"
TEST_USER_PASSWORD = "TestPass123!"


class TestMatchupEngine:
    """Test the weekly matchup simulation engine"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session and authenticate"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if login_resp.status_code != 200:
            pytest.skip("Admin login failed - skipping matchup tests")

        self.user = login_resp.json()
        self.user_id = self.user.get("id")

        # Get or create a test league
        leagues_resp = self.session.get(f"{BASE_URL}/api/leagues?my_leagues=true")
        leagues = leagues_resp.json()

        if leagues:
            self.league_id = leagues[0]["id"]
            self.is_commissioner = leagues[0]["commissioner_id"] == self.user_id
        else:
            # Create a test league
            create_resp = self.session.post(f"{BASE_URL}/api/leagues", json={
                "name": "TEST_Matchup_League",
                "format": "dynasty",
                "scoring_format": "head_to_head",
                "max_teams": 4,
                "draft_type": "snake",
                "roster_spots": 20
            })
            if create_resp.status_code == 200:
                self.league_id = create_resp.json()["id"]
                self.is_commissioner = True
            else:
                pytest.skip("Could not create test league")

        yield

    def test_generate_schedule_requires_auth(self):
        """Test that schedule generation requires authentication"""
        # Use a new session without auth
        new_session = requests.Session()
        resp = new_session.post(f"{BASE_URL}/api/matchups/generate-schedule", json={
            "league_id": self.league_id,
            "num_weeks": 4
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: Schedule generation requires authentication")

    def test_generate_schedule_commissioner_only(self):
        """Test that only commissioner can generate schedule"""
        if not self.is_commissioner:
            pytest.skip("User is not commissioner")

        # This should work for commissioner
        resp = self.session.post(f"{BASE_URL}/api/matchups/generate-schedule", json={
            "league_id": self.league_id,
            "num_weeks": 4
        })
        # May fail if not enough teams, but should not be 403
        if resp.status_code == 400:
            # Need at least 2 teams
            print(f"PASS: Commissioner access granted (needs more teams: {resp.json()})")
        else:
            assert resp.status_code in [200, 400], f"Expected 200 or 400, got {resp.status_code}: {resp.text}"
            print(f"PASS: Commissioner can generate schedule - {resp.json()}")

    def test_get_matchups_endpoint(self):
        """Test GET /api/matchups/{league_id} returns matchups"""
        resp = self.session.get(f"{BASE_URL}/api/matchups/{self.league_id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of matchups"
        print(f"PASS: Get matchups returns {len(data)} matchups")

    def test_get_matchups_with_week_filter(self):
        """Test GET /api/matchups/{league_id}?week=1 filters by week"""
        resp = self.session.get(f"{BASE_URL}/api/matchups/{self.league_id}?week=1")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of matchups"
        # All matchups should be week 1
        for m in data:
            assert m.get("week") == 1, f"Expected week 1, got {m.get('week')}"
        print(f"PASS: Get matchups with week filter returns {len(data)} week 1 matchups")

    def test_get_current_week_endpoint(self):
        """Test GET /api/matchups/{league_id}/current-week returns current week"""
        resp = self.session.get(f"{BASE_URL}/api/matchups/{self.league_id}/current-week")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "week" in data, "Response should contain 'week'"
        assert "matchups" in data, "Response should contain 'matchups'"
        assert isinstance(data["matchups"], list), "Matchups should be a list"
        print(f"PASS: Current week is {data['week']} with {len(data['matchups'])} matchups")

    def test_simulate_week_requires_auth(self):
        """Test that week simulation requires authentication"""
        new_session = requests.Session()
        resp = new_session.post(f"{BASE_URL}/api/matchups/simulate-week", json={
            "league_id": self.league_id,
            "week": 1
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: Week simulation requires authentication")

    def test_simulate_week_commissioner_only(self):
        """Test that only commissioner can simulate week"""
        if not self.is_commissioner:
            pytest.skip("User is not commissioner")

        resp = self.session.post(f"{BASE_URL}/api/matchups/simulate-week", json={
            "league_id": self.league_id,
            "week": 1
        })
        # May fail if no scheduled matchups, but should not be 403
        if resp.status_code == 400:
            print(f"PASS: Commissioner access granted (no scheduled matchups: {resp.json()})")
        else:
            assert resp.status_code in [200, 400], f"Expected 200 or 400, got {resp.status_code}: {resp.text}"
            print(f"PASS: Commissioner can simulate week - {resp.json()}")

    def test_get_results_endpoint(self):
        """Test GET /api/matchups/{league_id}/results?week=1 returns completed results"""
        resp = self.session.get(f"{BASE_URL}/api/matchups/{self.league_id}/results?week=1")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of results"
        # All results should be completed
        for m in data:
            assert m.get("status") == "completed", f"Expected completed status, got {m.get('status')}"
        print(f"PASS: Get results returns {len(data)} completed matchups")

    def test_standings_endpoint(self):
        """Test GET /api/leagues/{league_id}/standings returns standings"""
        resp = self.session.get(f"{BASE_URL}/api/leagues/{self.league_id}/standings")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        payload = resp.json()
        # New shape: {standings:[...], has_divisions, has_conferences, divisions, conferences}
        data = payload["standings"] if isinstance(payload, dict) else payload
        assert isinstance(data, list), "Expected list of standings"
        # Check standings structure
        for team in data:
            assert "team_id" in team, "Standing should have team_id"
            assert "team_name" in team, "Standing should have team_name"
            assert "wins" in team, "Standing should have wins"
            assert "losses" in team, "Standing should have losses"
            assert "rank" in team, "Standing should have rank"
        print(f"PASS: Standings returns {len(data)} teams")


class TestMatchupEngineE2E:
    """End-to-end test for matchup engine with full flow"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if login_resp.status_code != 200:
            pytest.skip("Admin login failed")

        self.user = login_resp.json()
        yield

    def test_full_matchup_flow(self):
        """Test complete flow: create league -> add teams -> generate schedule -> simulate"""
        # 1. Create a new test league
        league_resp = self.session.post(f"{BASE_URL}/api/leagues", json={
            "name": f"TEST_E2E_Matchup_{datetime.now().timestamp()}",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 4,
            "draft_type": "snake",
            "roster_spots": 20
        })
        assert league_resp.status_code == 200, f"Failed to create league: {league_resp.text}"
        league = league_resp.json()
        league_id = league["id"]
        print(f"Created test league: {league['name']} (ID: {league_id})")

        # League creation already provides the commissioner's team.
        teams_response = self.session.get(f"{BASE_URL}/api/teams?league_id={league_id}")
        assert teams_response.status_code == 200, teams_response.text
        assert len(teams_response.json()) == 1
        team1 = teams_response.json()[0]

        # 3. Commissioners can generate with open slots before invitees join.
        gen_resp = self.session.post(f"{BASE_URL}/api/matchups/generate-schedule", json={
            "league_id": league_id,
            "num_weeks": 4
        })
        assert gen_resp.status_code == 200, gen_resp.text
        placeholders = self.session.get(f"{BASE_URL}/api/matchups/{league_id}").json()
        assert any(str(m.get("home_team_id", "")).startswith("open_slot_") or str(m.get("away_team_id", "")).startswith("open_slot_") for m in placeholders)
        print("PASS: Schedule generated with explicit open slots")

        # 4. Register and login as second user to create second team
        user2_email = f"test_matchup_user2_{datetime.now().timestamp()}@test.com"
        reg_resp = self.session.post(f"{BASE_URL}/api/auth/register", json={"username": "fixture_" + uuid.uuid4().hex[:16],
            "email": user2_email,
            "password": "TestPass123!",
            "name": "Test User 2"
        })
        if reg_resp.status_code == 200:
            # Create second team
            team2_resp = self.session.post(f"{BASE_URL}/api/teams", json={
                "name": "TEST_Team_Beta",
                "league_id": league_id
            })
            if team2_resp.status_code == 200:
                team2 = team2_resp.json()
                print(f"Created team 2: {team2['name']}")

                # All schedule slots must have real teams before settlement.
                open_sim = self.session.post(f"{BASE_URL}/api/matchups/simulate-week", json={"league_id": league_id, "week": 1})
                # Second manager cannot simulate, regardless of unfilled slots.
                assert open_sim.status_code == 403, open_sim.text
                for i in range(2):
                    reg = self.session.post(f"{BASE_URL}/api/auth/register", json={"email": f"TEST_matchup_{uuid.uuid4().hex}@test.com", "password": "TestPass123!", "username": "fixture_" + uuid.uuid4().hex[:16]})
                    assert reg.status_code == 200, reg.text
                    added = self.session.post(f"{BASE_URL}/api/teams", json={"name": f"TEST_Team_{i+3}", "league_id": league_id})
                    assert added.status_code == 200, added.text

                # Re-login as admin to generate schedule
                self.session.post(f"{BASE_URL}/api/auth/login", json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                })

                # 5. Generate schedule with 2 teams
                gen_resp = self.session.post(f"{BASE_URL}/api/matchups/generate-schedule", json={
                    "league_id": league_id,
                    "num_weeks": 4
                })
                assert gen_resp.status_code == 200, f"Failed to generate schedule: {gen_resp.text}"
                gen_data = gen_resp.json()
                print(f"Generated schedule: {gen_data}")

                # 6. Verify matchups were created
                matchups_resp = self.session.get(f"{BASE_URL}/api/matchups/{league_id}")
                assert matchups_resp.status_code == 200
                matchups = matchups_resp.json()
                assert len(matchups) > 0, "Should have matchups after generation"
                print(f"Verified {len(matchups)} matchups created")

                # 7. Get current week
                current_resp = self.session.get(f"{BASE_URL}/api/matchups/{league_id}/current-week")
                assert current_resp.status_code == 200
                current = current_resp.json()
                assert current["week"] == 1, "Current week should be 1"
                print(f"Current week: {current['week']} with {len(current['matchups'])} matchups")

                # 8. Simulate week 1
                sim_resp = self.session.post(f"{BASE_URL}/api/matchups/simulate-week", json={
                    "league_id": league_id,
                    "week": 1
                })
                assert sim_resp.status_code == 200, f"Failed to simulate: {sim_resp.text}"
                sim_data = sim_resp.json()
                print(f"Simulated week 1: {sim_data}")

                # 9. Verify results
                results_resp = self.session.get(f"{BASE_URL}/api/matchups/{league_id}/results?week=1")
                assert results_resp.status_code == 200
                results = results_resp.json()
                assert len(results) > 0, "Should have results after simulation"
                for r in results:
                    assert r["status"] == "completed", "All matchups should be completed"
                print(f"Verified {len(results)} completed matchups")

                # 10. Check standings updated
                standings_resp = self.session.get(f"{BASE_URL}/api/leagues/{league_id}/standings")
                assert standings_resp.status_code == 200
                standings = standings_resp.json()["standings"]
                print(f"Standings after simulation: {standings}")

                # Verify W/L/T records updated (empty rosters = 0-0 tie)
                total_wins = sum(t.get("wins", 0) for t in standings)
                total_losses = sum(t.get("losses", 0) for t in standings)
                total_ties = sum(t.get("ties", 0) for t in standings)
                assert total_wins > 0 or total_losses > 0 or total_ties > 0, "W/L/T records should be updated"
                print(f"PASS: Full matchup flow completed successfully (W:{total_wins} L:{total_losses} T:{total_ties})")
            else:
                print(f"Could not create team 2: {team2_resp.text}")
        else:
            print(f"Could not register user 2: {reg_resp.text}")


class TestSidebarMigration:
    """Test that pages use sidebar layout (AppLayout)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed")
        yield

    def test_api_health(self):
        """Test API is healthy"""
        resp = self.session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print("PASS: API is healthy")

    def test_leagues_endpoint(self):
        """Test leagues endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/leagues")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        print("PASS: Leagues endpoint works")

    def test_players_endpoint(self):
        """Test players endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/players")
        assert resp.status_code == 200
        data = resp.json()
        assert "players" in data
        print(f"PASS: Players endpoint returns {data.get('total', 0)} players")

    def test_drafts_endpoint(self):
        """Test drafts endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/drafts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        print("PASS: Drafts endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

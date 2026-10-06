"""
Test Suite for Dynasty Dreams Roster Management & Scoring Engine
Tests: Roster CRUD, Scoring Config, Fantasy Points Calculation, Rotisserie Standings
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
TEST_LEAGUE_ID = "69e46af167999bfb85c3962a"


@pytest.fixture(scope="module")
def free_roster_player(_global_pollution_sweep):
    """A genuinely unowned player, independent of seeded search ordering."""
    from pymongo import MongoClient
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        pid = db.players.insert_one({"name": "Roster CRUD free player", "position": "C", "salary": 1_000_000}).inserted_id
        try:
            yield str(pid)
        finally:
            db.teams.update_many({"roster": str(pid)}, {"$pull": {"roster": str(pid)}, "$unset": {f"lineup.{pid}": ""}})
            db.players.delete_one({"_id": pid})


class TestSetup:
    """Setup and authentication tests"""

    @pytest.fixture(scope="class")
    def session(self):
        """Create a requests session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Authenticated session with admin user"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.text}")
        return session

    def test_health_check(self, session):
        """Verify API is healthy"""
        response = session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        print("✓ Health check passed")

    def test_admin_login(self, session):
        """Test admin login"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == ADMIN_EMAIL
        print(f"✓ Admin login successful: {data['name']}")


class TestRosterManagement:
    """Roster Management API Tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.text}")
        return s

    @pytest.fixture(scope="class")
    def test_team_id(self, auth_session):
        """Get or create a test team"""
        # Get teams in test league
        response = auth_session.get(f"{BASE_URL}/api/teams?league_id={TEST_LEAGUE_ID}")
        if response.status_code == 200 and len(response.json()) > 0:
            uid = auth_session.get(f"{BASE_URL}/api/auth/me").json()["id"]
            team = next(t for t in response.json() if t["owner_id"] == uid)
            return team["id"]
        pytest.skip("No team found in test league")

    @pytest.fixture(scope="class")
    def test_player_id(self, free_roster_player):
        return free_roster_player

    def test_get_roster_empty(self, auth_session, test_team_id):
        """GET /api/roster/{team_id} - Get team roster (may be empty)"""
        response = auth_session.get(f"{BASE_URL}/api/roster/{test_team_id}")
        assert response.status_code == 200
        data = response.json()
        assert "team_id" in data
        assert "team_name" in data
        assert "players" in data
        assert isinstance(data["players"], list)
        print(f"✓ Get roster: {data['team_name']} has {len(data['players'])} players")

    def test_get_roster_invalid_team(self, auth_session):
        """GET /api/roster/{team_id} - Invalid team returns 404"""
        response = auth_session.get(f"{BASE_URL}/api/roster/000000000000000000000000")
        assert response.status_code == 404
        print("✓ Invalid team returns 404")

    def test_add_player_to_roster(self, auth_session, test_team_id, test_player_id):
        """POST /api/roster/{team_id}/add - Add player to roster"""
        response = auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/add", json={
            "player_id": test_player_id
        })
        # Could be 200 (success) or 400 (already on roster)
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            assert "message" in response.json()
            print(f"✓ Added player to roster: {response.json()['message']}")
        else:
            print(f"✓ Player already on roster (expected): {response.json()}")

    def test_add_player_validates_ownership(self, auth_session):
        """POST /api/roster/{team_id}/add - Validates team ownership"""
        # Try to add to a non-existent team
        response = auth_session.post(f"{BASE_URL}/api/roster/000000000000000000000000/add", json={
            "player_id": "000000000000000000000000"
        })
        assert response.status_code in [403, 404]
        print("✓ Add player validates team ownership/existence")

    def test_get_roster_with_players(self, auth_session, test_team_id):
        """GET /api/roster/{team_id} - Verify roster has fantasy points"""
        response = auth_session.get(f"{BASE_URL}/api/roster/{test_team_id}")
        assert response.status_code == 200
        data = response.json()
        if len(data["players"]) > 0:
            player = data["players"][0]
            # Verify player data structure
            assert "player_id" in player
            assert "name" in player
            assert "position" in player
            assert "fantasy_points" in player
            print(f"✓ Roster player has fantasy_points: {player['name']} = {player['fantasy_points']} FPTS")
        else:
            print("✓ Roster is empty (no players to verify)")

    def test_drop_player_from_roster(self, auth_session, test_team_id, test_player_id):
        """POST /api/roster/{team_id}/drop - Drop player from roster"""
        # First ensure player is on roster
        auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/add", json={
            "player_id": test_player_id
        })

        # Now drop
        response = auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/drop", json={
            "player_id": test_player_id
        })
        # Could be 200 (success) or 400 (not on roster)
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            assert "message" in response.json()
            print(f"✓ Dropped player: {response.json()['message']}")
        else:
            print(f"✓ Player not on roster: {response.json()}")

    def test_drop_player_validates_ownership(self, auth_session):
        """POST /api/roster/{team_id}/drop - Validates team ownership"""
        response = auth_session.post(f"{BASE_URL}/api/roster/000000000000000000000000/drop", json={
            "player_id": "000000000000000000000000"
        })
        assert response.status_code in [403, 404]
        print("✓ Drop player validates team ownership/existence")


class TestScoringConfig:
    """Scoring Configuration API Tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.text}")
        return s

    def test_get_scoring_config_defaults(self, auth_session):
        """GET /api/scoring/config - Returns defaults if no config saved"""
        response = auth_session.get(f"{BASE_URL}/api/scoring/config?league_id={TEST_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()
        assert "skater_scoring" in data
        assert "goalie_scoring" in data
        assert "roto_categories" in data
        # Verify default values
        assert data["skater_scoring"]["goals"] == 3
        assert data["skater_scoring"]["assists"] == 2
        assert data["goalie_scoring"]["wins"] == 5
        print(f"✓ Scoring config defaults: Goals={data['skater_scoring']['goals']}, Assists={data['skater_scoring']['assists']}")

    def test_save_scoring_config(self, auth_session):
        """POST /api/scoring/config - Save scoring configuration"""
        config = {
            "league_id": TEST_LEAGUE_ID,
            "skater_scoring": {
                "goals": 4,
                "assists": 3,
                "plus_minus": 1,
                "penalty_minutes": -0.5,
                "power_play_goals": 1.5,
                "power_play_points": 0.5,
                "short_handed_goals": 2,
                "short_handed_points": 1,
                "game_winning_goals": 1,
                "shots": 0.3
            },
            "goalie_scoring": {
                "wins": 6,
                "losses": -2,
                "saves": 0.25,
                "goals_against": -1,
                "shutouts": 4,
                "overtime_losses": 0
            },
            "roto_categories": ["goals", "assists", "plus_minus", "wins", "shutouts"]
        }
        response = auth_session.post(f"{BASE_URL}/api/scoring/config", json=config)
        assert response.status_code == 200
        assert "message" in response.json()
        print(f"✓ Saved scoring config: {response.json()['message']}")

    def test_get_saved_scoring_config(self, auth_session):
        """GET /api/scoring/config - Returns saved config"""
        response = auth_session.get(f"{BASE_URL}/api/scoring/config?league_id={TEST_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()
        # Verify saved values (from previous test)
        assert data["skater_scoring"]["goals"] == 4
        assert data["skater_scoring"]["assists"] == 3
        assert data["goalie_scoring"]["wins"] == 6
        print(f"✓ Retrieved saved config: Goals={data['skater_scoring']['goals']}, Wins={data['goalie_scoring']['wins']}")

    def test_save_scoring_config_requires_auth(self):
        """POST /api/scoring/config - Requires authentication"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/scoring/config", json={
            "league_id": TEST_LEAGUE_ID,
            "skater_scoring": {"goals": 3},
            "goalie_scoring": {"wins": 5},
            "roto_categories": []
        })
        assert response.status_code == 401
        print("✓ Save scoring config requires authentication")


class TestScoringCalculation:
    """Scoring Calculation API Tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.text}")
        return s

    def test_calculate_league_scoring(self, auth_session):
        """GET /api/scoring/calculate/{league_id} - Calculate fantasy points per team"""
        response = auth_session.get(f"{BASE_URL}/api/scoring/calculate/{TEST_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            team = data[0]
            assert "team_id" in team
            assert "team_name" in team
            assert "owner_name" in team
            assert "roster_size" in team
            assert "total_fantasy_points" in team
            print(f"✓ League scoring calculated: {len(data)} teams, top team: {team['team_name']} = {team['total_fantasy_points']} FPTS")
        else:
            print("✓ League scoring calculated: No teams in league")

    def test_calculate_roto_standings(self, auth_session):
        """GET /api/scoring/roto/{league_id} - Calculate rotisserie standings"""
        response = auth_session.get(f"{BASE_URL}/api/scoring/roto/{TEST_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "standings" in data
        assert isinstance(data["categories"], list)
        assert isinstance(data["standings"], list)
        print(f"✓ Roto standings calculated: {len(data['categories'])} categories, {len(data['standings'])} teams")
        if len(data["standings"]) > 0:
            team = data["standings"][0]
            assert "team_id" in team
            assert "team_name" in team
            assert "stats" in team
            assert "roto_points" in team
            print(f"  Top team: {team['team_name']} = {team['roto_points']} roto points")


class TestRosterLimits:
    """Roster Limit Validation Tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.text}")
        return s

    @pytest.fixture(scope="class")
    def test_team_id(self, auth_session):
        """Get test team"""
        response = auth_session.get(f"{BASE_URL}/api/teams?league_id={TEST_LEAGUE_ID}")
        if response.status_code == 200 and len(response.json()) > 0:
            uid = auth_session.get(f"{BASE_URL}/api/auth/me").json()["id"]
            return next(t["id"] for t in response.json() if t["owner_id"] == uid)
        pytest.skip("No team found")

    def test_add_duplicate_player_fails(self, auth_session, test_team_id, free_roster_player):
        """Adding same player twice should fail"""
        player_id = free_roster_player

        # Add player first time
        auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/add", json={
            "player_id": player_id
        })

        # Try to add again
        response = auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/add", json={
            "player_id": player_id
        })
        assert response.status_code == 400
        assert "already" in response.json().get("detail", "").lower()
        print("✓ Duplicate player add correctly rejected")

        # Cleanup - drop the player
        auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/drop", json={
            "player_id": player_id
        })

    def test_drop_nonexistent_player_fails(self, auth_session, test_team_id):
        """Dropping player not on roster should fail"""
        response = auth_session.post(f"{BASE_URL}/api/roster/{test_team_id}/drop", json={
            "player_id": "000000000000000000000000"
        })
        assert response.status_code in [400, 404]
        print("✓ Drop non-existent player correctly rejected")


class TestExistingFeatures:
    """Verify existing features still work"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.text}")
        return s

    def test_leagues_endpoint(self, auth_session):
        """GET /api/leagues - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/leagues")
        assert response.status_code == 200
        print(f"✓ Leagues endpoint: {len(response.json())} leagues")

    def test_teams_endpoint(self, auth_session):
        """GET /api/teams - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/teams")
        assert response.status_code == 200
        print(f"✓ Teams endpoint: {len(response.json())} teams")

    def test_players_endpoint(self, auth_session):
        """GET /api/players - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/players?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        assert "total" in data
        print(f"✓ Players endpoint: {data['total']} total players")

    def test_trade_block_endpoint(self, auth_session):
        """GET /api/trade-block - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/trade-block")
        assert response.status_code == 200
        print(f"✓ Trade block endpoint: {len(response.json())} items")

    def test_trades_endpoint(self, auth_session):
        """GET /api/trades - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        print(f"✓ Trades endpoint: {len(response.json())} trades")

    def test_waivers_available_endpoint(self, auth_session):
        """GET /api/waivers/available - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/waivers/available")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        print(f"✓ Waivers available endpoint: {len(data['players'])} players")

    def test_drafts_endpoint(self, auth_session):
        """GET /api/drafts - Still works"""
        response = auth_session.get(f"{BASE_URL}/api/drafts")
        assert response.status_code == 200
        print(f"✓ Drafts endpoint: {len(response.json())} drafts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

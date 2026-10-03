"""
Iteration 6 Backend Tests:
- Player Detail API (GET /api/players/{id})
- Commissioner Page APIs (waivers, trades, teams, matchups)
- WebSocket endpoints (Socket.IO)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
CONNOR_MCDAVID_ID = "69e43d98b80cbdcecf495275"


class TestHealthAndAuth:
    """Basic health and authentication tests"""

    def test_health_endpoint(self):
        """Test API health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health endpoint returns healthy status")

    def test_admin_login(self):
        """Test admin login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == ADMIN_EMAIL
        print(f"PASS: Admin login successful, user_id: {data['id']}")
        return response.cookies


class TestPlayerDetailAPI:
    """Tests for Player Detail endpoint - GET /api/players/{id}"""

    def test_get_player_by_id_skater(self):
        """Test getting a skater player by ID (Connor McDavid)"""
        response = requests.get(f"{BASE_URL}/api/players/{CONNOR_MCDAVID_ID}")
        assert response.status_code == 200
        data = response.json()

        # Verify player data structure
        assert data["_id"] == CONNOR_MCDAVID_ID
        assert data["name"] == "Connor McDavid"
        assert data["position"] == "C"
        assert data["team"] == "EDM"

        # Verify skater stats are present
        assert "goals" in data
        assert "assists" in data
        assert "points" in data
        assert "plus_minus" in data
        assert "games_played" in data
        assert "power_play_goals" in data
        assert "power_play_points" in data
        assert "shots" in data
        assert "shooting_pct" in data

        print(f"PASS: Player detail for {data['name']} - {data['goals']}G, {data['assists']}A, {data['points']}P")

    def test_get_player_by_id_goalie(self):
        """Test getting a goalie player by ID"""
        # First find a goalie
        response = requests.get(f"{BASE_URL}/api/players?position=G&limit=1")
        assert response.status_code == 200
        data = response.json()

        if data["players"]:
            goalie_id = data["players"][0]["_id"]

            # Get goalie detail
            response = requests.get(f"{BASE_URL}/api/players/{goalie_id}")
            assert response.status_code == 200
            goalie = response.json()

            assert goalie["position"] == "G"
            # Verify goalie-specific stats
            assert "wins" in goalie or goalie.get("player_type") == "goalie"
            print(f"PASS: Goalie detail for {goalie['name']} - Position: {goalie['position']}")
        else:
            pytest.skip("No goalies found in database")

    def test_get_player_not_found(self):
        """Test 404 for non-existent player"""
        fake_id = "000000000000000000000000"
        response = requests.get(f"{BASE_URL}/api/players/{fake_id}")
        assert response.status_code == 404
        print("PASS: Returns 404 for non-existent player")

    def test_get_player_invalid_id(self):
        """Test error handling for invalid player ID format"""
        response = requests.get(f"{BASE_URL}/api/players/invalid-id")
        assert response.status_code in [400, 422, 500]  # Invalid ObjectId
        print("PASS: Returns error for invalid player ID format")


class TestCommissionerAPIs:
    """Tests for Commissioner page APIs"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.cookies = response.cookies
        self.user_id = response.json().get("id")

    def test_get_my_leagues_as_commissioner(self):
        """Test getting leagues where user is commissioner"""
        response = requests.get(f"{BASE_URL}/api/leagues?my_leagues=true", cookies=self.cookies)
        assert response.status_code == 200
        leagues = response.json()

        # Filter for commissioner leagues
        commissioner_leagues = [l for l in leagues if l.get("commissioner_id") == self.user_id]
        print(f"PASS: Found {len(commissioner_leagues)} leagues where user is commissioner")
        return commissioner_leagues

    def test_get_teams_for_league(self):
        """Test getting teams for a league"""
        # First get a league
        response = requests.get(f"{BASE_URL}/api/leagues?my_leagues=true", cookies=self.cookies)
        leagues = response.json()

        if leagues:
            league_id = leagues[0]["id"]
            response = requests.get(f"{BASE_URL}/api/teams?league_id={league_id}", cookies=self.cookies)
            assert response.status_code == 200
            teams = response.json()

            # Verify team structure
            if teams:
                team = teams[0]
                assert "id" in team
                assert "name" in team
                assert "wins" in team
                assert "losses" in team
                assert "ties" in team
                assert "points_for" in team
                assert "points_against" in team
                print(f"PASS: Got {len(teams)} teams for league, first team: {team['name']} ({team['wins']}-{team['losses']}-{team['ties']})")
            else:
                print("PASS: Teams endpoint works (no teams in league)")
        else:
            pytest.skip("No leagues found")

    def test_get_pending_waiver_claims(self):
        """Test getting pending waiver claims for commissioner"""
        response = requests.get(f"{BASE_URL}/api/leagues?my_leagues=true", cookies=self.cookies)
        leagues = response.json()

        if leagues:
            league_id = leagues[0]["id"]
            response = requests.get(f"{BASE_URL}/api/waivers/claims?league_id={league_id}&status=pending", cookies=self.cookies)
            assert response.status_code == 200
            claims = response.json()
            print(f"PASS: Got {len(claims)} pending waiver claims")
        else:
            pytest.skip("No leagues found")

    def test_get_pending_trades(self):
        """Test getting pending trades for commissioner"""
        response = requests.get(f"{BASE_URL}/api/leagues?my_leagues=true", cookies=self.cookies)
        leagues = response.json()

        if leagues:
            league_id = leagues[0]["id"]
            response = requests.get(f"{BASE_URL}/api/trades?league_id={league_id}&status=pending", cookies=self.cookies)
            assert response.status_code == 200
            trades = response.json()
            print(f"PASS: Got {len(trades)} pending trades")
        else:
            pytest.skip("No leagues found")

    def test_get_current_week_matchups(self):
        """Test getting current week matchups"""
        response = requests.get(f"{BASE_URL}/api/leagues?my_leagues=true", cookies=self.cookies)
        leagues = response.json()

        if leagues:
            league_id = leagues[0]["id"]
            response = requests.get(f"{BASE_URL}/api/matchups/{league_id}/current-week", cookies=self.cookies)
            # May return 404 if no schedule generated
            assert response.status_code in [200, 404]
            if response.status_code == 200:
                data = response.json()
                print(f"PASS: Current week: {data.get('week', 'N/A')}, matchups: {len(data.get('matchups', []))}")
            else:
                print("PASS: No schedule generated yet (404 expected)")
        else:
            pytest.skip("No leagues found")

    def test_generate_schedule_requires_auth(self):
        """Test that generate schedule requires authentication"""
        response = requests.post(f"{BASE_URL}/api/matchups/generate-schedule", json={
            "league_id": "fake_id",
            "num_weeks": 18
        })
        assert response.status_code == 401
        print("PASS: Generate schedule requires authentication")

    def test_simulate_week_requires_auth(self):
        """Test that simulate week requires authentication"""
        response = requests.post(f"{BASE_URL}/api/matchups/simulate-week", json={
            "league_id": "fake_id",
            "week": 1
        })
        assert response.status_code == 401
        print("PASS: Simulate week requires authentication")

    def test_process_waivers_requires_auth(self):
        """Test that process waivers requires authentication"""
        response = requests.post(f"{BASE_URL}/api/waivers/process?league_id=fake_id")
        assert response.status_code == 401
        print("PASS: Process waivers requires authentication")


class TestDraftAPIs:
    """Tests for Draft APIs used by DraftRoomPage"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.cookies = response.cookies

    def test_get_drafts(self):
        """Test getting list of drafts"""
        response = requests.get(f"{BASE_URL}/api/drafts", cookies=self.cookies)
        assert response.status_code == 200
        drafts = response.json()
        print(f"PASS: Got {len(drafts)} drafts")
        return drafts

    def test_get_draft_eligible_players(self):
        """Test getting eligible players for a draft"""
        # First get a draft
        response = requests.get(f"{BASE_URL}/api/drafts", cookies=self.cookies)
        drafts = response.json()

        if drafts:
            draft_id = drafts[0]["_id"]
            response = requests.get(f"{BASE_URL}/api/drafts/{draft_id}/eligible-players?limit=10", cookies=self.cookies)
            assert response.status_code == 200
            data = response.json()
            assert "players" in data
            print(f"PASS: Got {len(data['players'])} eligible players for draft")
        else:
            pytest.skip("No drafts found")

    def test_get_draft_board(self):
        """Test getting draft board"""
        response = requests.get(f"{BASE_URL}/api/drafts", cookies=self.cookies)
        drafts = response.json()

        if drafts:
            draft_id = drafts[0]["_id"]
            response = requests.get(f"{BASE_URL}/api/drafts/{draft_id}/board", cookies=self.cookies)
            assert response.status_code == 200
            data = response.json()
            assert "board" in data
            assert "current_pick" in data
            assert "status" in data
            print(f"PASS: Draft board - status: {data['status']}, current_pick: {data['current_pick']}")
        else:
            pytest.skip("No drafts found")


class TestWebSocketEndpoints:
    """Tests for WebSocket-related functionality"""

    def test_socket_io_endpoint_exists(self):
        """Test that Socket.IO endpoint is accessible"""
        # Socket.IO uses polling as fallback, test the polling endpoint
        response = requests.get(f"{BASE_URL}/api/socket.io/?EIO=4&transport=polling")
        # Socket.IO returns 200 with session info or 400 for bad request
        assert response.status_code in [200, 400]
        print(f"PASS: Socket.IO endpoint accessible (status: {response.status_code})")


class TestPlayersListAPI:
    """Tests for Players list endpoint with filters"""

    def test_get_players_list(self):
        """Test getting players list"""
        response = requests.get(f"{BASE_URL}/api/players?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        print(f"PASS: Got {len(data['players'])} players, total: {data['total']}")

    def test_get_players_with_search(self):
        """Test searching players by name"""
        response = requests.get(f"{BASE_URL}/api/players?search=McDavid&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert any("McDavid" in p["name"] for p in data["players"])
        print(f"PASS: Search for 'McDavid' returned {len(data['players'])} results")

    def test_get_players_by_position(self):
        """Test filtering players by position"""
        response = requests.get(f"{BASE_URL}/api/players?position=C&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert all(p["position"] == "C" for p in data["players"])
        print(f"PASS: Position filter 'C' returned {len(data['players'])} centers")

    def test_get_goalies(self):
        """Test getting goalie players"""
        response = requests.get(f"{BASE_URL}/api/players?position=G&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert all(p["position"] == "G" for p in data["players"])
        print(f"PASS: Got {len(data['players'])} goalies")


class TestSidebarNavigation:
    """Tests for sidebar navigation endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.cookies = response.cookies

    def test_dashboard_data(self):
        """Test dashboard endpoint"""
        response = requests.get(f"{BASE_URL}/api/leagues?my_leagues=true", cookies=self.cookies)
        assert response.status_code == 200
        print("PASS: Dashboard data (leagues) accessible")

    def test_trade_block_endpoint(self):
        """Test trade block endpoint"""
        response = requests.get(f"{BASE_URL}/api/trade-block", cookies=self.cookies)
        assert response.status_code == 200
        print("PASS: Trade block endpoint accessible")

    def test_transactions_endpoint(self):
        """Test transactions (trades) endpoint"""
        response = requests.get(f"{BASE_URL}/api/trades", cookies=self.cookies)
        assert response.status_code == 200
        print("PASS: Transactions endpoint accessible")

    def test_waivers_available_endpoint(self):
        """Test waivers available players endpoint"""
        response = requests.get(f"{BASE_URL}/api/waivers/available?limit=10", cookies=self.cookies)
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        print(f"PASS: Waivers available endpoint - {len(data['players'])} players")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

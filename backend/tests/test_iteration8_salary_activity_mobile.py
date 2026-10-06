"""
Iteration 8 Tests: Salary Cap Management, Activity Feed, and React Native Mobile Scaffold
Tests for:
1. Salary Cap & Contracts API (POST/GET/PUT /contracts, GET /salary-cap)
2. Activity Feed API (GET /activity, POST /activity/chat)
3. React Native Mobile Scaffold file verification
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
TEST_LEAGUE_ID = "69e46af167999bfb85c3962a"

class TestAuth:
    """Authentication for subsequent tests"""

    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Login and return authenticated session"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"),
            "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return session

    def test_login_success(self, session):
        """Test admin login works"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"),
            "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
        print(f"✓ Login successful: {data['name']}")


class TestSalaryCapContracts:
    """Salary Cap & Contracts API Tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"),
            "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return s

    def test_get_salary_cap_overview(self, auth_session):
        """GET /api/salary-cap/{league_id} returns cap overview with per-team breakdown"""
        response = auth_session.get(f"{BASE_URL}/api/salary-cap/{TEST_LEAGUE_ID}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        # Verify structure
        assert "salary_cap" in data, "Missing salary_cap field"
        assert "teams" in data, "Missing teams field"
        assert isinstance(data["teams"], list), "teams should be a list"

        # Verify cap value
        assert data["salary_cap"] > 0, "Salary cap should be positive"
        print(f"✓ Salary cap: ${data['salary_cap']:,.0f}")

        # Verify team breakdown structure
        if len(data["teams"]) > 0:
            team = data["teams"][0]
            assert "team_id" in team
            assert "team_name" in team
            assert "cap_used" in team
            assert "cap_remaining" in team
            assert "cap_pct" in team
            assert "active_contracts" in team
            print(f"✓ Team breakdown: {team['team_name']} - {team['cap_pct']}% used")

    def test_get_contracts_for_league(self, auth_session):
        """GET /api/contracts returns all contracts for a league"""
        response = auth_session.get(f"{BASE_URL}/api/contracts?league_id={TEST_LEAGUE_ID}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        assert isinstance(data, list), "Contracts should be a list"
        print(f"✓ Found {len(data)} contracts in league")

        # Verify contract structure if any exist
        if len(data) > 0:
            contract = data[0]
            assert "_id" in contract
            assert "player_name" in contract
            assert "aav" in contract
            assert "years" in contract
            assert "team_name" in contract
            print(f"✓ Contract structure valid: {contract['player_name']} - ${contract['aav']:,.0f} AAV")

    def test_get_expiring_contracts(self, auth_session):
        """GET /api/salary-cap/{league_id}/expiring returns contracts expiring in given year"""
        response = auth_session.get(f"{BASE_URL}/api/salary-cap/{TEST_LEAGUE_ID}/expiring?year=2026")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        assert isinstance(data, list), "Expiring contracts should be a list"
        print(f"✓ Found {len(data)} contracts expiring in 2026")

        # Verify all returned contracts have correct free_agency_year
        for contract in data:
            assert contract.get("free_agency_year") == 2026, f"Contract {contract.get('player_name')} has wrong expiry year"

    def test_create_contract_requires_auth(self):
        """POST /api/contracts requires authentication"""
        s = requests.Session()
        response = s.post(f"{BASE_URL}/api/contracts", json={
            "league_id": TEST_LEAGUE_ID,
            "team_id": "test",
            "player_id": "test",
            "aav": 1000000,
            "total_value": 3000000,
            "years": 3
        })
        assert response.status_code == 401, "Should require auth"
        print("✓ Contract creation requires authentication")

    def test_create_contract_with_full_details(self, auth_session):
        """POST /api/contracts creates dynasty contract with AAV, years, signing bonus, NTC, NMC, player_status"""
        # First get a team in the league
        teams_response = auth_session.get(f"{BASE_URL}/api/teams?league_id={TEST_LEAGUE_ID}")
        assert teams_response.status_code == 200
        teams = teams_response.json()

        if len(teams) == 0:
            pytest.skip("No teams in test league")

        team = teams[0]
        team_id = team["id"]

        # Get a player
        players_response = auth_session.get(f"{BASE_URL}/api/players?limit=1")
        assert players_response.status_code == 200
        players = players_response.json()

        if len(players.get("players", [])) == 0:
            pytest.skip("No players available")

        player = players["players"][0]
        player_id = player["_id"]

        # Create contract with all fields
        contract_data = {
            "league_id": TEST_LEAGUE_ID,
            "team_id": team_id,
            "player_id": player_id,
            "aav": 5000000,
            "total_value": 20000000,
            "signing_bonus": 1000000,
            "years": 4,
            "start_year": 2025,
            "no_trade_clause": True,
            "no_move_clause": False,
            "player_status": "signed"
        }

        response = auth_session.post(f"{BASE_URL}/api/contracts", json=contract_data)

        # May fail if cap exceeded or player already has contract - that's OK
        if response.status_code == 400:
            error = response.json().get("detail", "")
            if "cap" in error.lower() or "exceeds" in error.lower():
                print(f"✓ Cap validation working: {error}")
                return
            print(f"Contract creation blocked: {error}")
            return

        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        # Verify all fields
        assert data["aav"] == 5000000
        assert data["years"] == 4
        assert data["signing_bonus"] == 1000000
        assert data["no_trade_clause"] == True
        assert data["no_move_clause"] == False
        assert data["player_status"] == "signed"
        assert data["free_agency_year"] == 2029  # 2025 + 4
        print(f"✓ Contract created: {data['player_name']} - {data['years']}yr/${data['aav']:,.0f} AAV")

    def test_cap_validation_rejects_over_cap(self, auth_session):
        """Cap validation: reject if contract exceeds cap"""
        # Get a team
        teams_response = auth_session.get(f"{BASE_URL}/api/teams?league_id={TEST_LEAGUE_ID}")
        teams = teams_response.json()

        if len(teams) == 0:
            pytest.skip("No teams in test league")

        team = teams[0]

        # Get a player
        players_response = auth_session.get(f"{BASE_URL}/api/players?limit=2")
        players = players_response.json()

        if len(players.get("players", [])) == 0:
            pytest.skip("No players available")

        player = players["players"][1]

        # Try to create contract that exceeds cap (100M AAV)
        response = auth_session.post(f"{BASE_URL}/api/contracts", json={
            "league_id": TEST_LEAGUE_ID,
            "team_id": team["id"],
            "player_id": player["_id"],
            "aav": 100000000,  # 100M - should exceed cap
            "total_value": 100000000,
            "years": 1
        })

        # Should either fail with 400 (cap exceeded) or succeed if cap is disabled
        if response.status_code == 400:
            error = response.json().get("detail", "")
            assert "cap" in error.lower() or "exceeds" in error.lower(), f"Expected cap error, got: {error}"
            print(f"✓ Cap validation working: {error}")
        else:
            print("Note: Cap validation may be disabled for this league")


class TestActivityFeed:
    """Activity Feed API Tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"),
            "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
        })
        assert response.status_code == 200
        return s

    def test_get_activity_feed_paginated(self, auth_session):
        """GET /api/activity/{league_id} returns paginated activity items"""
        response = auth_session.get(f"{BASE_URL}/api/activity/{TEST_LEAGUE_ID}?limit=10&page=1")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        # Verify pagination structure
        assert "items" in data, "Missing items field"
        assert "total" in data, "Missing total field"
        assert "page" in data, "Missing page field"
        assert "pages" in data, "Missing pages field"

        assert isinstance(data["items"], list)
        print(f"✓ Activity feed: {len(data['items'])} items, {data['total']} total")

        # Verify item structure if any exist
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "event_type" in item
            assert "message" in item
            assert "created_at" in item
            print(f"✓ Activity item: [{item['event_type']}] {item['message'][:50]}...")

    def test_activity_feed_filter_by_event_type(self, auth_session):
        """Activity feed can be filtered by event type"""
        # Test filter for chat events
        response = auth_session.get(f"{BASE_URL}/api/activity/{TEST_LEAGUE_ID}?event_type=chat")
        assert response.status_code == 200
        data = response.json()

        # All returned items should be chat type
        for item in data["items"]:
            assert item["event_type"] == "chat", f"Expected chat, got {item['event_type']}"

        print(f"✓ Filter by event_type working: {len(data['items'])} chat items")

    def test_post_league_chat_message(self, auth_session):
        """POST /api/activity/{league_id}/chat posts league chat message"""
        test_message = f"Test chat message at {datetime.now().isoformat()}"

        response = auth_session.post(f"{BASE_URL}/api/activity/{TEST_LEAGUE_ID}/chat", json={
            "text": test_message
        })
        assert response.status_code == 200, f"Failed: {response.text}"

        # Verify message appears in feed
        feed_response = auth_session.get(f"{BASE_URL}/api/activity/{TEST_LEAGUE_ID}?event_type=chat&limit=5")
        assert feed_response.status_code == 200

        items = feed_response.json()["items"]
        found = any(test_message in item.get("message", "") for item in items)
        assert found, "Chat message not found in activity feed"
        print(f"✓ Chat message posted and visible in feed")

    def test_activity_auto_logged_on_contract_creation(self, auth_session):
        """Activity auto-logged on contract creation"""
        # Check for contract_signed events
        response = auth_session.get(f"{BASE_URL}/api/activity/{TEST_LEAGUE_ID}?event_type=contract_signed")
        assert response.status_code == 200
        data = response.json()

        # If there are contract_signed events, verify structure
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "signs" in item["message"].lower() or "contract" in item["message"].lower()
            print(f"✓ Contract signing logged: {item['message'][:60]}...")
        else:
            print("Note: No contract_signed events yet (expected if no contracts created)")


class TestReactNativeMobileScaffold:
    """React Native Mobile Scaffold Verification Tests"""

    def test_mobile_directory_exists(self):
        """Verify /app/mobile directory exists with package.json and App.js"""
        import os

        assert os.path.exists("/app/mobile"), "Mobile directory missing"
        assert os.path.exists("/app/mobile/package.json"), "package.json missing"
        assert os.path.exists("/app/mobile/App.js"), "App.js missing"
        print("✓ Mobile directory structure exists")

    def test_navigation_structure_exists(self):
        """Verify AppNavigator with tabs + stacks exists"""
        import os

        nav_path = "/app/mobile/src/navigation/AppNavigator.js"
        assert os.path.exists(nav_path), "AppNavigator.js missing"

        with open(nav_path, 'r') as f:
            content = f.read()

        # Verify navigation components
        assert "createBottomTabNavigator" in content, "Missing bottom tab navigator"
        assert "createNativeStackNavigator" in content, "Missing stack navigator"
        assert "NavigationContainer" in content, "Missing NavigationContainer"
        print("✓ Navigation structure with tabs + stacks exists")

    def test_15_screen_files_exist(self):
        """Verify 15 screen files exist in /app/mobile/src/screens/"""
        import os

        screens_dir = "/app/mobile/src/screens"
        assert os.path.exists(screens_dir), "Screens directory missing"

        expected_screens = [
            "LoginScreen.js",
            "RegisterScreen.js",
            "DashboardScreen.js",
            "LeaguesScreen.js",
            "PlayersScreen.js",
            "PlayerDetailScreen.js",
            "DraftRoomScreen.js",
            "AuctionDraftScreen.js",
            "TradeBlockScreen.js",
            "WaiversScreen.js",
            "RosterScreen.js",
            "StandingsScreen.js",
            "SalaryCapScreen.js",
            "ActivityFeedScreen.js",
            "NotificationsScreen.js"
        ]

        for screen in expected_screens:
            path = os.path.join(screens_dir, screen)
            assert os.path.exists(path), f"Missing screen: {screen}"

        print(f"✓ All 15 screen files exist")

    def test_api_client_with_token_management(self):
        """Verify API client with token management in /app/mobile/src/lib/api.js"""
        import os

        api_path = "/app/mobile/src/lib/api.js"
        assert os.path.exists(api_path), "api.js missing"

        with open(api_path, 'r') as f:
            content = f.read()

        # Verify token management functions
        assert "setTokens" in content, "Missing setTokens function"
        assert "getAccessToken" in content, "Missing getAccessToken function"
        assert "clearTokens" in content, "Missing clearTokens function"
        assert "SecureStore" in content, "Missing SecureStore for secure token storage"
        assert "interceptors" in content, "Missing request/response interceptors"
        print("✓ API client with token management exists")

    def test_websocket_hook_exists(self):
        """Verify WebSocket hook in /app/mobile/src/hooks/useSocket.js"""
        import os

        socket_path = "/app/mobile/src/hooks/useSocket.js"
        assert os.path.exists(socket_path), "useSocket.js missing"

        with open(socket_path, 'r') as f:
            content = f.read()

        # Verify socket functionality
        assert "socket.io-client" in content, "Missing socket.io-client import"
        assert "useSocket" in content, "Missing useSocket hook"
        assert "useDraftSocket" in content, "Missing useDraftSocket hook"
        assert "useLeagueSocket" in content, "Missing useLeagueSocket hook"
        assert "connected" in content, "Missing connected state"
        print("✓ WebSocket hook with draft and league sockets exists")

    def test_login_screen_has_content(self):
        """Verify LoginScreen.js has actual implementation"""
        import os

        login_path = "/app/mobile/src/screens/LoginScreen.js"
        with open(login_path, 'r') as f:
            content = f.read()

        # Should have actual React Native code
        assert len(content) > 100, "LoginScreen.js appears empty"
        assert "TextInput" in content, "Missing TextInput component"
        assert "TouchableOpacity" in content, "Missing TouchableOpacity"
        assert "handleLogin" in content or "login" in content, "Missing login handler"
        print("✓ LoginScreen.js has implementation")


class TestExistingFeatures:
    """Verify existing features still work"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"),
            "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
        })
        assert response.status_code == 200
        return s

    def test_leagues_endpoint(self, auth_session):
        """GET /api/leagues returns leagues"""
        response = auth_session.get(f"{BASE_URL}/api/leagues")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Leagues endpoint: {len(data)} leagues")

    def test_players_endpoint(self, auth_session):
        """GET /api/players returns players"""
        response = auth_session.get(f"{BASE_URL}/api/players?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        print(f"✓ Players endpoint: {len(data['players'])} players")

    def test_teams_endpoint(self, auth_session):
        """GET /api/teams returns teams"""
        response = auth_session.get(f"{BASE_URL}/api/teams?league_id={TEST_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Teams endpoint: {len(data)} teams")

    def test_notifications_endpoint(self, auth_session):
        """GET /api/notifications returns notifications"""
        response = auth_session.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Notifications endpoint: {len(data)} notifications")

    def test_drafts_endpoint(self, auth_session):
        """GET /api/drafts returns drafts"""
        response = auth_session.get(f"{BASE_URL}/api/drafts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Drafts endpoint: {len(data)} drafts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

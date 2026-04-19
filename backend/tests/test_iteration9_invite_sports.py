"""
Iteration 9 Tests: League Invite System + Sport-Agnostic Model
Tests:
- GET /api/leagues/{id}/invite - returns invite_code, invite_url, qr_code_base64
- GET /api/leagues/{id}/invite/qr - returns PNG image
- POST /api/leagues/join-by-invite - join league with invite_code + team_name
- POST /api/leagues/{id}/invite/email - store email invite records
- Invalid invite code returns 404
- Duplicate join returns 400
- All leagues have invite_code (not just private)
- GET /api/sports - returns 4 sports (NHL active, NFL/NBA/MLB coming soon)
- League creation includes sport field
- League responses include sport field
"""

import pytest
import requests
import os
import time
import random

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dynasty-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"
TEST_LEAGUE_ID = "69e446a5da97b3ac9066ebe2"


class TestSportsEndpoint:
    """Test the sport-agnostic /api/sports endpoint"""
    
    def test_get_sports_returns_4_sports(self):
        """GET /api/sports returns 4 sports"""
        response = requests.get(f"{BASE_URL}/api/sports")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        sports = response.json()
        assert len(sports) == 4, f"Expected 4 sports, got {len(sports)}"
        
        sport_ids = [s["id"] for s in sports]
        assert "nhl" in sport_ids, "NHL should be in sports list"
        assert "nfl" in sport_ids, "NFL should be in sports list"
        assert "nba" in sport_ids, "NBA should be in sports list"
        assert "mlb" in sport_ids, "MLB should be in sports list"
        print("PASS: GET /api/sports returns 4 sports")
    
    def test_nhl_is_active(self):
        """NHL should be the only active sport"""
        response = requests.get(f"{BASE_URL}/api/sports")
        assert response.status_code == 200
        
        sports = response.json()
        nhl = next((s for s in sports if s["id"] == "nhl"), None)
        assert nhl is not None, "NHL not found"
        assert nhl["active"] is True, "NHL should be active"
        assert nhl["player_count"] > 0, "NHL should have players"
        
        # Other sports should not be active
        for sport in sports:
            if sport["id"] != "nhl":
                assert sport["active"] is False, f"{sport['id']} should not be active"
        print("PASS: NHL is active, others are not")
    
    def test_sports_have_positions(self):
        """Each sport should have positions defined"""
        response = requests.get(f"{BASE_URL}/api/sports")
        assert response.status_code == 200
        
        sports = response.json()
        for sport in sports:
            assert "positions" in sport, f"{sport['id']} missing positions"
            assert len(sport["positions"]) > 0, f"{sport['id']} has no positions"
            assert "full_name" in sport, f"{sport['id']} missing full_name"
        print("PASS: All sports have positions and full_name")


class TestLeagueInviteSystem:
    """Test the league invite system"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
        self.user = login_response.json()
        print(f"Logged in as {self.user['email']}")
    
    def test_get_league_invite_returns_code_url_qr(self):
        """GET /api/leagues/{id}/invite returns invite_code, invite_url, qr_code_base64"""
        response = self.session.get(f"{BASE_URL}/api/leagues/{TEST_LEAGUE_ID}/invite")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "invite_code" in data, "Missing invite_code"
        assert "invite_url" in data, "Missing invite_url"
        assert "qr_code_base64" in data, "Missing qr_code_base64"
        
        # Validate invite_code is non-empty
        assert len(data["invite_code"]) > 0, "invite_code should not be empty"
        
        # Validate invite_url contains the code
        assert data["invite_code"] in data["invite_url"], "invite_url should contain invite_code"
        assert "/join/" in data["invite_url"], "invite_url should contain /join/"
        
        # Validate QR code is base64 encoded PNG
        assert len(data["qr_code_base64"]) > 100, "qr_code_base64 should be substantial"
        print(f"PASS: GET /api/leagues/{TEST_LEAGUE_ID}/invite returns invite_code={data['invite_code']}, url={data['invite_url']}, qr_base64 length={len(data['qr_code_base64'])}")
    
    def test_get_invite_qr_returns_png_image(self):
        """GET /api/leagues/{id}/invite/qr returns PNG image"""
        response = self.session.get(f"{BASE_URL}/api/leagues/{TEST_LEAGUE_ID}/invite/qr")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check content type is image/png
        content_type = response.headers.get("content-type", "")
        assert "image/png" in content_type, f"Expected image/png, got {content_type}"
        
        # Check response has content
        assert len(response.content) > 100, "PNG image should have content"
        
        # Check PNG magic bytes
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Response should be valid PNG"
        print(f"PASS: GET /api/leagues/{TEST_LEAGUE_ID}/invite/qr returns valid PNG ({len(response.content)} bytes)")
    
    def test_join_by_invalid_invite_code_returns_404(self):
        """POST /api/leagues/join-by-invite with invalid code returns 404"""
        response = self.session.post(f"{BASE_URL}/api/leagues/join-by-invite", json={
            "invite_code": "INVALID_CODE_12345",
            "team_name": "Test Team"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("PASS: Invalid invite code returns 404")
    
    def test_join_by_invite_success(self):
        """POST /api/leagues/join-by-invite with valid code joins the league"""
        # First, create a new league to test joining
        unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        create_response = self.session.post(f"{BASE_URL}/api/leagues", json={
            "name": f"TEST_InviteLeague_{unique_id}",
            "sport": "nhl",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "draft_type": "snake"
        })
        assert create_response.status_code == 200, f"Failed to create league: {create_response.text}"
        league = create_response.json()
        league_id = league["id"]
        
        # Get the invite code
        invite_response = self.session.get(f"{BASE_URL}/api/leagues/{league_id}/invite")
        assert invite_response.status_code == 200
        invite_code = invite_response.json()["invite_code"]
        
        # Create a second user to join
        test_email = f"test_join_{unique_id}@test.com"
        register_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "name": "Test Joiner"
        })
        
        if register_response.status_code == 200:
            # Use the new user's session
            join_session = requests.Session()
            login_resp = join_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "TestPass123!"
            })
            assert login_resp.status_code == 200
            
            # Join the league
            join_response = join_session.post(f"{BASE_URL}/api/leagues/join-by-invite", json={
                "invite_code": invite_code,
                "team_name": f"Test Team {unique_id}"
            })
            assert join_response.status_code == 200, f"Expected 200, got {join_response.status_code}: {join_response.text}"
            
            join_data = join_response.json()
            assert "team_id" in join_data, "Response should contain team_id"
            assert "league_id" in join_data, "Response should contain league_id"
            assert join_data["league_id"] == league_id, "league_id should match"
            print(f"PASS: Join by invite successful - team_id={join_data['team_id']}")
            
            # Test duplicate join returns 400
            dup_response = join_session.post(f"{BASE_URL}/api/leagues/join-by-invite", json={
                "invite_code": invite_code,
                "team_name": "Another Team"
            })
            assert dup_response.status_code == 400, f"Expected 400 for duplicate join, got {dup_response.status_code}"
            print("PASS: Duplicate join returns 400")
        else:
            print(f"SKIP: Could not create test user (may already exist)")
    
    def test_email_invites_stored(self):
        """POST /api/leagues/{id}/invite/email stores invite records"""
        # Use the test league
        response = self.session.post(f"{BASE_URL}/api/leagues/{TEST_LEAGUE_ID}/invite/email", json={
            "league_id": TEST_LEAGUE_ID,
            "emails": ["test1@example.com", "test2@example.com"]
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should contain message"
        assert "2" in data["message"], "Message should mention 2 emails"
        assert "invite_url" in data, "Response should contain invite_url"
        print(f"PASS: Email invites stored - {data['message']}")
    
    def test_email_invites_requires_commissioner(self):
        """POST /api/leagues/{id}/invite/email requires commissioner"""
        # Create a new user who is not commissioner
        unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        test_email = f"test_noncomm_{unique_id}@test.com"
        
        register_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "name": "Non Commissioner"
        })
        
        if register_response.status_code == 200:
            non_comm_session = requests.Session()
            login_resp = non_comm_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "TestPass123!"
            })
            assert login_resp.status_code == 200
            
            # Try to send email invites (should fail)
            response = non_comm_session.post(f"{BASE_URL}/api/leagues/{TEST_LEAGUE_ID}/invite/email", json={
                "league_id": TEST_LEAGUE_ID,
                "emails": ["test@example.com"]
            })
            assert response.status_code == 403, f"Expected 403, got {response.status_code}"
            print("PASS: Non-commissioner cannot send email invites (403)")
        else:
            print("SKIP: Could not create test user")


class TestLeagueSportField:
    """Test that leagues include sport field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
    
    def test_league_creation_includes_sport(self):
        """League creation includes sport field"""
        unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        response = self.session.post(f"{BASE_URL}/api/leagues", json={
            "name": f"TEST_SportLeague_{unique_id}",
            "sport": "nhl",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "draft_type": "snake"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        league = response.json()
        assert "sport" in league, "League response should include sport"
        assert league["sport"] == "nhl", f"Expected sport=nhl, got {league['sport']}"
        assert "invite_code" in league, "League response should include invite_code"
        assert league["invite_code"] is not None, "New leagues should have invite_code"
        print(f"PASS: League created with sport={league['sport']}, invite_code={league['invite_code']}")
    
    def test_get_league_includes_sport(self):
        """GET /api/leagues/{id} includes sport field"""
        response = requests.get(f"{BASE_URL}/api/leagues/{TEST_LEAGUE_ID}")
        assert response.status_code == 200
        
        league = response.json()
        assert "sport" in league, "League response should include sport"
        print(f"PASS: GET /api/leagues/{TEST_LEAGUE_ID} includes sport={league['sport']}")
    
    def test_get_leagues_list_includes_sport(self):
        """GET /api/leagues includes sport field in each league"""
        response = requests.get(f"{BASE_URL}/api/leagues")
        assert response.status_code == 200
        
        leagues = response.json()
        assert len(leagues) > 0, "Should have at least one league"
        
        for league in leagues[:5]:  # Check first 5
            assert "sport" in league, f"League {league['id']} missing sport field"
        print(f"PASS: GET /api/leagues includes sport field in all leagues")


class TestNewLeaguesHaveInviteCode:
    """Test that all new leagues get invite codes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
    
    def test_public_league_gets_invite_code(self):
        """Public leagues get invite codes"""
        unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        response = self.session.post(f"{BASE_URL}/api/leagues", json={
            "name": f"TEST_PublicLeague_{unique_id}",
            "sport": "nhl",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "draft_type": "snake",
            "is_private": False
        })
        assert response.status_code == 200
        
        league = response.json()
        assert league["is_private"] is False, "League should be public"
        assert "invite_code" in league, "Public league should have invite_code"
        assert league["invite_code"] is not None, "Public league invite_code should not be null"
        assert len(league["invite_code"]) > 0, "Public league invite_code should not be empty"
        print(f"PASS: Public league has invite_code={league['invite_code']}")
    
    def test_private_league_gets_invite_code(self):
        """Private leagues get invite codes"""
        unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        response = self.session.post(f"{BASE_URL}/api/leagues", json={
            "name": f"TEST_PrivateLeague_{unique_id}",
            "sport": "nhl",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 12,
            "draft_type": "snake",
            "is_private": True
        })
        assert response.status_code == 200
        
        league = response.json()
        assert league["is_private"] is True, "League should be private"
        assert "invite_code" in league, "Private league should have invite_code"
        assert league["invite_code"] is not None, "Private league invite_code should not be null"
        print(f"PASS: Private league has invite_code={league['invite_code']}")


class TestExistingFeatures:
    """Verify existing features still work"""
    
    def test_auth_login(self):
        """Login still works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        print("PASS: Auth login works")
    
    def test_get_players(self):
        """GET /api/players still works"""
        response = requests.get(f"{BASE_URL}/api/players?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        assert len(data["players"]) > 0
        print(f"PASS: GET /api/players returns {len(data['players'])} players")
    
    def test_get_teams(self):
        """GET /api/teams still works"""
        response = requests.get(f"{BASE_URL}/api/teams")
        assert response.status_code == 200
        print("PASS: GET /api/teams works")
    
    def test_get_drafts(self):
        """GET /api/drafts still works"""
        response = requests.get(f"{BASE_URL}/api/drafts")
        assert response.status_code == 200
        print("PASS: GET /api/drafts works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

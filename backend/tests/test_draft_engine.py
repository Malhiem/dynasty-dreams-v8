#!/usr/bin/env python3
"""
Dynasty Dreams Draft Engine Backend API Tests
Tests all draft-related endpoints for the NHL fantasy sports platform using pytest

Endpoints tested:
- POST /api/drafts - Create a new draft for a league
- GET /api/drafts - List all drafts
- GET /api/drafts/{id} - Get draft details
- POST /api/drafts/{id}/start - Start a draft (with early_start=true and false)
- GET /api/drafts/{id}/board - Get the draft board grid
- GET /api/drafts/{id}/eligible-players - Get available players with search and position filter
- POST /api/drafts/{id}/pick - Make a draft pick (validates turn, prevents duplicate picks)
- POST /api/drafts/{id}/pause - Toggle timer pause
- POST /api/drafts/{id}/chat - Send chat message
- GET /api/drafts/{id}/chat - Get chat history
- PUT /api/drafts/{id}/config - Update draft settings
"""

import pytest
import requests
import os
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def authenticated_client():
    """Session with auth cookies from admin login"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Admin login failed - skipping authenticated tests")
    return session


@pytest.fixture(scope="module")
def test_league_and_team(authenticated_client):
    """Create a test league and team for draft testing"""
    timestamp = datetime.now().strftime('%H%M%S%f')

    # Create league
    league_response = authenticated_client.post(f"{BASE_URL}/api/leagues", json={
        "name": f"TEST_DraftLeague_{timestamp}",
        "format": "dynasty",
        "scoring_format": "head_to_head",
        "max_teams": 12,
        "salary_cap_enabled": False,
        "draft_type": "snake",
        "roster_spots": 20,
        "keepers_allowed": 0,
        "is_private": False
    })
    assert league_response.status_code == 200, f"Failed to create league: {league_response.text}"
    league = league_response.json()

    # League creation includes the commissioner's team.
    team_response = authenticated_client.get(f"{BASE_URL}/api/teams?league_id={league['id']}")
    assert team_response.status_code == 200, team_response.text
    teams = team_response.json()
    assert len(teams) == 1
    team = teams[0]

    return {"league": league, "team": team}


class TestDraftCreation:
    """Tests for POST /api/drafts - Create a new draft"""

    def test_create_draft_without_auth_fails(self, api_client):
        """Test POST /api/drafts without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/drafts", json={
            "league_id": "some_id",
            "draft_type": "entry",
            "total_rounds": 5,
            "time_per_pick": 120,
            "snake_draft": True
        })
        assert response.status_code == 401
        print("PASS: Create draft without auth returns 401")

    def test_create_draft_invalid_league_fails(self, authenticated_client):
        """Test POST /api/drafts with invalid league_id returns 404"""
        response = authenticated_client.post(f"{BASE_URL}/api/drafts", json={
            "league_id": "000000000000000000000000",  # Valid ObjectId format but doesn't exist
            "draft_type": "entry",
            "total_rounds": 5,
            "time_per_pick": 120,
            "snake_draft": True
        })
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        print("PASS: Create draft with invalid league returns 404")

    def test_create_draft_success(self, authenticated_client, test_league_and_team):
        """Test POST /api/drafts creates a new draft successfully"""
        league_id = test_league_and_team["league"]["id"]

        response = authenticated_client.post(f"{BASE_URL}/api/drafts", json={
            "league_id": league_id,
            "draft_type": "entry",
            "total_rounds": 5,
            "time_per_pick": 120,
            "snake_draft": True,
            "player_criteria": ["all"],
            "missed_pick_action": "auto-select"
        })
        assert response.status_code == 200, f"Failed to create draft: {response.text}"
        data = response.json()

        # Verify draft structure
        assert "_id" in data
        assert data["league_id"] == league_id
        assert data["draft_type"] == "entry"
        assert data["total_rounds"] == 5
        assert data["time_per_pick"] == 120
        assert data["snake_draft"] == True
        assert data["status"] == "scheduled"
        assert data["draft_started"] == False
        assert data["current_pick"] == 1
        assert "team_abbrs" in data
        assert "picks" in data
        assert len(data["picks"]) == 0

        # Store for later tests
        pytest.test_draft_id = data["_id"]
        print(f"PASS: Created draft {data['_id']} for league {league_id}")


class TestDraftListing:
    """Tests for GET /api/drafts - List all drafts"""

    def test_get_all_drafts(self, api_client):
        """Test GET /api/drafts returns list of drafts"""
        response = api_client.get(f"{BASE_URL}/api/drafts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/drafts returned {len(data)} drafts")

    def test_get_drafts_by_league(self, api_client, test_league_and_team):
        """Test GET /api/drafts?league_id={id} filters by league"""
        league_id = test_league_and_team["league"]["id"]
        response = api_client.get(f"{BASE_URL}/api/drafts?league_id={league_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # All returned drafts should be for this league
        for draft in data:
            assert draft["league_id"] == league_id
        print(f"PASS: GET /api/drafts?league_id filtered correctly, found {len(data)} drafts")


class TestDraftDetails:
    """Tests for GET /api/drafts/{id} - Get draft details"""

    def test_get_draft_not_found(self, api_client):
        """Test GET /api/drafts/{id} with invalid id returns 404"""
        response = api_client.get(f"{BASE_URL}/api/drafts/000000000000000000000000")
        assert response.status_code == 404
        print("PASS: GET draft with invalid id returns 404")

    def test_get_draft_details(self, api_client):
        """Test GET /api/drafts/{id} returns draft details"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["_id"] == pytest.test_draft_id
        assert "league_id" in data
        assert "draft_type" in data
        assert "total_rounds" in data
        assert "time_per_pick" in data
        assert "snake_draft" in data
        assert "status" in data
        assert "team_abbrs" in data
        assert "picks" in data
        print(f"PASS: GET /api/drafts/{pytest.test_draft_id} returned draft details")


class TestDraftBoard:
    """Tests for GET /api/drafts/{id}/board - Get draft board grid"""

    def test_get_draft_board_not_found(self, api_client):
        """Test GET /api/drafts/{id}/board with invalid id returns 404"""
        response = api_client.get(f"{BASE_URL}/api/drafts/000000000000000000000000/board")
        assert response.status_code == 404
        print("PASS: GET draft board with invalid id returns 404")

    def test_get_draft_board(self, api_client):
        """Test GET /api/drafts/{id}/board returns board grid"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/board")
        assert response.status_code == 200
        data = response.json()

        assert "board" in data
        assert "current_pick" in data
        assert "status" in data
        assert "team_abbrs" in data
        assert "total_rounds" in data
        assert "snake_draft" in data
        assert "on_the_clock" in data

        # Board should be a 2D array with total_rounds rows
        assert isinstance(data["board"], list)
        assert len(data["board"]) == data["total_rounds"]

        # Each round should have picks for each team
        for round_picks in data["board"]:
            assert isinstance(round_picks, list)
            for pick in round_picks:
                assert "round" in pick
                assert "pick_in_round" in pick
                assert "overall" in pick
                assert "team" in pick

        print(f"PASS: GET /api/drafts/{pytest.test_draft_id}/board returned {len(data['board'])} rounds")


class TestEligiblePlayers:
    """Tests for GET /api/drafts/{id}/eligible-players - Get available players"""

    def test_get_eligible_players_not_found(self, api_client):
        """Test GET /api/drafts/{id}/eligible-players with invalid id returns 404"""
        response = api_client.get(f"{BASE_URL}/api/drafts/000000000000000000000000/eligible-players")
        assert response.status_code == 404
        print("PASS: GET eligible players with invalid id returns 404")

    def test_get_eligible_players(self, api_client):
        """Test GET /api/drafts/{id}/eligible-players returns available players"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/eligible-players")
        assert response.status_code == 200
        data = response.json()

        assert "players" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data

        # Should have players available
        assert len(data["players"]) > 0

        # Verify player structure
        player = data["players"][0]
        assert "id" in player
        assert "name" in player
        assert "position" in player
        assert "nhlTeam" in player
        assert "drafted" in player
        assert player["drafted"] == False

        # Store a player ID for pick testing
        pytest.test_player_id = player["id"]
        print(f"PASS: GET eligible players returned {len(data['players'])} players, total: {data['total']}")

    def test_get_eligible_players_with_search(self, api_client):
        """Test GET /api/drafts/{id}/eligible-players?search=McDavid"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/eligible-players?search=McDavid")
        assert response.status_code == 200
        data = response.json()

        # Should find McDavid
        assert len(data["players"]) >= 1
        mcdavid = next((p for p in data["players"] if "McDavid" in p["name"]), None)
        assert mcdavid is not None
        print(f"PASS: Search for McDavid found {len(data['players'])} players")

    def test_get_eligible_players_with_position_filter(self, api_client):
        """Test GET /api/drafts/{id}/eligible-players?position=G returns goalies"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/eligible-players?position=G")
        assert response.status_code == 200
        data = response.json()

        # All returned players should be goalies
        for player in data["players"]:
            assert player["position"] == "G"
        print(f"PASS: Position filter G returned {len(data['players'])} goalies")


class TestDraftStart:
    """Tests for POST /api/drafts/{id}/start - Start a draft"""

    def test_start_draft_without_auth_fails(self, api_client):
        """Test POST /api/drafts/{id}/start without auth returns 401"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/start")
        assert response.status_code == 401
        print("PASS: Start draft without auth returns 401")

    def test_start_draft_not_found(self, authenticated_client):
        """Test POST /api/drafts/{id}/start with invalid id returns 404"""
        response = authenticated_client.post(f"{BASE_URL}/api/drafts/000000000000000000000000/start")
        assert response.status_code == 404
        print("PASS: Start draft with invalid id returns 404")

    def test_start_draft_with_early_start(self, authenticated_client):
        """Test POST /api/drafts/{id}/start?early_start=true starts draft without clock"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/start?early_start=true")
        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert data["early_start"] == True

        # Verify draft is now active
        draft_response = authenticated_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}")
        draft = draft_response.json()
        assert draft["status"] == "active"
        assert draft["draft_started"] == True
        assert draft["early_start"] == True

        print(f"PASS: Started draft {pytest.test_draft_id} with early_start=true")

    def test_start_draft_already_active_is_idempotent(self, authenticated_client):
        """Repeat start is a successful no-op and preserves the active draft."""
        assert hasattr(pytest, 'test_draft_id')
        url = f"{BASE_URL}/api/drafts/{pytest.test_draft_id}"
        before = authenticated_client.get(url).json()
        response = authenticated_client.post(f"{url}/start")
        assert response.status_code == 200, response.text
        assert response.json()["already_active"] is True
        assert authenticated_client.get(url).json() == before


class TestDraftPick:
    """Tests for POST /api/drafts/{id}/pick - Make a draft pick"""

    def test_make_pick_without_auth_fails(self, api_client):
        """Test POST /api/drafts/{id}/pick without auth returns 401"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pick", json={
            "player_id": "some_player_id"
        })
        assert response.status_code == 401
        print("PASS: Make pick without auth returns 401")

    def test_make_pick_draft_not_found(self, authenticated_client):
        """Test POST /api/drafts/{id}/pick with invalid draft id returns 404"""
        response = authenticated_client.post(f"{BASE_URL}/api/drafts/000000000000000000000000/pick", json={
            "player_id": "some_player_id"
        })
        assert response.status_code == 404
        print("PASS: Make pick with invalid draft id returns 404")

    def test_make_pick_player_not_found(self, authenticated_client):
        """Test POST /api/drafts/{id}/pick with invalid player_id returns 404"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pick", json={
            "player_id": "000000000000000000000000"
        })
        assert response.status_code == 404
        data = response.json()
        assert "player not found" in data["detail"].lower()
        print("PASS: Make pick with invalid player returns 404")

    def test_make_pick_success(self, authenticated_client):
        """Test POST /api/drafts/{id}/pick makes a successful pick"""
        if not hasattr(pytest, 'test_draft_id') or not hasattr(pytest, 'test_player_id'):
            pytest.skip("No draft or player available from previous tests")

        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pick", json={
            "player_id": pytest.test_player_id
        })
        assert response.status_code == 200, f"Failed to make pick: {response.text}"
        data = response.json()

        # Verify pick structure
        assert "round" in data
        assert "pick_in_round" in data
        assert "overall" in data
        assert "team" in data
        assert "player_id" in data
        assert "player" in data
        assert "timestamp" in data

        assert data["player_id"] == pytest.test_player_id
        assert data["overall"] == 1  # First pick
        assert data["round"] == 1

        # Store for duplicate pick test
        pytest.picked_player_id = pytest.test_player_id
        print(f"PASS: Made pick #{data['overall']} - {data['player']['name']}")

    def test_make_pick_duplicate_player_fails(self, authenticated_client):
        """Test POST /api/drafts/{id}/pick with already drafted player returns 400"""
        if not hasattr(pytest, 'test_draft_id') or not hasattr(pytest, 'picked_player_id'):
            pytest.skip("No draft or picked player available from previous tests")

        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pick", json={
            "player_id": pytest.picked_player_id
        })
        assert response.status_code == 400
        data = response.json()
        assert "already drafted" in data["detail"].lower()
        print("PASS: Duplicate player pick returns 400")

    def test_drafted_player_excluded_from_eligible(self, api_client):
        """Test that drafted players are excluded from eligible-players list"""
        if not hasattr(pytest, 'test_draft_id') or not hasattr(pytest, 'picked_player_id'):
            pytest.skip("No draft or picked player available from previous tests")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/eligible-players")
        assert response.status_code == 200
        data = response.json()

        # The picked player should NOT be in the eligible list
        player_ids = [p["id"] for p in data["players"]]
        assert pytest.picked_player_id not in player_ids
        print("PASS: Drafted player excluded from eligible players list")


class TestDraftPause:
    """Tests for POST /api/drafts/{id}/pause - Toggle timer pause"""

    def test_pause_draft_without_auth_fails(self, api_client):
        """Test POST /api/drafts/{id}/pause without auth returns 401"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pause")
        assert response.status_code == 401
        print("PASS: Pause draft without auth returns 401")

    def test_pause_draft_not_found(self, authenticated_client):
        """Test POST /api/drafts/{id}/pause with invalid id returns 404"""
        response = authenticated_client.post(f"{BASE_URL}/api/drafts/000000000000000000000000/pause")
        assert response.status_code == 404
        print("PASS: Pause draft with invalid id returns 404")

    def test_pause_draft_toggle(self, authenticated_client):
        """Test POST /api/drafts/{id}/pause toggles timer pause"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        # First pause
        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert "paused" in data
        first_state = data["paused"]

        # Toggle again
        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["paused"] != first_state  # Should be toggled

        print(f"PASS: Pause toggle works - first: {first_state}, second: {data['paused']}")


class TestDraftChat:
    """Tests for POST/GET /api/drafts/{id}/chat - Draft chat"""

    def test_send_chat_without_auth_fails(self, api_client):
        """Test POST /api/drafts/{id}/chat without auth returns 401"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/chat", json={
            "text": "Hello!"
        })
        assert response.status_code == 401
        print("PASS: Send chat without auth returns 401")

    def test_send_chat_message(self, authenticated_client):
        """Test POST /api/drafts/{id}/chat sends a message"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        test_message = f"Test message at {datetime.now().isoformat()}"
        response = authenticated_client.post(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/chat", json={
            "text": test_message
        })
        assert response.status_code == 200
        data = response.json()

        assert "id" in data
        assert "type" in data
        assert data["type"] == "chat"
        assert "sender" in data
        assert "text" in data
        assert data["text"] == test_message
        assert "timestamp" in data

        print(f"PASS: Sent chat message: {test_message[:30]}...")

    def test_get_chat_not_found(self, api_client):
        """Test GET /api/drafts/{id}/chat with invalid id returns 404"""
        response = api_client.get(f"{BASE_URL}/api/drafts/000000000000000000000000/chat")
        assert response.status_code == 404
        print("PASS: Get chat with invalid id returns 404")

    def test_get_chat_history(self, api_client):
        """Test GET /api/drafts/{id}/chat returns chat history"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/chat")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # Should have at least the system message from draft start and our test message
        assert len(data) >= 2

        # Verify message structure
        for msg in data:
            assert "id" in msg
            assert "type" in msg
            assert "sender" in msg
            assert "text" in msg
            assert "timestamp" in msg

        print(f"PASS: Got {len(data)} chat messages")


class TestDraftConfig:
    """Tests for PUT /api/drafts/{id}/config - Update draft settings"""

    def test_update_config_without_auth_fails(self, api_client):
        """Test PUT /api/drafts/{id}/config without auth returns 401"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        fresh_session = requests.Session()
        response = fresh_session.put(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/config", json={
            "time_per_pick": 60
        })
        assert response.status_code == 401
        print("PASS: Update config without auth returns 401")

    def test_update_config_not_found(self, authenticated_client):
        """Test PUT /api/drafts/{id}/config with invalid id returns 404"""
        response = authenticated_client.put(f"{BASE_URL}/api/drafts/000000000000000000000000/config", json={
            "time_per_pick": 60
        })
        assert response.status_code == 404
        print("PASS: Update config with invalid id returns 404")

    def test_update_config_time_per_pick(self, authenticated_client):
        """Test PUT /api/drafts/{id}/config updates time_per_pick"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        new_time = 90
        response = authenticated_client.put(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/config", json={
            "time_per_pick": new_time
        })
        assert response.status_code == 200
        data = response.json()

        assert "updated" in data
        assert "time_per_pick" in data["updated"]

        # Verify the change
        draft_response = authenticated_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}")
        draft = draft_response.json()
        assert draft["time_per_pick"] == new_time

        print(f"PASS: Updated time_per_pick to {new_time}")

    def test_update_config_multiple_fields(self, authenticated_client):
        """Test PUT /api/drafts/{id}/config updates multiple fields"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = authenticated_client.put(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/config", json={
            "time_per_pick": 120,
            "missed_pick_action": "pick-anytime"
        })
        assert response.status_code == 200
        data = response.json()

        assert "updated" in data
        assert len(data["updated"]) == 2

        print(f"PASS: Updated multiple config fields: {data['updated']}")


class TestSnakeDraftOrdering:
    """Tests for snake draft ordering logic"""

    def test_draft_board_snake_ordering(self, api_client):
        """Test that draft board shows correct snake ordering"""
        if not hasattr(pytest, 'test_draft_id'):
            pytest.skip("No draft created in previous test")

        response = api_client.get(f"{BASE_URL}/api/drafts/{pytest.test_draft_id}/board")
        assert response.status_code == 200
        data = response.json()

        if not data["snake_draft"]:
            pytest.skip("Draft is not snake format")

        if len(data["team_abbrs"]) < 2:
            pytest.skip("Need at least 2 teams to test snake ordering")

        # In snake draft, even rounds should be reversed
        # Round 1: Team A, Team B, Team C
        # Round 2: Team C, Team B, Team A (reversed)
        board = data["board"]
        team_abbrs = data["team_abbrs"]

        if len(board) >= 2:
            round1_teams = [pick["team"] for pick in board[0]]
            round2_teams = [pick["team"] for pick in board[1]]

            # Round 2 should be reversed order of Round 1
            assert round2_teams == list(reversed(round1_teams)), "Snake draft ordering incorrect"
            print("PASS: Snake draft ordering verified - Round 2 is reversed from Round 1")
        else:
            print("PASS: Snake draft configured (only 1 round to verify)")


class TestExistingFeatures:
    """Verify existing features still work after draft engine addition"""

    def test_login_still_works(self, api_client):
        """Test POST /api/auth/login still works"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        print("PASS: Login still works")

    def test_leagues_still_work(self, api_client):
        """Test GET /api/leagues still works"""
        response = api_client.get(f"{BASE_URL}/api/leagues")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Leagues endpoint still works, found {len(data)} leagues")

    def test_teams_still_work(self, api_client):
        """Test GET /api/teams still works"""
        response = api_client.get(f"{BASE_URL}/api/teams")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Teams endpoint still works, found {len(data)} teams")

    def test_players_still_work(self, api_client):
        """Test GET /api/players still works"""
        response = api_client.get(f"{BASE_URL}/api/players?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        assert "total" in data
        assert data["total"] >= 1000  # Should have 1038 players
        print(f"PASS: Players endpoint still works, total: {data['total']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

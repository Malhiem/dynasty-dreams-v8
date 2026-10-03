#!/usr/bin/env python3
"""
Dynasty Dreams Trade Center & Waiver Wire Backend API Tests
Tests all trade and waiver-related endpoints for the NHL fantasy sports platform using pytest

Trade Center Endpoints tested:
- POST /api/trade-block - Add player/pick to trade block
- GET /api/trade-block - List all trade block items
- DELETE /api/trade-block/{id} - Remove item from trade block
- POST /api/trades - Create trade proposal
- GET /api/trades - List trades (with filters)
- GET /api/trades/{id} - Get trade details
- POST /api/trades/{id}/accept - Target team accepts trade
- POST /api/trades/{id}/reject - Target team rejects trade
- POST /api/trades/{id}/withdraw - Proposer withdraws trade
- POST /api/trades/{id}/vote - League members vote on trade

Waiver Wire Endpoints tested:
- GET /api/waivers/available - Get available players
- POST /api/waivers/claim - Place FAAB bid
- GET /api/waivers/claims - List waiver claims
- DELETE /api/waivers/claims/{id} - Cancel pending claim
- GET /api/waivers/budget - Get FAAB budget
- GET /api/waivers/order - Get waiver priority order
- GET /api/waivers/history - Get processed claims history
- POST /api/waivers/process - Commissioner processes claims
"""
import uuid

import pytest
import requests
import os
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

# Second user for trade testing
TEST_USER2_EMAIL = f"test_trade_user_{datetime.now().strftime('%H%M%S%f')}@test.com"
TEST_USER2_PASSWORD = "TestPass123!"


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
def second_user_client():
    """Create and login a second user for trade testing"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    # Register second user
    reg_response = session.post(f"{BASE_URL}/api/auth/register", json={"username": "fixture_" + uuid.uuid4().hex[:16],
        "email": TEST_USER2_EMAIL,
        "password": TEST_USER2_PASSWORD,
        "name": "Trade Test User"
    })
    if reg_response.status_code not in [200, 400]:  # 400 if already exists
        pytest.skip("Failed to create second user")

    # Login second user
    login_response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER2_EMAIL,
        "password": TEST_USER2_PASSWORD
    })
    if login_response.status_code != 200:
        pytest.skip("Second user login failed")

    return session


@pytest.fixture(scope="module")
def test_league_and_teams(authenticated_client, second_user_client, test_players):
    """Create a test league with two teams for trade testing"""
    timestamp = datetime.now().strftime('%H%M%S%f')

    # Create league (admin is commissioner)
    league_response = authenticated_client.post(f"{BASE_URL}/api/leagues", json={
        "name": f"TEST_TradeLeague_{timestamp}",
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

    # League creation already creates the commissioner's team.
    teams_response = authenticated_client.get(f"{BASE_URL}/api/teams?league_id={league['id']}")
    assert teams_response.status_code == 200, teams_response.text
    assert len(teams_response.json()) == 1
    team1 = teams_response.json()[0]

    # Create team 2 (second user's team)
    team2_response = second_user_client.post(f"{BASE_URL}/api/teams", json={
        "name": f"TEST_User2Team_{timestamp}",
        "league_id": league["id"]
    })
    assert team2_response.status_code == 200, f"Failed to create team 2: {team2_response.text}"
    team2 = team2_response.json()

    for client, team, player in ((authenticated_client, team1, test_players[0]), (second_user_client, team2, test_players[1])):
        added = client.post(f"{BASE_URL}/api/roster/{team['id']}/add", json={"player_id": player["_id"]})
        assert added.status_code == 200, added.text
    return {"league": league, "team1": team1, "team2": team2}


@pytest.fixture(scope="module")
def test_players(api_client):
    """Get some test players for trade/waiver testing"""
    response = api_client.get(f"{BASE_URL}/api/players?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["players"]) >= 2
    return data["players"]


# ═══════════════════════════════════════════════════════════════
# TRADE BLOCK TESTS
# ═══════════════════════════════════════════════════════════════

class TestTradeBlockAdd:
    """Tests for POST /api/trade-block - Add item to trade block"""

    def test_add_to_trade_block_without_auth_fails(self, api_client, test_players):
        """Test POST /api/trade-block without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/trade-block", json={
            "player_id": test_players[0]["_id"],
            "item_type": "player",
            "looking_for": ["C", "LW"]
        })
        assert response.status_code == 401
        print("PASS: Add to trade block without auth returns 401")

    def test_add_player_to_trade_block(self, authenticated_client, test_players):
        """Test POST /api/trade-block adds a player successfully"""
        # Use a unique player based on timestamp to avoid duplicates
        timestamp_idx = int(datetime.now().strftime('%S')) % len(test_players)
        player = test_players[timestamp_idx]

        response = authenticated_client.post(f"{BASE_URL}/api/trade-block", json={
            "player_id": player["_id"],
            "item_type": "player",
            "looking_for": ["C", "LW"]
        })

        # Handle case where player is already on trade block (from previous test runs)
        if response.status_code == 400 and "already" in response.text.lower():
            # Try with a different player
            for i, p in enumerate(test_players):
                if i != timestamp_idx:
                    response = authenticated_client.post(f"{BASE_URL}/api/trade-block", json={
                        "player_id": p["_id"],
                        "item_type": "player",
                        "looking_for": ["C", "LW"]
                    })
                    if response.status_code == 200:
                        player = p
                        break

        assert response.status_code == 200, f"Failed to add to trade block: {response.text}"
        data = response.json()

        assert "_id" in data
        assert data["item_type"] == "player"
        assert data["player_id"] == player["_id"]
        assert data["name"] == player["name"]
        assert "position" in data
        assert "looking_for" in data
        assert "owner_id" in data
        assert "created_at" in data

        # Store for later tests
        pytest.trade_block_item_id = data["_id"]
        pytest.trade_block_player_id = player["_id"]
        print(f"PASS: Added {player['name']} to trade block")

    def test_add_pick_to_trade_block(self, authenticated_client):
        """Test POST /api/trade-block adds a draft pick successfully"""
        response = authenticated_client.post(f"{BASE_URL}/api/trade-block", json={
            "item_type": "pick",
            "pick_year": 2026,
            "pick_round": "1st",
            "looking_for": ["G"]
        })
        assert response.status_code == 200, f"Failed to add pick to trade block: {response.text}"
        data = response.json()

        assert data["item_type"] == "pick"
        assert data["pick_year"] == 2026
        assert data["pick_round"] == "1st"
        assert "2026" in data["name"]
        assert "1st" in data["name"]

        pytest.trade_block_pick_id = data["_id"]
        print("PASS: Added 2026 1st Round pick to trade block")

    def test_add_duplicate_to_trade_block_fails(self, authenticated_client, test_players):
        """Test POST /api/trade-block with duplicate player returns 400"""
        if not hasattr(pytest, 'trade_block_player_id'):
            pytest.skip("No player added to trade block in previous test")

        response = authenticated_client.post(f"{BASE_URL}/api/trade-block", json={
            "player_id": pytest.trade_block_player_id,
            "item_type": "player",
            "looking_for": ["D"]
        })
        assert response.status_code == 400
        data = response.json()
        assert "already" in data["detail"].lower()
        print("PASS: Duplicate trade block entry returns 400")

    def test_add_invalid_player_to_trade_block_fails(self, authenticated_client):
        """Test POST /api/trade-block with invalid player_id returns 404"""
        response = authenticated_client.post(f"{BASE_URL}/api/trade-block", json={
            "player_id": "000000000000000000000000",
            "item_type": "player",
            "looking_for": []
        })
        assert response.status_code == 404
        print("PASS: Invalid player_id returns 404")


class TestTradeBlockList:
    """Tests for GET /api/trade-block - List trade block items"""

    def test_get_trade_block(self, api_client):
        """Test GET /api/trade-block returns list of items"""
        response = api_client.get(f"{BASE_URL}/api/trade-block")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # Should have at least the items we added
        assert len(data) >= 1

        # Verify item structure
        for item in data:
            assert "_id" in item
            assert "item_type" in item
            assert "name" in item
            assert "owner_id" in item
            assert "created_at" in item

        print(f"PASS: GET /api/trade-block returned {len(data)} items")


class TestTradeBlockRemove:
    """Tests for DELETE /api/trade-block/{id} - Remove from trade block"""

    def test_remove_from_trade_block_without_auth_fails(self, api_client):
        """Test DELETE /api/trade-block/{id} without auth returns 401"""
        if not hasattr(pytest, 'trade_block_pick_id'):
            pytest.skip("No trade block item to remove")

        fresh_session = requests.Session()
        response = fresh_session.delete(f"{BASE_URL}/api/trade-block/{pytest.trade_block_pick_id}")
        assert response.status_code == 401
        print("PASS: Remove from trade block without auth returns 401")

    def test_remove_from_trade_block_not_found(self, authenticated_client):
        """Test DELETE /api/trade-block/{id} with invalid id returns 404"""
        response = authenticated_client.delete(f"{BASE_URL}/api/trade-block/000000000000000000000000")
        assert response.status_code == 404
        print("PASS: Remove non-existent trade block item returns 404")

    def test_remove_from_trade_block_success(self, authenticated_client):
        """Test DELETE /api/trade-block/{id} removes item successfully"""
        if not hasattr(pytest, 'trade_block_pick_id'):
            pytest.skip("No trade block item to remove")

        response = authenticated_client.delete(f"{BASE_URL}/api/trade-block/{pytest.trade_block_pick_id}")
        assert response.status_code == 200
        data = response.json()
        assert "removed" in data["message"].lower() or "message" in data

        # Verify it's gone
        list_response = authenticated_client.get(f"{BASE_URL}/api/trade-block")
        items = list_response.json()
        item_ids = [item["_id"] for item in items]
        assert pytest.trade_block_pick_id not in item_ids

        print("PASS: Removed pick from trade block")


# ═══════════════════════════════════════════════════════════════
# TRADE PROPOSAL TESTS
# ═══════════════════════════════════════════════════════════════

class TestTradeProposalCreate:
    """Tests for POST /api/trades - Create trade proposal"""

    def test_create_trade_without_auth_fails(self, api_client, test_league_and_teams, test_players):
        """Test POST /api/trades without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/trades", json={
            "league_id": test_league_and_teams["league"]["id"],
            "target_team_id": test_league_and_teams["team2"]["id"],
            "assets_offered": [{"asset_type": "player", "player_id": test_players[0]["_id"]}],
            "assets_requested": [{"asset_type": "player", "player_id": test_players[1]["_id"]}]
        })
        assert response.status_code == 401
        print("PASS: Create trade without auth returns 401")

    def test_create_trade_invalid_league_fails(self, authenticated_client, test_players):
        """Test POST /api/trades with invalid league_id returns 404"""
        response = authenticated_client.post(f"{BASE_URL}/api/trades", json={
            "league_id": "000000000000000000000000",
            "target_team_id": "000000000000000000000000",
            "assets_offered": [{"asset_type": "player", "player_id": test_players[0]["_id"]}],
            "assets_requested": [{"asset_type": "player", "player_id": test_players[1]["_id"]}]
        })
        assert response.status_code == 404
        print("PASS: Create trade with invalid league returns 404")

    def test_create_trade_proposal_success(self, authenticated_client, test_league_and_teams, test_players):
        """Test POST /api/trades creates a trade proposal successfully"""
        league = test_league_and_teams["league"]
        team2 = test_league_and_teams["team2"]

        response = authenticated_client.post(f"{BASE_URL}/api/trades", json={
            "league_id": league["id"],
            "target_team_id": team2["id"],
            "assets_offered": [
                {"asset_type": "player", "player_id": test_players[0]["_id"]}
            ],
            "assets_requested": [
                {"asset_type": "player", "player_id": test_players[1]["_id"]}
            ],
            "message": "Test trade proposal"
        })
        assert response.status_code == 200, f"Failed to create trade: {response.text}"
        data = response.json()

        assert "_id" in data
        assert data["league_id"] == league["id"]
        assert data["target_team_id"] == team2["id"]
        assert data["status"] == "proposed"
        assert "proposer_team_id" in data
        assert "proposer_team_name" in data
        assert "target_team_name" in data
        assert "assets_offered" in data
        assert "assets_requested" in data
        assert len(data["assets_offered"]) == 1
        assert len(data["assets_requested"]) == 1
        assert "votes" in data
        assert data["votes"]["approve"] == 0
        assert data["votes"]["veto"] == 0
        assert "submitted_at" in data

        # Store for later tests
        pytest.trade_id = data["_id"]
        print(f"PASS: Created trade proposal {data['_id']}")

    def test_create_trade_with_pick(self, authenticated_client, test_league_and_teams, test_players):
        """Test POST /api/trades with draft pick asset"""
        league = test_league_and_teams["league"]
        team2 = test_league_and_teams["team2"]

        response = authenticated_client.post(f"{BASE_URL}/api/trades", json={
            "league_id": league["id"],
            "target_team_id": team2["id"],
            "assets_offered": [
                {"asset_type": "pick", "pick_year": 2026, "pick_round": "2nd"}
            ],
            "assets_requested": [
                {"asset_type": "player", "player_id": test_players[2]["_id"]}
            ],
            "message": "Pick for player trade"
        })
        assert response.status_code == 200, f"Failed to create pick trade: {response.text}"
        data = response.json()

        assert data["assets_offered"][0]["asset_type"] == "pick"
        pytest.trade_with_pick_id = data["_id"]
        print("PASS: Created trade with draft pick")


class TestTradeProposalList:
    """Tests for GET /api/trades - List trades"""

    def test_get_all_trades(self, api_client):
        """Test GET /api/trades returns list of trades"""
        response = api_client.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        print(f"PASS: GET /api/trades returned {len(data)} trades")

    def test_get_trades_by_league(self, api_client, test_league_and_teams):
        """Test GET /api/trades?league_id={id} filters by league"""
        league_id = test_league_and_teams["league"]["id"]
        response = api_client.get(f"{BASE_URL}/api/trades?league_id={league_id}")
        assert response.status_code == 200
        data = response.json()

        for trade in data:
            assert trade["league_id"] == league_id
        print(f"PASS: Filtered trades by league, found {len(data)}")

    def test_get_trades_by_status(self, api_client):
        """Test GET /api/trades?status=pending filters by status"""
        response = api_client.get(f"{BASE_URL}/api/trades?status=pending")
        assert response.status_code == 200
        data = response.json()

        for trade in data:
            assert trade["status"] == "pending"
        print(f"PASS: Filtered trades by status=pending, found {len(data)}")

    def test_get_my_trades(self, authenticated_client):
        """Test GET /api/trades?my_trades=true returns user's trades"""
        response = authenticated_client.get(f"{BASE_URL}/api/trades?my_trades=true")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        print(f"PASS: GET my_trades returned {len(data)} trades")


class TestTradeProposalDetails:
    """Tests for GET /api/trades/{id} - Get trade details"""

    def test_get_trade_not_found(self, api_client):
        """Test GET /api/trades/{id} with invalid id returns 404"""
        response = api_client.get(f"{BASE_URL}/api/trades/000000000000000000000000")
        assert response.status_code == 404
        print("PASS: GET trade with invalid id returns 404")

    def test_get_trade_details(self, api_client):
        """Test GET /api/trades/{id} returns trade details"""
        if not hasattr(pytest, 'trade_id'):
            pytest.skip("No trade created in previous test")

        response = api_client.get(f"{BASE_URL}/api/trades/{pytest.trade_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["_id"] == pytest.trade_id
        assert "league_id" in data
        assert "proposer_team_id" in data
        assert "target_team_id" in data
        assert "assets_offered" in data
        assert "assets_requested" in data
        assert "status" in data
        assert "votes" in data
        print(f"PASS: GET /api/trades/{pytest.trade_id} returned details")


class TestTradeActions:
    """Tests for trade accept/reject/withdraw/vote actions"""

    def test_accept_trade_wrong_user_fails(self, authenticated_client):
        """Test POST /api/trades/{id}/accept by non-target user returns 403"""
        if not hasattr(pytest, 'trade_id'):
            pytest.skip("No trade created in previous test")

        # Admin (proposer) tries to accept their own trade
        response = authenticated_client.post(f"{BASE_URL}/api/trades/{pytest.trade_id}/accept")
        assert response.status_code == 403
        data = response.json()
        assert "target" in data["detail"].lower()
        print("PASS: Accept trade by non-target user returns 403")

    def test_reject_trade_wrong_user_fails(self, authenticated_client):
        """Test POST /api/trades/{id}/reject by non-target user returns 403"""
        if not hasattr(pytest, 'trade_id'):
            pytest.skip("No trade created in previous test")

        response = authenticated_client.post(f"{BASE_URL}/api/trades/{pytest.trade_id}/reject")
        assert response.status_code == 403
        print("PASS: Reject trade by non-target user returns 403")

    def test_withdraw_trade_wrong_user_fails(self, second_user_client):
        """Test POST /api/trades/{id}/withdraw by non-proposer returns 403"""
        if not hasattr(pytest, 'trade_id'):
            pytest.skip("No trade created in previous test")

        # Second user (target) tries to withdraw
        response = second_user_client.post(f"{BASE_URL}/api/trades/{pytest.trade_id}/withdraw")
        assert response.status_code == 403
        data = response.json()
        assert "proposer" in data["detail"].lower()
        print("PASS: Withdraw trade by non-proposer returns 403")

    def test_proposed_trade_cannot_be_voted_on(self, authenticated_client):
        response = authenticated_client.post(f"{BASE_URL}/api/trades/{pytest.trade_id}/vote", json={"vote": "approve"})
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "Trade is not open for voting"

    def test_accept_trade_by_target(self, second_user_client):
        """Test POST /api/trades/{id}/accept by target team succeeds"""
        if not hasattr(pytest, 'trade_id'):
            pytest.skip("No trade created in previous test")

        response = second_user_client.post(f"{BASE_URL}/api/trades/{pytest.trade_id}/accept")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "accepted"
        print("PASS: Target team accepted trade")

    def test_repeated_vote_is_idempotent(self, authenticated_client, second_user_client, test_league_and_teams, test_players):
        # The original trade was accepted through the legacy auto-execution path.
        # Create a separate reverse swap and enter review through /respond.
        proposal = authenticated_client.post(f"{BASE_URL}/api/trades", json={
            "league_id": test_league_and_teams["league"]["id"], "target_team_id": test_league_and_teams["team2"]["id"],
            "assets_offered": [{"asset_type": "player", "player_id": test_players[1]["_id"]}],
            "assets_requested": [{"asset_type": "player", "player_id": test_players[0]["_id"]}]})
        assert proposal.status_code == 200, proposal.text
        trade_id = proposal.json()["_id"]
        accepted = second_user_client.post(f"{BASE_URL}/api/trades/{trade_id}/respond", json={"action": "accept"})
        assert accepted.status_code == 200, accepted.text
        url = f"{BASE_URL}/api/trades/{trade_id}/vote"
        for vote in ("approve", "approve"):
            response = authenticated_client.post(url, json={"vote": vote})
            assert response.status_code == 200, response.text
        trade = authenticated_client.get(f"{BASE_URL}/api/trades/{trade_id}").json()
        assert trade["votes"]["approve"] == 1
        assert trade["votes"]["veto"] == 0

    def test_accept_already_accepted_fails(self, second_user_client):
        """Test POST /api/trades/{id}/accept on non-pending trade returns 400"""
        if not hasattr(pytest, 'trade_id'):
            pytest.skip("No trade created in previous test")

        response = second_user_client.post(f"{BASE_URL}/api/trades/{pytest.trade_id}/accept")
        assert response.status_code == 400
        data = response.json()
        assert "not pending" in data["detail"].lower()
        print("PASS: Accept non-pending trade returns 400")

    def test_reject_trade_by_target(self, second_user_client, authenticated_client, test_league_and_teams, test_players):
        """Test POST /api/trades/{id}/reject by target team succeeds"""
        # Create a new trade to reject
        league = test_league_and_teams["league"]
        team2 = test_league_and_teams["team2"]

        create_response = authenticated_client.post(f"{BASE_URL}/api/trades", json={
            "league_id": league["id"],
            "target_team_id": team2["id"],
            "assets_offered": [{"asset_type": "player", "player_id": test_players[3]["_id"]}],
            "assets_requested": [{"asset_type": "player", "player_id": test_players[4]["_id"]}]
        })
        assert create_response.status_code == 200
        trade_to_reject = create_response.json()["_id"]

        # Target rejects
        response = second_user_client.post(f"{BASE_URL}/api/trades/{trade_to_reject}/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        print("PASS: Target team rejected trade")

    def test_withdraw_trade_by_proposer(self, authenticated_client, test_league_and_teams, test_players):
        """Test POST /api/trades/{id}/withdraw by proposer succeeds"""
        # Create a new trade to withdraw
        league = test_league_and_teams["league"]
        team2 = test_league_and_teams["team2"]

        create_response = authenticated_client.post(f"{BASE_URL}/api/trades", json={
            "league_id": league["id"],
            "target_team_id": team2["id"],
            "assets_offered": [{"asset_type": "player", "player_id": test_players[5]["_id"]}],
            "assets_requested": [{"asset_type": "player", "player_id": test_players[6]["_id"]}]
        })
        assert create_response.status_code == 200
        trade_to_withdraw = create_response.json()["_id"]

        # Proposer withdraws
        response = authenticated_client.post(f"{BASE_URL}/api/trades/{trade_to_withdraw}/withdraw")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "withdrawn"
        print("PASS: Proposer withdrew trade")


# ═══════════════════════════════════════════════════════════════
# WAIVER WIRE TESTS
# ═══════════════════════════════════════════════════════════════

class TestWaiverAvailablePlayers:
    """Tests for GET /api/waivers/available - Get available players"""

    def test_get_waiver_players(self, api_client):
        """Test GET /api/waivers/available returns players"""
        response = api_client.get(f"{BASE_URL}/api/waivers/available")
        assert response.status_code == 200
        data = response.json()

        assert "players" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert len(data["players"]) > 0

        # Verify player structure
        player = data["players"][0]
        assert "id" in player
        assert "name" in player
        assert "position" in player
        assert "team" in player
        assert "points" in player
        assert "has_active_claim" in player

        # Store a player for claim testing
        pytest.waiver_player_id = player["id"]
        pytest.waiver_player_name = player["name"]
        print(f"PASS: GET /api/waivers/available returned {len(data['players'])} players")

    def test_get_waiver_players_with_search(self, api_client):
        """Test GET /api/waivers/available?search=McDavid"""
        response = api_client.get(f"{BASE_URL}/api/waivers/available?search=McDavid")
        assert response.status_code == 200
        data = response.json()

        assert len(data["players"]) >= 1
        mcdavid = next((p for p in data["players"] if "McDavid" in p["name"]), None)
        assert mcdavid is not None
        print("PASS: Search for McDavid in waivers works")

    def test_get_waiver_players_with_position_filter(self, api_client):
        """Test GET /api/waivers/available?position=G returns goalies"""
        response = api_client.get(f"{BASE_URL}/api/waivers/available?position=G")
        assert response.status_code == 200
        data = response.json()

        for player in data["players"]:
            assert player["position"] == "G"
        print(f"PASS: Position filter G returned {len(data['players'])} goalies")


class TestWaiverClaim:
    """Tests for POST /api/waivers/claim - Place FAAB bid"""

    def test_place_claim_without_auth_fails(self, api_client, test_league_and_teams):
        """Test POST /api/waivers/claim without auth returns 401"""
        if not hasattr(pytest, 'waiver_player_id'):
            pytest.skip("No waiver player available")

        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/waivers/claim", json={
            "league_id": test_league_and_teams["league"]["id"],
            "player_id": pytest.waiver_player_id,
            "bid_amount": 10
        })
        assert response.status_code == 401
        print("PASS: Place claim without auth returns 401")

    def test_place_waiver_claim_success(self, authenticated_client, test_league_and_teams):
        """Test POST /api/waivers/claim places a bid successfully"""
        if not hasattr(pytest, 'waiver_player_id'):
            pytest.skip("No waiver player available")

        league_id = test_league_and_teams["league"]["id"]

        response = authenticated_client.post(f"{BASE_URL}/api/waivers/claim", json={
            "league_id": league_id,
            "player_id": pytest.waiver_player_id,
            "bid_amount": 15
        })
        assert response.status_code == 200, f"Failed to place claim: {response.text}"
        data = response.json()

        assert "_id" in data
        assert data["league_id"] == league_id
        assert data["player_id"] == pytest.waiver_player_id
        assert data["player_name"] == pytest.waiver_player_name
        assert data["bid_amount"] == 15
        assert data["status"] == "pending"
        assert "team_id" in data
        assert "team_name" in data
        assert "created_at" in data

        pytest.waiver_claim_id = data["_id"]
        print(f"PASS: Placed waiver claim for {data['player_name']} with $15 bid")

    def test_place_duplicate_claim_fails(self, authenticated_client, test_league_and_teams):
        """Test POST /api/waivers/claim duplicate claim returns 400"""
        if not hasattr(pytest, 'waiver_player_id'):
            pytest.skip("No waiver player available")

        response = authenticated_client.post(f"{BASE_URL}/api/waivers/claim", json={
            "league_id": test_league_and_teams["league"]["id"],
            "player_id": pytest.waiver_player_id,
            "bid_amount": 20
        })
        assert response.status_code == 400
        data = response.json()
        assert "already" in data["detail"].lower() or "pending" in data["detail"].lower()
        print("PASS: Duplicate waiver claim returns 400")

    def test_place_claim_over_budget_fails(self, authenticated_client, test_league_and_teams, test_players):
        """Test POST /api/waivers/claim with bid > budget returns 400"""
        # Use a different player
        player_id = test_players[7]["_id"] if len(test_players) > 7 else test_players[1]["_id"]

        response = authenticated_client.post(f"{BASE_URL}/api/waivers/claim", json={
            "league_id": test_league_and_teams["league"]["id"],
            "player_id": player_id,
            "bid_amount": 500  # Way over $100 budget
        })
        assert response.status_code == 400
        data = response.json()
        assert "budget" in data["detail"].lower() or "insufficient" in data["detail"].lower()
        print("PASS: Bid over budget returns 400")


class TestWaiverClaimsList:
    """Tests for GET /api/waivers/claims - List waiver claims"""

    def test_get_all_claims(self, api_client):
        """Test GET /api/waivers/claims returns list of claims"""
        response = api_client.get(f"{BASE_URL}/api/waivers/claims")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        print(f"PASS: GET /api/waivers/claims returned {len(data)} claims")

    def test_get_claims_by_league(self, api_client, test_league_and_teams):
        """Test GET /api/waivers/claims?league_id={id} filters by league"""
        league_id = test_league_and_teams["league"]["id"]
        response = api_client.get(f"{BASE_URL}/api/waivers/claims?league_id={league_id}")
        assert response.status_code == 200
        data = response.json()

        for claim in data:
            assert claim["league_id"] == league_id
        print(f"PASS: Filtered claims by league, found {len(data)}")

    def test_get_my_claims(self, authenticated_client):
        """Test GET /api/waivers/claims?my_claims=true returns user's claims"""
        response = authenticated_client.get(f"{BASE_URL}/api/waivers/claims?my_claims=true")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 1  # Should have at least the claim we placed
        print(f"PASS: GET my_claims returned {len(data)} claims")

    def test_get_claims_by_status(self, api_client):
        """Test GET /api/waivers/claims?status=pending filters by status"""
        response = api_client.get(f"{BASE_URL}/api/waivers/claims?status=pending")
        assert response.status_code == 200
        data = response.json()

        for claim in data:
            assert claim["status"] == "pending"
        print(f"PASS: Filtered claims by status=pending, found {len(data)}")


class TestWaiverClaimCancel:
    """Tests for DELETE /api/waivers/claims/{id} - Cancel pending claim"""

    def test_cancel_claim_without_auth_fails(self, api_client):
        """Test DELETE /api/waivers/claims/{id} without auth returns 401"""
        if not hasattr(pytest, 'waiver_claim_id'):
            pytest.skip("No waiver claim to cancel")

        fresh_session = requests.Session()
        response = fresh_session.delete(f"{BASE_URL}/api/waivers/claims/{pytest.waiver_claim_id}")
        assert response.status_code == 401
        print("PASS: Cancel claim without auth returns 401")

    def test_cancel_claim_not_found(self, authenticated_client):
        """Test DELETE /api/waivers/claims/{id} with invalid id returns 404"""
        response = authenticated_client.delete(f"{BASE_URL}/api/waivers/claims/000000000000000000000000")
        assert response.status_code == 404
        print("PASS: Cancel non-existent claim returns 404")

    def test_cancel_claim_wrong_user_fails(self, second_user_client):
        """Test DELETE /api/waivers/claims/{id} by non-owner returns 403"""
        if not hasattr(pytest, 'waiver_claim_id'):
            pytest.skip("No waiver claim to cancel")

        response = second_user_client.delete(f"{BASE_URL}/api/waivers/claims/{pytest.waiver_claim_id}")
        assert response.status_code == 403
        print("PASS: Cancel claim by non-owner returns 403")


class TestWaiverBudget:
    """Tests for GET /api/waivers/budget - Get FAAB budget"""

    def test_get_budget_without_auth_fails(self, api_client, test_league_and_teams):
        """Test GET /api/waivers/budget without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/waivers/budget?league_id={test_league_and_teams['league']['id']}")
        assert response.status_code == 401
        print("PASS: Get budget without auth returns 401")

    def test_get_budget_success(self, authenticated_client, test_league_and_teams):
        """Test GET /api/waivers/budget returns budget info"""
        league_id = test_league_and_teams["league"]["id"]
        response = authenticated_client.get(f"{BASE_URL}/api/waivers/budget?league_id={league_id}")
        assert response.status_code == 200
        data = response.json()

        assert "team_id" in data
        assert "league_id" in data
        assert "total_budget" in data
        assert "spent" in data
        assert "remaining" in data
        assert data["total_budget"] == 100.0  # Default FAAB budget
        assert data["remaining"] <= 100.0

        print(f"PASS: Budget - Total: ${data['total_budget']}, Spent: ${data['spent']}, Remaining: ${data['remaining']}")


class TestWaiverOrder:
    """Tests for GET /api/waivers/order - Get waiver priority order"""

    def test_get_waiver_order(self, api_client, test_league_and_teams):
        """Test GET /api/waivers/order returns priority order"""
        league_id = test_league_and_teams["league"]["id"]
        response = api_client.get(f"{BASE_URL}/api/waivers/order?league_id={league_id}")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 2  # Should have at least 2 teams

        # Verify order structure
        for i, team in enumerate(data):
            assert team["rank"] == i + 1
            assert "team_id" in team
            assert "team_name" in team
            assert "owner_name" in team
            assert "wins" in team
            assert "losses" in team

        print(f"PASS: Waiver order returned {len(data)} teams")


class TestWaiverHistory:
    """Tests for GET /api/waivers/history - Get processed claims history"""

    def test_get_waiver_history(self, api_client):
        """Test GET /api/waivers/history returns processed claims"""
        response = api_client.get(f"{BASE_URL}/api/waivers/history")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # All returned claims should be processed (won/lost/processed)
        for claim in data:
            assert claim["status"] in ["won", "lost", "processed"]

        print(f"PASS: Waiver history returned {len(data)} processed claims")

    def test_get_waiver_history_by_league(self, api_client, test_league_and_teams):
        """Test GET /api/waivers/history?league_id={id} filters by league"""
        league_id = test_league_and_teams["league"]["id"]
        response = api_client.get(f"{BASE_URL}/api/waivers/history?league_id={league_id}")
        assert response.status_code == 200
        data = response.json()

        for claim in data:
            assert claim["league_id"] == league_id
        print(f"PASS: Filtered waiver history by league, found {len(data)}")


class TestWaiverProcess:
    """Tests for POST /api/waivers/process - Commissioner processes claims"""

    def test_process_waivers_without_auth_fails(self, api_client, test_league_and_teams):
        """Test POST /api/waivers/process without auth returns 401"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/waivers/process?league_id={test_league_and_teams['league']['id']}")
        assert response.status_code == 401
        print("PASS: Process waivers without auth returns 401")

    def test_process_waivers_non_commissioner_fails(self, second_user_client, test_league_and_teams):
        """Test POST /api/waivers/process by non-commissioner returns 403"""
        league_id = test_league_and_teams["league"]["id"]
        response = second_user_client.post(f"{BASE_URL}/api/waivers/process?league_id={league_id}")
        assert response.status_code == 403
        data = response.json()
        assert "commissioner" in data["detail"].lower()
        print("PASS: Process waivers by non-commissioner returns 403")

    def test_process_waivers_success(self, authenticated_client, test_league_and_teams):
        """Test POST /api/waivers/process processes pending claims"""
        league_id = test_league_and_teams["league"]["id"]

        response = authenticated_client.post(f"{BASE_URL}/api/waivers/process?league_id={league_id}&force=true")
        assert response.status_code == 200
        data = response.json()

        assert data["processed"] >= 1, data
        assert "results" in data

        if data["processed"] > 0:
            assert "results" in data
            for result in data["results"]:
                assert "player" in result
                assert "winner" in result
                assert "bid" in result

        print(f"PASS: Processed {data['processed']} waiver claims")


class TestCancelClaimAfterProcess:
    """Test cancelling a claim after processing"""

    def test_cancel_processed_claim_fails(self, authenticated_client, test_league_and_teams, test_players):
        """Test DELETE /api/waivers/claims/{id} on processed claim returns 400"""
        # First, create a new claim
        league_id = test_league_and_teams["league"]["id"]
        player_id = test_players[8]["_id"] if len(test_players) > 8 else test_players[2]["_id"]

        claim_response = authenticated_client.post(f"{BASE_URL}/api/waivers/claim", json={
            "league_id": league_id,
            "player_id": player_id,
            "bid_amount": 5
        })

        if claim_response.status_code != 200:
            pytest.skip("Could not create claim for this test")

        claim_id = claim_response.json()["_id"]

        # Process waivers
        authenticated_client.post(f"{BASE_URL}/api/waivers/process?league_id={league_id}&force=true")

        # Try to cancel the processed claim
        response = authenticated_client.delete(f"{BASE_URL}/api/waivers/claims/{claim_id}")
        assert response.status_code == 400
        data = response.json()
        assert "not pending" in data["detail"].lower()
        print("PASS: Cancel processed claim returns 400")


# ═══════════════════════════════════════════════════════════════
# EXISTING FEATURES VERIFICATION
# ═══════════════════════════════════════════════════════════════

class TestExistingFeatures:
    """Verify existing features still work after trade/waiver engine addition"""

    def test_login_still_works(self, api_client):
        """Test POST /api/auth/login still works"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
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
        assert data["total"] >= 1000
        print(f"PASS: Players endpoint still works, total: {data['total']}")

    def test_drafts_still_work(self, api_client):
        """Test GET /api/drafts still works"""
        response = api_client.get(f"{BASE_URL}/api/drafts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Drafts endpoint still works, found {len(data)} drafts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

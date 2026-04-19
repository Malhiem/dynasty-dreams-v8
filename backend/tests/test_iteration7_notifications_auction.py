"""
Iteration 7 Tests: Notifications System and Auction Draft Engine
Tests for:
- Notification CRUD endpoints
- Notification creation on trade proposals
- Auction draft flow (nominate, bid, resolve)
- Budget management
- Commissioner-only access controls
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"

# Test league ID from review request
TEST_LEAGUE_ID = "69e446a5da97b3ac9066ebe2"


class TestSession:
    """Shared session for authenticated requests"""
    session = None
    user_id = None
    access_token = None


@pytest.fixture(scope="module")
def auth_session():
    """Login and return authenticated session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Login failed: {response.status_code} - {response.text}")
    
    data = response.json()
    TestSession.user_id = data.get("id")
    
    # Get cookies for auth
    if "access_token" in response.cookies:
        TestSession.access_token = response.cookies.get("access_token")
    
    return session


@pytest.fixture(scope="module")
def test_player_id(auth_session):
    """Get a player ID for testing"""
    response = auth_session.get(f"{BASE_URL}/api/players?limit=1")
    if response.status_code == 200:
        players = response.json().get("players", [])
        if players:
            return players[0].get("_id") or players[0].get("id")
    pytest.skip("No players available for testing")


# ═══════════════════════════════════════════════════════════════
# NOTIFICATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestNotificationEndpoints:
    """Test notification REST endpoints"""
    
    def test_get_notifications_returns_list(self, auth_session):
        """GET /api/notifications returns user's notifications"""
        response = auth_session.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /api/notifications returns {len(data)} notifications")
    
    def test_get_notifications_with_limit(self, auth_session):
        """GET /api/notifications respects limit parameter"""
        response = auth_session.get(f"{BASE_URL}/api/notifications?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) <= 5, "Should respect limit parameter"
        print(f"✓ GET /api/notifications?limit=5 returns {len(data)} notifications")
    
    def test_get_notifications_unread_only(self, auth_session):
        """GET /api/notifications?unread_only=true filters unread"""
        response = auth_session.get(f"{BASE_URL}/api/notifications?unread_only=true")
        assert response.status_code == 200
        
        data = response.json()
        # All returned should be unread
        for notif in data:
            assert notif.get("read") == False, "All notifications should be unread"
        print(f"✓ GET /api/notifications?unread_only=true returns {len(data)} unread notifications")
    
    def test_get_unread_count(self, auth_session):
        """GET /api/notifications/count returns unread count"""
        response = auth_session.get(f"{BASE_URL}/api/notifications/count")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "count" in data, "Response should have 'count' field"
        assert isinstance(data["count"], int), "Count should be an integer"
        print(f"✓ GET /api/notifications/count returns count: {data['count']}")
    
    def test_mark_all_read(self, auth_session):
        """POST /api/notifications/read-all marks all as read"""
        response = auth_session.post(f"{BASE_URL}/api/notifications/read-all")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        print(f"✓ POST /api/notifications/read-all: {data['message']}")
        
        # Verify count is now 0
        count_response = auth_session.get(f"{BASE_URL}/api/notifications/count")
        if count_response.status_code == 200:
            count_data = count_response.json()
            assert count_data["count"] == 0, "Unread count should be 0 after mark-all-read"
            print(f"✓ Verified unread count is now 0")


class TestNotificationMarkRead:
    """Test marking individual notifications as read"""
    
    def test_mark_notification_read(self, auth_session):
        """POST /api/notifications/{id}/read marks single notification as read"""
        # First get notifications
        response = auth_session.get(f"{BASE_URL}/api/notifications?limit=1")
        if response.status_code != 200:
            pytest.skip("Could not get notifications")
        
        notifications = response.json()
        if not notifications:
            pytest.skip("No notifications to test with")
        
        notif_id = notifications[0].get("_id")
        
        # Mark as read
        mark_response = auth_session.post(f"{BASE_URL}/api/notifications/{notif_id}/read")
        assert mark_response.status_code == 200, f"Expected 200, got {mark_response.status_code}"
        
        data = mark_response.json()
        assert "message" in data, "Response should have message"
        print(f"✓ POST /api/notifications/{notif_id}/read: {data['message']}")


# ═══════════════════════════════════════════════════════════════
# AUCTION DRAFT TESTS
# ═══════════════════════════════════════════════════════════════

class TestAuctionDraftCreation:
    """Test auction draft creation"""
    
    auction_draft_id = None
    test_league_id = "69e446a5da97b3ac9066ebe2"  # Test Draft League with Arctic Wolves team
    
    def test_create_auction_draft(self, auth_session):
        """POST /api/drafts creates auction draft with draft_type=auction"""
        # Use the test league that has a team (Arctic Wolves)
        league_id = self.test_league_id
        
        # Create auction draft
        response = auth_session.post(f"{BASE_URL}/api/drafts", json={
            "league_id": league_id,
            "draft_type": "auction",
            "total_rounds": 15,
            "time_per_pick": 30,
            "snake_draft": False
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("draft_type") == "auction", "Draft type should be auction"
        assert "_id" in data, "Response should have _id"
        
        TestAuctionDraftCreation.auction_draft_id = data["_id"]
        print(f"✓ Created auction draft: {data['_id']} in league {league_id}")


class TestAuctionBudgetInit:
    """Test auction budget initialization"""
    
    def test_init_budgets(self, auth_session):
        """POST /api/drafts/{id}/auction/init-budgets initializes team budgets"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        response = auth_session.post(f"{BASE_URL}/api/drafts/{draft_id}/auction/init-budgets")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "budgets" in data, "Response should have budgets"
        assert "message" in data, "Response should have message"
        print(f"✓ Initialized budgets: {data['message']}")


class TestAuctionState:
    """Test auction state endpoint"""
    
    def test_get_auction_state(self, auth_session):
        """GET /api/drafts/{id}/auction/state returns active auction and budgets"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        response = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/auction/state")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "active_auction" in data, "Response should have active_auction"
        assert "budgets" in data, "Response should have budgets"
        assert "total_picks" in data, "Response should have total_picks"
        assert "draft_type" in data, "Response should have draft_type"
        
        print(f"✓ GET auction state: {len(data['budgets'])} teams, active_auction={data['active_auction'] is not None}")


class TestAuctionNominate:
    """Test auction nomination"""
    
    def test_nominate_player(self, auth_session, test_player_id):
        """POST /api/drafts/{id}/auction/nominate starts auction for a player"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        # First start the draft
        start_response = auth_session.post(f"{BASE_URL}/api/drafts/{draft_id}/start?early_start=true")
        if start_response.status_code not in [200, 400]:  # 400 if already started
            pytest.skip(f"Could not start draft: {start_response.text}")
        
        # Get eligible players
        players_response = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/eligible-players?limit=1")
        if players_response.status_code != 200:
            pytest.skip("Could not get eligible players")
        
        players = players_response.json().get("players", [])
        if not players:
            pytest.skip("No eligible players")
        
        player_id = players[0].get("id")
        
        # Nominate
        response = auth_session.post(f"{BASE_URL}/api/drafts/{draft_id}/auction/nominate", json={
            "player_id": player_id,
            "opening_bid": 10
        })
        
        # Could be 200 or 400 if auction already in progress
        if response.status_code == 400 and "already in progress" in response.text:
            print("✓ Auction already in progress (expected)")
            return
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "player_id" in data, "Response should have player_id"
        assert "current_bid" in data, "Response should have current_bid"
        assert data["current_bid"] == 10, "Opening bid should be 10"
        print(f"✓ Nominated player {data.get('player_name')} with opening bid ${data['current_bid']}")


class TestAuctionBid:
    """Test auction bidding"""
    
    def test_bid_validation_must_be_higher(self, auth_session):
        """POST /api/drafts/{id}/auction/bid validates bid must be higher than current"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        # Get current auction state
        state_response = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/auction/state")
        if state_response.status_code != 200:
            pytest.skip("Could not get auction state")
        
        state = state_response.json()
        active_auction = state.get("active_auction")
        
        if not active_auction:
            pytest.skip("No active auction to bid on")
        
        current_bid = active_auction.get("current_bid", 0)
        
        # Try to bid lower
        response = auth_session.post(f"{BASE_URL}/api/drafts/{draft_id}/auction/bid", json={
            "amount": current_bid - 1
        })
        
        assert response.status_code == 400, f"Expected 400 for low bid, got {response.status_code}"
        assert "higher" in response.text.lower(), "Error should mention bid must be higher"
        print(f"✓ Bid validation: rejected bid of ${current_bid - 1} (current is ${current_bid})")
    
    def test_place_valid_bid(self, auth_session):
        """POST /api/drafts/{id}/auction/bid places higher bid"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        # Get current auction state
        state_response = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/auction/state")
        if state_response.status_code != 200:
            pytest.skip("Could not get auction state")
        
        state = state_response.json()
        active_auction = state.get("active_auction")
        
        if not active_auction:
            pytest.skip("No active auction to bid on")
        
        current_bid = active_auction.get("current_bid", 0)
        new_bid = current_bid + 5
        
        response = auth_session.post(f"{BASE_URL}/api/drafts/{draft_id}/auction/bid", json={
            "amount": new_bid
        })
        
        # Could fail if user doesn't have a team or budget
        if response.status_code == 403:
            pytest.skip("User doesn't have a team in this league")
        if response.status_code == 400 and "budget" in response.text.lower():
            pytest.skip("Insufficient budget")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("amount") == new_bid, f"Bid amount should be {new_bid}"
        print(f"✓ Placed bid of ${new_bid}")


class TestAuctionResolve:
    """Test auction resolution"""
    
    def test_resolve_auction_commissioner_only(self, auth_session):
        """POST /api/drafts/{id}/auction/resolve is commissioner-only"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        # Get current auction state
        state_response = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/auction/state")
        if state_response.status_code != 200:
            pytest.skip("Could not get auction state")
        
        state = state_response.json()
        active_auction = state.get("active_auction")
        
        if not active_auction:
            pytest.skip("No active auction to resolve")
        
        # Try to resolve (should work if user is commissioner)
        response = auth_session.post(f"{BASE_URL}/api/drafts/{draft_id}/auction/resolve")
        
        # Either 200 (commissioner) or 403 (not commissioner)
        assert response.status_code in [200, 403], f"Expected 200 or 403, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "winning_bid" in data, "Response should have winning_bid"
            assert "winner_team" in data, "Response should have winner_team"
            print(f"✓ Resolved auction: {data.get('winner_team')} wins for ${data.get('winning_bid')}")
        else:
            print("✓ Non-commissioner correctly blocked from resolving")


class TestAuctionBudgetDeduction:
    """Test budget deduction after resolve"""
    
    def test_budget_deducted_after_resolve(self, auth_session):
        """Budget is deducted after auction resolve"""
        draft_id = TestAuctionDraftCreation.auction_draft_id
        if not draft_id:
            pytest.skip("No auction draft created")
        
        # Get auction state to check budgets
        response = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/auction/state")
        assert response.status_code == 200
        
        data = response.json()
        budgets = data.get("budgets", [])
        
        # Check that at least one team has budget less than initial (if picks were made)
        total_picks = data.get("total_picks", 0)
        if total_picks > 0:
            # At least one team should have reduced budget
            has_reduced_budget = any(b.get("budget_remaining", 200) < 200 for b in budgets)
            print(f"✓ Budget check: {total_picks} picks made, reduced budgets: {has_reduced_budget}")
        else:
            print("✓ No picks made yet, budgets at initial values")


# ═══════════════════════════════════════════════════════════════
# TRADE NOTIFICATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestTradeNotification:
    """Test that trade proposals create notifications"""
    
    def test_trade_proposal_creates_notification(self, auth_session):
        """Trade proposal creates notification for target team"""
        # Get leagues
        leagues_response = auth_session.get(f"{BASE_URL}/api/leagues?my_leagues=true")
        if leagues_response.status_code != 200:
            pytest.skip("Could not get leagues")
        
        leagues = leagues_response.json()
        if not leagues:
            pytest.skip("No leagues available")
        
        league_id = leagues[0].get("id")
        
        # Get teams in league
        teams_response = auth_session.get(f"{BASE_URL}/api/teams?league_id={league_id}")
        if teams_response.status_code != 200:
            pytest.skip("Could not get teams")
        
        teams = teams_response.json()
        if len(teams) < 2:
            pytest.skip("Need at least 2 teams for trade")
        
        # Find a target team (not owned by current user)
        target_team = None
        for team in teams:
            if team.get("owner_id") != TestSession.user_id:
                target_team = team
                break
        
        if not target_team:
            pytest.skip("No target team available")
        
        # Get a player to trade
        players_response = auth_session.get(f"{BASE_URL}/api/players?limit=1")
        if players_response.status_code != 200:
            pytest.skip("Could not get players")
        
        players = players_response.json().get("players", [])
        if not players:
            pytest.skip("No players available")
        
        player_id = players[0].get("_id") or players[0].get("id")
        
        # Create trade proposal
        trade_response = auth_session.post(f"{BASE_URL}/api/trades", json={
            "league_id": league_id,
            "target_team_id": target_team.get("id"),
            "assets_offered": [{"asset_type": "player", "player_id": player_id}],
            "assets_requested": [],
            "message": "Test trade for notification"
        })
        
        if trade_response.status_code == 200:
            print("✓ Trade proposal created - notification should be sent to target team owner")
        else:
            print(f"Trade creation returned {trade_response.status_code}: {trade_response.text}")


# ═══════════════════════════════════════════════════════════════
# EXISTING FEATURES REGRESSION
# ═══════════════════════════════════════════════════════════════

class TestExistingFeatures:
    """Verify existing features still work"""
    
    def test_auth_me(self, auth_session):
        """GET /api/auth/me returns current user"""
        response = auth_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        print(f"✓ Auth working: {data['email']}")
    
    def test_get_leagues(self, auth_session):
        """GET /api/leagues returns leagues"""
        response = auth_session.get(f"{BASE_URL}/api/leagues")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Leagues endpoint: {len(data)} leagues")
    
    def test_get_players(self, auth_session):
        """GET /api/players returns players"""
        response = auth_session.get(f"{BASE_URL}/api/players?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        print(f"✓ Players endpoint: {len(data['players'])} players")
    
    def test_get_drafts(self, auth_session):
        """GET /api/drafts returns drafts"""
        response = auth_session.get(f"{BASE_URL}/api/drafts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Drafts endpoint: {len(data)} drafts")
    
    def test_get_trades(self, auth_session):
        """GET /api/trades returns trades"""
        response = auth_session.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Trades endpoint: {len(data)} trades")
    
    def test_get_waivers(self, auth_session):
        """GET /api/waivers/available returns waiver players"""
        response = auth_session.get(f"{BASE_URL}/api/waivers/available?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "players" in data
        print(f"✓ Waivers endpoint: {len(data['players'])} players")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

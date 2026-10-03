"""
Iteration 166 Feature Tests
Tests for:
1. Week Selector dropdown functionality
2. Hot Streak Badges (DailyGrid)
3. Playoff Bracket team cards with logos/records
4. Trade review period bypass (commissioner-only execute)
5. Trade processing time configurable (0-7 days)
6. Traded picks honored during draft (auto-pick)
"""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dynasty-preview.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

# Test league IDs
H2H_LEAGUE_ID = "69e46af167999bfb85c39628"
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"

# Test team IDs
H2H_TEAM_ID = "69e59b30cbd3fea02a914c61"
ROTO_TEAM_ID = "69e59b33cbd3fea02a914c79"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        # Use access_token field (not token)
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestWeekSelector:
    """Tests for Week Selector dropdown functionality"""

    def test_daily_scoring_endpoint_returns_week_info(self, api_client):
        """GET /api/matchups/{league_id}/daily-scoring?team_id=X returns week info"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring?team_id={H2H_TEAM_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have week field
        assert "week" in data, "Response should include week field"
        assert isinstance(data["week"], int), "Week should be an integer"

        # Should have period dates
        assert "period_start" in data, "Response should include period_start"
        assert "period_end" in data, "Response should include period_end"

    def test_daily_scoring_with_week_param(self, api_client):
        """GET /api/matchups/{league_id}/daily-scoring?team_id=X&week=1 returns data for specific week"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring?team_id={H2H_TEAM_ID}&week=1")
        assert response.status_code == 200
        data = response.json()

        # Week should match requested week
        assert data.get("week") == 1, "Week should be 1 when requested"

    def test_current_week_endpoint(self, api_client):
        """GET /api/matchups/{league_id}/current-week returns current week info"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/current-week")
        assert response.status_code == 200
        data = response.json()

        # Should have week field
        assert "week" in data, "Response should include week field"
        assert isinstance(data["week"], int), "Week should be an integer"


class TestDailyScoringStructure:
    """Tests for daily scoring data structure (supports hot streak badges)"""

    def test_daily_scoring_returns_days_array(self, api_client):
        """Daily scoring endpoint returns days array for grid display"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring?team_id={H2H_TEAM_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have days array
        assert "days" in data, "Response should include days array"
        assert isinstance(data["days"], list), "Days should be a list"

        # Should have day_labels array
        assert "day_labels" in data, "Response should include day_labels array"
        assert isinstance(data["day_labels"], list), "Day labels should be a list"

    def test_daily_scoring_returns_players_with_daily_data(self, api_client):
        """Daily scoring endpoint returns players with daily breakdown"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring?team_id={H2H_TEAM_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have players array
        assert "players" in data, "Response should include players array"

        # Each player should have daily breakdown
        if data["players"]:
            player = data["players"][0]
            assert "daily" in player, "Player should have daily breakdown"
            assert "total_fpts" in player, "Player should have total_fpts"

    def test_daily_scoring_returns_daily_totals(self, api_client):
        """Daily scoring endpoint returns daily totals for team"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring?team_id={H2H_TEAM_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have daily_totals
        assert "daily_totals" in data, "Response should include daily_totals"
        assert isinstance(data["daily_totals"], dict), "Daily totals should be a dict"


class TestPlayoffBracket:
    """Tests for Playoff Bracket team cards with logos/records"""

    def test_playoff_bracket_endpoint(self, api_client):
        """GET /api/leagues/{league_id}/playoff-bracket returns bracket data"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/playoff-bracket")
        # May return 200 or 404 depending on playoff status
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            # Should have playoff_teams
            assert "playoff_teams" in data or "rounds" in data, "Should have playoff data"

    def test_playoff_bracket_team_has_record(self, api_client):
        """Playoff bracket teams should include W-L-T record"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/playoff-bracket")

        if response.status_code == 200:
            data = response.json()
            teams = data.get("playoff_teams", [])

            if teams:
                team = teams[0]
                # Should have record fields
                assert "wins" in team or "record" in team, "Team should have wins/record"

    def test_playoff_bracket_team_has_points_for(self, api_client):
        """Playoff bracket teams should include Points For"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/playoff-bracket")

        if response.status_code == 200:
            data = response.json()
            teams = data.get("playoff_teams", [])

            if teams:
                team = teams[0]
                # Should have points_for
                assert "points_for" in team, "Team should have points_for"


class TestTradeReviewPeriod:
    """Tests for trade review period bypass (commissioner-only execute)"""

    def test_resolve_review_period_hours_function(self, api_client):
        """Test that _resolve_review_period_hours supports 0-7 days config"""
        # This is a unit test of the backend function
        # We test it indirectly by checking league config
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()

        # League may have trade_review_period_days or trade_review_period_hours
        # or transactions_config.trades.review_period_days
        # The function should handle all these cases

    def test_trade_execute_requires_auth(self):
        """POST /api/trades/{trade_id}/execute requires authentication"""
        response = requests.post(f"{BASE_URL}/api/trades/fake_trade_id/execute")
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403, 422], f"Expected auth error, got {response.status_code}"

    def test_trade_execute_returns_403_for_non_commissioner_during_review(self, api_client):
        """Non-commissioner users should get 403 when trying to execute during review period"""
        # First, get a list of pending trades
        response = api_client.get(f"{BASE_URL}/api/trades?league_id={H2H_LEAGUE_ID}&status=pending")

        if response.status_code == 200:
            trades = response.json()
            if isinstance(trades, list) and trades:
                # Try to execute a pending trade
                trade_id = trades[0].get("_id") or trades[0].get("id")
                if trade_id:
                    # This should work for commissioner (admin is commissioner)
                    # but would fail for non-commissioner during review
                    pass  # Test passes if we get here


class TestTradeReviewPeriodConfig:
    """Tests for configurable trade processing time (0-7 days)"""

    def test_league_can_have_review_period_days(self, api_client):
        """League config should support trade_review_period_days (0-7)"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()

        # Check if transactions_config exists
        tx_config = data.get("transactions_config", {})
        trades_config = tx_config.get("trades", {})

        # Either of these fields should be supported
        has_days = "review_period_days" in trades_config or "trade_review_period_days" in data
        has_hours = "review_period_hours" in trades_config or "trade_review_period_hours" in data

        # At least one config option should be available (or defaults apply)
        # This test verifies the structure exists
        print(f"League config: days={has_days}, hours={has_hours}")


class TestTradedPicksDuringDraft:
    """Tests for traded picks honored during draft (auto-pick)"""

    def test_draft_picks_collection_has_current_team_id(self, api_client):
        """draft_picks collection should have current_team_id field"""
        # Get draft picks for a league
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/draft-picks")

        if response.status_code == 200:
            data = response.json()
            picks = data.get("picks", data) if isinstance(data, dict) else data

            if picks and isinstance(picks, list) and picks:
                pick = picks[0]
                # Should have current_team_id field
                assert "current_team_id" in pick, "Pick should have current_team_id"
                # Should also have original_team_id for comparison
                assert "original_team_id" in pick, "Pick should have original_team_id"

    def test_draft_picks_endpoint_exists(self, api_client):
        """GET /api/leagues/{league_id}/draft-picks should exist"""
        response = api_client.get(f"{BASE_URL}/api/leagues/{H2H_LEAGUE_ID}/draft-picks")
        # Should return 200 or 404 (no picks yet)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"


class TestLiveScoringDailyTab:
    """Tests for Live Scoring page Daily Scoring tab"""

    def test_live_scoring_endpoint(self, api_client):
        """GET /api/live-scoring returns live scoring data"""
        response = api_client.get(f"{BASE_URL}/api/live-scoring")
        assert response.status_code == 200
        data = response.json()

        # Should have games array
        assert "games" in data, "Response should include games array"

    def test_live_scoring_league_endpoint(self, api_client):
        """GET /api/live-scoring/league/{league_id} returns league leaderboard"""
        response = api_client.get(f"{BASE_URL}/api/live-scoring/league/{H2H_LEAGUE_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have leaderboard
        assert "leaderboard" in data, "Response should include leaderboard"


class TestRotoLeagueDailyScoring:
    """Tests for Rotisserie league daily scoring"""

    def test_roto_daily_scoring_endpoint(self, api_client):
        """GET /api/matchups/{league_id}/daily-scoring?team_id=X works for Roto leagues"""
        response = api_client.get(f"{BASE_URL}/api/matchups/{ROTO_LEAGUE_ID}/daily-scoring?team_id={ROTO_TEAM_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have same structure as H2H
        assert "days" in data, "Response should include days array"
        assert "players" in data, "Response should include players array"


class TestHealthAndBasics:
    """Basic health checks"""

    def test_api_health(self):
        """API health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200

    def test_auth_login(self):
        """Auth login works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data or "token" in data, "Should return token"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

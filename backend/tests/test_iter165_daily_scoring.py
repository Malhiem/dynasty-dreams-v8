"""
Iteration 165 - Daily Scoring Feature Tests
Tests the daily scoring endpoint and related functionality for:
- Matchup page daily scoring tabs
- Roster/Team page daily scoring tab
- Live Scoring page daily scoring tab
- Player Card Modal daily scoring section
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test leagues from agent context
H2H_LEAGUE_ID = "69e46af167999bfb85c3962b"
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"

# Test credentials
TEST_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
TEST_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for all tests"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    # Login
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

    return session


@pytest.fixture(scope="module")
def h2h_team_id(auth_session):
    """Get a team ID from the H2H league"""
    response = auth_session.get(f"{BASE_URL}/api/teams", params={"league_id": H2H_LEAGUE_ID})
    if response.status_code != 200:
        pytest.skip(f"Failed to get teams: {response.status_code}")

    teams = response.json()
    if not teams:
        pytest.skip("No teams found in H2H league")

    return teams[0]["id"]


@pytest.fixture(scope="module")
def roto_team_id(auth_session):
    """Get a team ID from the Rotisserie league"""
    response = auth_session.get(f"{BASE_URL}/api/teams", params={"league_id": ROTO_LEAGUE_ID})
    if response.status_code != 200:
        pytest.skip(f"Failed to get teams: {response.status_code}")

    teams = response.json()
    if not teams:
        pytest.skip("No teams found in Roto league")

    return teams[0]["id"]


class TestDailyScoringEndpoint:
    """Tests for GET /api/matchups/{league_id}/daily-scoring endpoint"""

    def test_daily_scoring_h2h_returns_200(self, auth_session, h2h_team_id):
        """Test daily scoring endpoint returns 200 for H2H league"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Daily scoring endpoint returns 200 for H2H league")

    def test_daily_scoring_roto_returns_200(self, auth_session, roto_team_id):
        """Test daily scoring endpoint returns 200 for Rotisserie league"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{ROTO_LEAGUE_ID}/daily-scoring",
            params={"team_id": roto_team_id}
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Daily scoring endpoint returns 200 for Rotisserie league")

    def test_daily_scoring_response_structure(self, auth_session, h2h_team_id):
        """Test daily scoring response has correct structure"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify required fields exist
        required_fields = [
            "league_id", "team_id", "team_name", "week", "scoring_format",
            "period_start", "period_end", "days", "day_labels", "players",
            "daily_totals", "period_total_fpts"
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify types
        assert isinstance(data["days"], list), "days should be a list"
        assert isinstance(data["day_labels"], list), "day_labels should be a list"
        assert isinstance(data["players"], list), "players should be a list"
        assert isinstance(data["daily_totals"], dict), "daily_totals should be a dict"
        assert isinstance(data["period_total_fpts"], (int, float)), "period_total_fpts should be numeric"

        # Verify days and day_labels have same length
        assert len(data["days"]) == len(data["day_labels"]), "days and day_labels should have same length"

        print(f"✓ Daily scoring response has correct structure")
        print(f"  - Week: {data['week']}")
        print(f"  - Period: {data['period_start']} to {data['period_end']}")
        print(f"  - Days count: {len(data['days'])}")
        print(f"  - Players count: {len(data['players'])}")
        print(f"  - Period total FPTS: {data['period_total_fpts']}")

    def test_daily_scoring_player_structure(self, auth_session, h2h_team_id):
        """Test player objects in daily scoring response have correct structure"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        assert response.status_code == 200
        data = response.json()

        if len(data["players"]) == 0:
            pytest.skip("No players in roster to test structure")

        player = data["players"][0]

        # Verify player fields
        player_fields = [
            "id", "name", "position", "team", "is_goalie",
            "total_fpts", "total_goals", "total_assists", "total_shots",
            "total_saves", "total_goals_against", "total_wins", "total_games", "daily"
        ]

        for field in player_fields:
            assert field in player, f"Missing player field: {field}"

        # Verify daily is a dict
        assert isinstance(player["daily"], dict), "player.daily should be a dict"

        print(f"✓ Player structure is correct")
        print(f"  - First player: {player['name']} ({player['position']}) - {player['team']}")
        print(f"  - Total FPTS: {player['total_fpts']}")
        print(f"  - Total games: {player['total_games']}")

    def test_daily_scoring_with_week_param(self, auth_session, h2h_team_id):
        """Test daily scoring endpoint accepts week parameter"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id, "week": 1}
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert data["week"] == 1, f"Expected week 1, got {data['week']}"
        print(f"✓ Daily scoring accepts week parameter (week={data['week']})")

    def test_daily_scoring_invalid_league(self, auth_session, h2h_team_id):
        """Test daily scoring returns 404 for invalid league"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/invalid_league_id/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        # Should return 400, 404 or 422 for invalid league
        assert response.status_code in [400, 404, 422], f"Expected 400/404/422, got {response.status_code}"
        print(f"✓ Daily scoring returns {response.status_code} for invalid league")

    def test_daily_scoring_invalid_team(self, auth_session):
        """Test daily scoring returns error for invalid team"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": "invalid_team_id"}
        )

        # Should return 400, 404 or 422 for invalid team
        assert response.status_code in [400, 404, 422], f"Expected 400/404/422, got {response.status_code}"
        print(f"✓ Daily scoring returns {response.status_code} for invalid team")

    def test_daily_scoring_requires_auth(self):
        """Test daily scoring endpoint requires authentication"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        response = session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": "some_team_id"}
        )

        # Should return 401 or 403 for unauthenticated request
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✓ Daily scoring requires authentication (returns {response.status_code})")


class TestDailyScoringDataIntegrity:
    """Tests for data integrity in daily scoring response"""

    def test_daily_totals_match_player_sums(self, auth_session, h2h_team_id):
        """Test that daily_totals match sum of player daily fpts"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        assert response.status_code == 200
        data = response.json()

        # For each day, sum player fpts and compare to daily_totals
        for day in data["days"]:
            expected_total = sum(
                p["daily"].get(day, {}).get("fpts", 0)
                for p in data["players"]
            )
            actual_total = data["daily_totals"].get(day, 0)

            # Allow small floating point differences
            assert abs(expected_total - actual_total) < 0.1, \
                f"Day {day}: expected {expected_total}, got {actual_total}"

        print(f"✓ Daily totals match player sums for all {len(data['days'])} days")

    def test_period_total_matches_player_sums(self, auth_session, h2h_team_id):
        """Test that period_total_fpts matches sum of player total_fpts"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        assert response.status_code == 200
        data = response.json()

        expected_total = sum(p["total_fpts"] for p in data["players"])
        actual_total = data["period_total_fpts"]

        # Allow small floating point differences
        assert abs(expected_total - actual_total) < 0.1, \
            f"Period total: expected {expected_total}, got {actual_total}"

        print(f"✓ Period total ({actual_total}) matches player sums")

    def test_day_labels_format(self, auth_session, h2h_team_id):
        """Test that day_labels are in expected format (e.g., 'Mon 10/7')"""
        response = auth_session.get(
            f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/daily-scoring",
            params={"team_id": h2h_team_id}
        )

        assert response.status_code == 200
        data = response.json()

        if len(data["day_labels"]) == 0:
            pytest.skip("No day labels to test")

        # Check first label has expected format
        label = data["day_labels"][0]
        parts = label.split(" ")

        # Should have day name and date
        assert len(parts) >= 2, f"Day label should have day name and date: {label}"

        # Day name should be 3 letters
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        assert parts[0] in day_names, f"Invalid day name in label: {label}"

        print(f"✓ Day labels are in correct format (e.g., '{label}')")


class TestCurrentWeekEndpoint:
    """Tests for GET /api/matchups/{league_id}/current-week endpoint"""

    def test_current_week_returns_200(self, auth_session):
        """Test current week endpoint returns 200"""
        response = auth_session.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/current-week")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Current week endpoint returns 200")

    def test_current_week_response_structure(self, auth_session):
        """Test current week response has correct structure"""
        response = auth_session.get(f"{BASE_URL}/api/matchups/{H2H_LEAGUE_ID}/current-week")

        assert response.status_code == 200
        data = response.json()

        assert "week" in data, "Missing 'week' field"
        assert "matchups" in data, "Missing 'matchups' field"
        assert isinstance(data["week"], int), "week should be an integer"
        assert isinstance(data["matchups"], list), "matchups should be a list"

        print(f"✓ Current week response structure is correct")
        print(f"  - Week: {data['week']}")
        print(f"  - Matchups count: {len(data['matchups'])}")


class TestLiveScoringEndpoints:
    """Tests for live scoring endpoints used by daily scoring feature"""

    def test_live_scoring_summary(self, auth_session):
        """Test live scoring summary endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/live-scoring")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Should have games array
        assert "games" in data, "Missing 'games' field"
        assert isinstance(data["games"], list), "games should be a list"

        print(f"✓ Live scoring summary returns 200")
        print(f"  - Games count: {len(data['games'])}")

    def test_live_scoring_league(self, auth_session):
        """Test live scoring league endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/live-scoring/league/{H2H_LEAGUE_ID}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Should have leaderboard
        assert "leaderboard" in data, "Missing 'leaderboard' field"
        assert isinstance(data["leaderboard"], list), "leaderboard should be a list"

        print(f"✓ Live scoring league endpoint returns 200")
        print(f"  - Leaderboard entries: {len(data['leaderboard'])}")

    def test_live_scoring_team(self, auth_session, h2h_team_id):
        """Test live scoring team endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/live-scoring/team/{h2h_team_id}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Should have players array
        assert "players" in data, "Missing 'players' field"
        assert isinstance(data["players"], list), "players should be a list"

        print(f"✓ Live scoring team endpoint returns 200")
        print(f"  - Players count: {len(data['players'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

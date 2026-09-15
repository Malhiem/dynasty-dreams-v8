"""API tests for Roto standings endpoints — iteration 153.

Tests:
- GET /api/leagues/{id}/roto/standings returns correct structure
- GET /api/leagues/{id}/roto/matchup returns correct structure with ranks
- Categories include team_stats, points, and ranks dictionaries
- Totals sum correctly
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ROTO_LEAGUE_ID = "69e46af167999bfb85c39629"  # Stat Chasers Roto league
H2H_LEAGUE_ID = "69e46af167999bfb85c3962a"  # Frozen Dynasty (non-roto)


@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@dynastydreams.com",
        "password": "Admin123!"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestRotoStandingsEndpoint:
    """Tests for GET /api/leagues/{id}/roto/standings"""

    def test_standings_returns_200(self, auth_headers):
        """Standings endpoint returns 200 for roto league."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_standings_has_categories_array(self, auth_headers):
        """Response includes categories array."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        assert "categories" in data, "Missing 'categories' in response"
        assert isinstance(data["categories"], list), "categories should be a list"
        assert len(data["categories"]) > 0, "categories should not be empty"

    def test_category_has_required_fields(self, auth_headers):
        """Each category has team_stats, points, and ranks dictionaries."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        for cat in data["categories"]:
            assert "key" in cat, f"Category missing 'key': {cat}"
            assert "label" in cat, f"Category missing 'label': {cat}"
            assert "team_stats" in cat, f"Category {cat['key']} missing 'team_stats'"
            assert "points" in cat, f"Category {cat['key']} missing 'points'"
            assert "ranks" in cat, f"Category {cat['key']} missing 'ranks'"
            assert "higher_is_better" in cat, f"Category {cat['key']} missing 'higher_is_better'"
            # Verify they are dictionaries keyed by team_id
            assert isinstance(cat["team_stats"], dict), f"team_stats should be dict"
            assert isinstance(cat["points"], dict), f"points should be dict"
            assert isinstance(cat["ranks"], dict), f"ranks should be dict"

    def test_standings_has_totals(self, auth_headers):
        """Response includes totals with team_name and total_points."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        assert "totals" in data, "Missing 'totals' in response"
        assert isinstance(data["totals"], dict), "totals should be a dict"
        # Check structure of a total entry
        for tid, t in data["totals"].items():
            assert "team_name" in t, f"Total for {tid} missing team_name"
            assert "total_points" in t, f"Total for {tid} missing total_points"

    def test_totals_equal_sum_of_category_points(self, auth_headers):
        """Each team's total equals sum of its category points."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        for tid, t in data["totals"].items():
            expected_total = sum(
                cat["points"].get(tid, 0) for cat in data["categories"]
            )
            actual_total = t["total_points"]
            assert abs(actual_total - expected_total) < 0.01, \
                f"Team {tid}: expected total {expected_total}, got {actual_total}"

    def test_standings_has_num_teams(self, auth_headers):
        """Response includes num_teams count."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        assert "num_teams" in data, "Missing 'num_teams'"
        assert data["num_teams"] == 14, f"Expected 14 teams, got {data['num_teams']}"


class TestRotoMatchupEndpoint:
    """Tests for GET /api/leagues/{id}/roto/matchup"""

    def test_matchup_returns_200(self, auth_headers):
        """Matchup endpoint returns 200."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/matchup",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_matchup_includes_ranks(self, auth_headers):
        """Matchup response includes ranks in each category."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/matchup",
            headers=auth_headers
        )
        data = resp.json()
        assert "categories" in data
        for cat in data["categories"]:
            assert "ranks" in cat, f"Category {cat.get('key')} missing 'ranks'"
            assert isinstance(cat["ranks"], dict), "ranks should be dict"


class TestRotoRecomputeEndpoint:
    """Tests for POST /api/leagues/{id}/roto/recompute"""

    def test_recompute_returns_200(self, auth_headers):
        """Recompute endpoint returns 200 for admin."""
        resp = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/recompute",
            headers=auth_headers,
            json={"period": None, "close": False}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_recompute_returns_leader_info(self, auth_headers):
        """Recompute response includes leader info."""
        resp = requests.post(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/recompute",
            headers=auth_headers,
            json={"period": None, "close": False}
        )
        data = resp.json()
        assert data.get("ok") is True
        assert "num_teams" in data
        assert "leader" in data


class TestRotoUnauthorized:
    """Tests for unauthorized access."""

    def test_standings_requires_auth(self):
        """Standings endpoint requires authentication."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings"
        )
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"


class TestRotoAllTiedScenario:
    """Tests for the all-tied scenario (14 teams with 0 stats)."""

    def test_all_tied_ranks_are_1(self, auth_headers):
        """When all teams have same stat, all get rank 1."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        # Check first category (goals) - all should be rank 1
        goals_cat = next((c for c in data["categories"] if c["key"] == "goals"), None)
        assert goals_cat is not None, "Goals category not found"
        for tid, rank in goals_cat["ranks"].items():
            assert rank == 1, f"Team {tid} expected rank 1, got {rank}"

    def test_all_tied_points_are_split(self, auth_headers):
        """When all 14 teams tied, each gets avg(1..14) = 7.5 points."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        goals_cat = next((c for c in data["categories"] if c["key"] == "goals"), None)
        assert goals_cat is not None
        # avg(1..14) = (1+2+...+14)/14 = 105/14 = 7.5
        for tid, pts in goals_cat["points"].items():
            assert pts == 7.5, f"Team {tid} expected 7.5 pts, got {pts}"

    def test_all_tied_total_is_90(self, auth_headers):
        """With 12 categories and 7.5 pts each, total = 90."""
        resp = requests.get(
            f"{BASE_URL}/api/leagues/{ROTO_LEAGUE_ID}/roto/standings",
            headers=auth_headers
        )
        data = resp.json()
        for tid, t in data["totals"].items():
            assert t["total_points"] == 90, \
                f"Team {tid} expected total 90, got {t['total_points']}"

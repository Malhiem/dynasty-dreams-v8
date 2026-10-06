"""Tests for the ELO-based skill rating system."""
import os
import sys

import pytest
from httpx import AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


# ─── Pure helpers ────────────────────────────────────────────────────
def test_elo_expected_score_balanced():
    from routes.ratings import expected_score
    assert abs(expected_score(1500, 1500) - 0.5) < 1e-9


def test_elo_expected_score_higher_favored():
    from routes.ratings import expected_score
    # 400-point gap → ~9% expected for the underdog, ~91% for the favorite
    e = expected_score(1900, 1500)
    assert 0.90 < e < 0.92


def test_elo_update_higher_wins_small_delta():
    """Higher-rated team beating lower-rated team → small rating gain."""
    from routes.ratings import update_pair
    new_a, new_b, delta = update_pair(1700, 1500, 1.0, k=32)
    # Expected score was ~0.76, so delta_a = 32 * (1 - 0.76) ≈ 7.7
    assert 5 < delta < 10
    assert new_a > 1700
    assert new_b < 1500
    assert abs((new_a - 1700) + (new_b - 1500)) < 1e-6  # zero-sum


def test_elo_update_underdog_wins_big_delta():
    from routes.ratings import update_pair
    _, _, delta = update_pair(1300, 1500, 1.0, k=32)
    # Expected was ~0.24, so delta = 32 * (1 - 0.24) ≈ 24.3
    assert 20 < delta < 28


def test_elo_update_tie_balanced_no_change():
    from routes.ratings import update_pair
    _, _, delta = update_pair(1500, 1500, 0.5, k=32)
    assert abs(delta) < 1e-9


def test_tier_for_percentile():
    from routes.ratings import tier_for_percentile
    assert tier_for_percentile(5) == "Rookie"
    assert tier_for_percentile(25) == "Contender"
    assert tier_for_percentile(50) == "Veteran"
    assert tier_for_percentile(70) == "All-Star"
    assert tier_for_percentile(85) == "Hall of Famer"
    assert tier_for_percentile(96) == "Elite"
    assert tier_for_percentile(99.5) == "Legend"
    assert tier_for_percentile(100) == "Legend"


# ─── Endpoint contracts ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tier_definitions_endpoint():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.get("/api/ratings/tiers")
        assert r.status_code == 200
        body = r.json()
        names = [t["name"] for t in body["tiers"]]
        assert names == ["Rookie", "Contender", "Veteran", "All-Star",
                         "Hall of Famer", "Elite", "Legend"]
        assert body["start_rating"] == 1500.0
        assert body["k_factor"] == 32.0


@pytest.mark.asyncio
async def test_team_rating_default_value():
    """A team that hasn't played any matchups returns rating=1500 + tier=Veteran."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.post("/api/auth/login",
                              json={"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"),
                                    "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")})
        token = r.json()["access_token"]
        teams = await client.get(
            "/api/teams",
            headers={"Authorization": f"Bearer {token}"},
            params={"league_id": "69e46af167999bfb85c39628"},
        )
        team_id = teams.json()[0]["id"]
        r = await client.get(f"/api/teams/{team_id}/rating")
        assert r.status_code == 200
        body = r.json()
        assert body["rating"] == 1500.0
        assert body["tier"] in ("Veteran", "Rookie", "Contender", "All-Star",
                                "Hall of Famer", "Elite", "Legend")
        assert "history" in body


@pytest.mark.asyncio
async def test_user_and_league_rating_endpoints():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.get("/api/u/suite_owner/rating")
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "suite_owner"
        assert body["teams_count"] >= 1
        assert body["rating"] >= 0
        assert "tier" in body

        # League rating
        r = await client.get("/api/leagues/69e46af167999bfb85c39628/rating")
        assert r.status_code == 200
        body = r.json()
        assert body["teams_count"] >= 1
        assert "tier" in body
        assert len(body["team_ratings"]) >= 1


@pytest.mark.asyncio
async def test_username_rating_404():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.get("/api/u/__does_not_exist__/rating")
        assert r.status_code == 404


# ─── Profile trophy-case shape ───────────────────────────────────────
@pytest.mark.asyncio
async def test_profile_has_active_leagues_and_split_trophies():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.get("/api/u/suite_owner")
        assert r.status_code == 200
        body = r.json()
        # New fields present
        assert "active_leagues" in body
        assert isinstance(body["active_leagues"], list)
        # New trophy types present in stats counter
        assert "runner_ups" in body["stats"]
        assert "regular_season_top3" in body["stats"]
        # Trophy entries should carry league_is_private flag
        for tr in body["trophies"]:
            assert "league_is_private" in tr
        # All active leagues should be flagged is_active and carry league_is_private
        for al in body["active_leagues"]:
            assert al["is_active"] is True
            assert "league_is_private" in al

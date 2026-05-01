"""Tests for live-scoring league leaderboard enrichment (iter 61).

Validates that /api/live-scoring/league/{id} now returns:
- live_points_against  (opponent's live points from current matchup)
- matchup_id           (grouping key when a league has 2+ matchups)
- opponent_team_id
- projected_rank_change (signed delta vs. pre-week rank, i.e. by points_for)
- pre_rank + projected_rank
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
USER_EMAIL = "chriszarek@gmail.com"
USER_PASSWORD = "Chris2026!"
LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings (H2H, 12 teams)


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_live_scoring_league_leaderboard_new_fields():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/live-scoring/league/{LEAGUE_ID}", headers=h)
        assert r.status_code == 200, r.text
        rows = r.json()["leaderboard"]
        assert len(rows) > 0

        for row in rows:
            assert "live_points" in row
            assert "live_points_against" in row
            assert "opponent_team_id" in row
            assert "matchup_id" in row
            assert "pre_rank" in row
            assert "projected_rank" in row
            assert "projected_rank_change" in row
            assert isinstance(row["projected_rank_change"], int)


@pytest.mark.asyncio
async def test_live_points_against_matches_opponent_live_points():
    """For any team with an opponent in the matchup, row.live_points_against
    should equal the opponent's row.live_points."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/live-scoring/league/{LEAGUE_ID}", headers=h)
        rows = r.json()["leaderboard"]
        by_id = {row["team_id"]: row for row in rows}
        for row in rows:
            opp_id = row.get("opponent_team_id")
            if not opp_id or opp_id not in by_id:
                continue
            opp = by_id[opp_id]
            assert abs(row["live_points_against"] - opp["live_points"]) < 0.01, (
                f"Team {row['team_name']} LPA={row['live_points_against']} "
                f"but opponent {opp['team_name']} LP={opp['live_points']}"
            )


@pytest.mark.asyncio
async def test_preweek_projection_and_delta_present_and_stable():
    """Iter 62: every leaderboard row must include numeric `preweek_projection`
    and `projection_delta`. Repeated calls in the same week must return the
    SAME projection per team (cached on team.preweek_projections)."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r1 = await client.get(f"/api/live-scoring/league/{LEAGUE_ID}", headers=h)
        assert r1.status_code == 200, r1.text
        rows1 = r1.json()["leaderboard"]
        assert len(rows1) > 0
        for row in rows1:
            assert "preweek_projection" in row
            assert "projection_delta" in row
            assert isinstance(row["preweek_projection"], (int, float))
            assert isinstance(row["projection_delta"], (int, float))
            # Sanity: clamped projection range
            assert 60.0 <= float(row["preweek_projection"]) <= 300.0
            # Delta math must be self-consistent
            expected_delta = round(float(row["live_points"]) - float(row["preweek_projection"]), 2)
            assert abs(row["projection_delta"] - expected_delta) < 0.01

        # Stability across calls
        r2 = await client.get(f"/api/live-scoring/league/{LEAGUE_ID}", headers=h)
        rows2 = {row["team_id"]: row for row in r2.json()["leaderboard"]}
        for row in rows1:
            tid = row["team_id"]
            assert tid in rows2
            assert abs(rows2[tid]["preweek_projection"] - row["preweek_projection"]) < 0.01, (
                f"Team {tid} projection changed between calls: "
                f"{row['preweek_projection']} -> {rows2[tid]['preweek_projection']}"
            )


@pytest.mark.asyncio
async def test_live_points_against_still_present_backend():
    """Backend should NOT have removed live_points_against — only the UI changed."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/live-scoring/league/{LEAGUE_ID}", headers=h)
        rows = r.json()["leaderboard"]
        for row in rows:
            assert "live_points_against" in row, "live_points_against must remain in API response"


@pytest.mark.asyncio
async def test_matchup_id_groups_pairs():
    """Each matchup_id should appear on exactly 2 team rows (home + away)."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/live-scoring/league/{LEAGUE_ID}", headers=h)
        rows = r.json()["leaderboard"]
        from collections import Counter
        mid_counts = Counter(row["matchup_id"] for row in rows if row.get("matchup_id"))
        # At least one matchup pair; every tracked id must be paired
        assert len(mid_counts) > 0
        for mid, n in mid_counts.items():
            assert n == 2, f"matchup_id {mid} appears {n} times (should be exactly 2)"

"""Focused unit tests for `routes/roster.py` (read-side endpoints).

We only exercise `GET /roster/{team_id}` (the light list) because the
`/detail` variant lazily imports `live_scoring_worker` which pulls in the
whole live-scoring graph. Live-stat behavior is covered by the existing
integration tests (`test_iteration*`).
"""
import os
import sys

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import roster as roster_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


def _stub_calc(player, _config=None):
    """Identity-ish fantasy points: just points * 1.0 + goals * 0.5.

    Lets the tests assert deterministic ordering without dragging in the
    real scoring config.
    """
    return float(player.get("points", 0)) + 0.5 * float(player.get("goals", 0))


async def _seed_team_with_players(db, *, roster_size=3, with_lineup=False):
    """Insert a league + team + N players. Returns (team_id, [player_ids])."""
    league_res = await db.leagues.insert_one({
        "name": "Roster Test League",
        "commissioner_id": "test_user_0001",
    })
    league_id = str(league_res.inserted_id)

    player_ids = []
    # Players with distinct point totals so ordering is verifiable.
    specs = [
        ("Star", "C", 95, 40),
        ("Mid", "LW", 60, 20),
        ("Goalie", "G", 0, 0),
    ][:roster_size]
    for name, pos, pts, g in specs:
        res = await db.players.insert_one({
            "name": name, "position": pos, "team": "TST",
            "points": pts, "goals": g, "assists": pts - g,
            "games_played": 50,
            "player_type": "goalie" if pos == "G" else "skater",
        })
        player_ids.append(str(res.inserted_id))

    lineup = {}
    if with_lineup:
        lineup[player_ids[0]] = {"section": "starting", "slot": "C1"}
        lineup[player_ids[1]] = {"section": "bench"}
        if len(player_ids) > 2:
            lineup[player_ids[2]] = {"section": "goalies", "slot": "G1"}

    team_res = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": "test_user_0001",
        "owner_name": "Owner",
        "name": "Test Team",
        "roster": player_ids,
        "lineup": lineup,
    })
    return str(team_res.inserted_id), player_ids


@pytest.mark.asyncio
async def test_get_roster_404_when_team_missing():
    async with isolated_router_app(roster_routes) as ctx:
        # Inject the missing dep that the live server normally provides.
        roster_routes._deps["calculate_fantasy_points"] = _stub_calc
        # A valid but non-existent ObjectId
        missing_id = str(ObjectId())
        r = await ctx.client.get(f"/api/roster/{missing_id}")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_roster_returns_players_sorted_by_fpts_desc():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_calc
        team_id, _ = await _seed_team_with_players(ctx.db, roster_size=3)
        r = await ctx.client.get(f"/api/roster/{team_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["team_id"] == team_id
        assert body["team_name"] == "Test Team"
        names = [p["name"] for p in body["players"]]
        # Star (95+20=115) > Mid (60+10=70) > Goalie (0)
        assert names == ["Star", "Mid", "Goalie"]


@pytest.mark.asyncio
async def test_get_roster_honors_lineup_section_override():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_calc
        team_id, pids = await _seed_team_with_players(ctx.db, with_lineup=True)
        r = await ctx.client.get(f"/api/roster/{team_id}")
        body = r.json()
        by_name = {p["name"]: p for p in body["players"]}
        assert by_name["Star"]["roster_section"] == "starting"
        assert by_name["Mid"]["roster_section"] == "bench"
        assert by_name["Goalie"]["roster_section"] == "goalies"


@pytest.mark.asyncio
async def test_get_roster_skips_missing_player_docs():
    """Defensive: roster lists a player_id that no longer exists. The
    endpoint should silently skip it (not raise) so the UI still loads."""
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_calc
        team_id, pids = await _seed_team_with_players(ctx.db, roster_size=2)
        # Delete one player to simulate the stale-id scenario
        await ctx.db.players.delete_one({"_id": ObjectId(pids[1])})
        r = await ctx.client.get(f"/api/roster/{team_id}")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["players"]]
        assert names == ["Star"]


@pytest.mark.asyncio
async def test_get_roster_empty_when_team_has_no_roster():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_calc
        team_res = await ctx.db.teams.insert_one({
            "league_id": "any",
            "owner_id": "test_user_0001",
            "owner_name": "Owner",
            "name": "Empty",
            "roster": [],
        })
        r = await ctx.client.get(f"/api/roster/{team_res.inserted_id}")
        assert r.status_code == 200
        assert r.json()["players"] == []

"""Focused unit tests for the new roster write-side endpoints
(extracted in iter 98)."""
import os
import sys

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import roster as roster_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


def _stub_fpts(player, _config=None):
    """Synth fantasy points roughly tracks `points` so tier thresholds
    work in the salary-synthesis path."""
    return float(player.get("points", 0))


async def _seed_team(db, *, league_id, owner_id="test_user_0001", roster=None):
    res = await db.teams.insert_one({
        "league_id": league_id, "owner_id": owner_id,
        "owner_name": "Owner", "name": "Test Team",
        "roster": roster or [], "lineup": {},
    })
    return str(res.inserted_id)


async def _seed_league(db, *, roster_spots=20, salary_cap=None, ir_mode=None):
    doc = {"name": "L", "commissioner_id": "test_user_0001",
           "roster_spots": roster_spots}
    if salary_cap:
        doc["salary_cap_enabled"] = True
        doc["salary_cap"] = salary_cap
    if ir_mode:
        doc["injury_reserve_compliance_mode"] = ir_mode
    res = await db.leagues.insert_one(doc)
    return str(res.inserted_id)


async def _seed_player(db, *, name="P", position="C", points=20):
    res = await db.players.insert_one({
        "name": name, "position": position, "team": "TST",
        "points": points, "goals": 0, "assists": 0,
        "games_played": 40, "player_type": "skater",
    })
    return str(res.inserted_id)


# ─── /add ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_404_when_team_missing():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        r = await ctx.client.post(
            f"/api/roster/{ObjectId()}/add",
            json={"player_id": str(ObjectId())},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_403_when_not_owner():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        league_id = await _seed_league(ctx.db)
        team_id = await _seed_team(ctx.db, league_id=league_id, owner_id="someone_else")
        pid = await _seed_player(ctx.db)
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add", json={"player_id": pid},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_add_400_when_roster_full():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        league_id = await _seed_league(ctx.db, roster_spots=1)
        existing = await _seed_player(ctx.db, name="Existing")
        team_id = await _seed_team(ctx.db, league_id=league_id, roster=[existing])
        new_pid = await _seed_player(ctx.db, name="New")
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add", json={"player_id": new_pid},
        )
        assert r.status_code == 400
        assert "Roster full" in r.json()["detail"]


@pytest.mark.asyncio
async def test_add_400_when_player_already_on_roster():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        league_id = await _seed_league(ctx.db)
        pid = await _seed_player(ctx.db)
        team_id = await _seed_team(ctx.db, league_id=league_id, roster=[pid])
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add", json={"player_id": pid},
        )
        assert r.status_code == 400
        assert "already on roster" in r.json()["detail"]


@pytest.mark.asyncio
async def test_add_400_when_over_cap():
    """Adding a high-points player to a team near the cap should fail
    with a clear "over the salary cap by $X" message."""
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        # $10M cap, $9M already used (1 mid-tier player), adding a star
        league_id = await _seed_league(ctx.db, salary_cap=10_000_000)
        existing = await _seed_player(ctx.db, name="MidA", points=60)  # tier ~$6M
        team_id = await _seed_team(
            ctx.db, league_id=league_id, roster=[existing],
        )
        # Manually set salary_used to a high baseline so the cap math fails
        await ctx.db.teams.update_one(
            {"_id": ObjectId(team_id)}, {"$set": {"salary_used": 9_000_000}},
        )
        star = await _seed_player(ctx.db, name="Star", points=110)  # ~$11.7M
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add", json={"player_id": star},
        )
        assert r.status_code == 400
        assert "over the salary cap" in r.json()["detail"]


@pytest.mark.asyncio
async def test_add_happy_path_pushes_and_logs_activity():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        log_calls: list = []

        async def fake_log(*args, **kwargs):
            log_calls.append((args, kwargs))

        roster_routes._deps["log_activity"] = fake_log

        league_id = await _seed_league(ctx.db)
        pid = await _seed_player(ctx.db, name="McDavid", points=110)
        team_id = await _seed_team(ctx.db, league_id=league_id)

        r = await ctx.client.post(
            f"/api/roster/{team_id}/add", json={"player_id": pid},
        )
        assert r.status_code == 200
        assert "Added McDavid" in r.json()["message"]
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert pid in team["roster"]
        assert team["salary_used"] > 0  # recompute fired
        assert len(log_calls) == 1
        assert log_calls[0][0][1] == "roster_add"


# ─── /drop ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_404_when_team_missing():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        r = await ctx.client.post(
            f"/api/roster/{ObjectId()}/drop",
            json={"player_id": str(ObjectId())},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_drop_400_when_player_not_on_roster():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        league_id = await _seed_league(ctx.db)
        team_id = await _seed_team(ctx.db, league_id=league_id)
        r = await ctx.client.post(
            f"/api/roster/{team_id}/drop",
            json={"player_id": str(ObjectId())},
        )
        assert r.status_code == 400
        assert "not on roster" in r.json()["detail"]


@pytest.mark.asyncio
async def test_drop_happy_path_pulls_and_logs():
    async with isolated_router_app(roster_routes) as ctx:
        roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
        log_calls: list = []

        async def fake_log(*args, **kwargs):
            log_calls.append((args, kwargs))

        roster_routes._deps["log_activity"] = fake_log

        league_id = await _seed_league(ctx.db)
        pid = await _seed_player(ctx.db, name="DropMe", points=20)
        team_id = await _seed_team(ctx.db, league_id=league_id, roster=[pid])

        r = await ctx.client.post(
            f"/api/roster/{team_id}/drop", json={"player_id": pid},
        )
        assert r.status_code == 200
        assert "Dropped DropMe" in r.json()["message"]
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert pid not in team["roster"]
        assert len(log_calls) == 1
        assert log_calls[0][0][1] == "roster_drop"


# ─── salary synthesis edge cases ──────────────────────────────


def test_synthesize_player_salary_honours_explicit_aav():
    roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
    p = {"name": "X", "contract": {"aav": 6_500_000}, "points": 0}
    assert roster_routes._synthesize_player_salary(p) == 6_500_000


def test_synthesize_player_salary_bounds_check():
    roster_routes._deps["calculate_fantasy_points"] = _stub_fpts
    # Floor: minimum NHL salary
    floor = roster_routes._synthesize_player_salary({"points": 0, "name": "Rook"})
    assert floor >= 775_000
    # Ceiling: even superstars don't exceed the synthesis ceiling
    sup = roster_routes._synthesize_player_salary({"points": 200, "name": "GOAT"})
    assert sup <= 13_500_000

"""Focused unit tests for `routes/leagues.py`.

We hit the highest-value read + write endpoints — divisions, schedule
config, veto threshold preview — against an ephemeral database. Heavy
endpoints (`/leagues/{id}/standings`, `/leagues/{id}/playoff-bracket`) are
exercised indirectly by the broader matchup/playoff suites in the live
test DB and aren't refactored here to avoid duplicating their seed work.
"""
import os
import sys

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import leagues as leagues_routes  # noqa: E402

from tests.router_test_utils import (  # noqa: E402
    isolated_router_app,
    seed_league,
    seed_team,
)


# ─── Divisions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_divisions_buckets_teams_and_reports_unassigned():
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        # Two teams in East/Atlantic, one team unassigned.
        await ctx.db.teams.insert_many([
            {"league_id": league_id, "name": "A1",
             "division": "Atlantic", "conference": "East", "owner_id": "u1"},
            {"league_id": league_id, "name": "A2",
             "division": "Atlantic", "conference": "East", "owner_id": "u2"},
            {"league_id": league_id, "name": "U", "owner_id": "u3"},
        ])
        r = await ctx.client.get(f"/api/leagues/{league_id}/divisions")
        body = r.json()
        assert len(body["divisions"]) == 1
        atl = body["divisions"][0]
        assert atl["division"] == "Atlantic"
        assert atl["conference"] == "East"
        assert {t["name"] for t in atl["teams"]} == {"A1", "A2"}
        assert [u["name"] for u in body["unassigned"]] == ["U"]


@pytest.mark.asyncio
async def test_put_divisions_blocks_non_commissioner():
    async with isolated_router_app(
        leagues_routes,
        user={"_id": "not_commish", "id": "not_commish", "name": "Other"},
    ) as ctx:
        league_id = await seed_league(ctx.db, commissioner_id="real_commish")
        r = await ctx.client.put(
            f"/api/leagues/{league_id}/divisions",
            json={"assignments": []},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_put_divisions_rejects_save_that_leaves_team_unassigned():
    """Every team in the league must end up with BOTH division AND
    conference after the save — partial assignments are rejected."""
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id, name="T1")
        other_team = await seed_team(ctx.db, league_id=league_id, name="T2")
        r = await ctx.client.put(
            f"/api/leagues/{league_id}/divisions",
            json={
                "assignments": [
                    {"team_id": team_id, "division": "Atlantic", "conference": "East"},
                    # other_team intentionally NOT assigned — must 400
                ]
            },
        )
        assert r.status_code == 400
        # The endpoint returns a structured error detail dict with `code`,
        # `message`, and `missing` fields — not a flat string.
        detail = r.json()["detail"]
        assert detail["code"] == "incomplete_league_structure"
        assert len(detail["missing"]) >= 1


@pytest.mark.asyncio
async def test_put_divisions_happy_path_persists():
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        t1 = await seed_team(ctx.db, league_id=league_id, name="T1")
        t2 = await seed_team(ctx.db, league_id=league_id, name="T2")
        r = await ctx.client.put(
            f"/api/leagues/{league_id}/divisions",
            json={
                "assignments": [
                    {"team_id": t1, "division": "Atlantic", "conference": "East"},
                    {"team_id": t2, "division": "Pacific", "conference": "West"},
                ]
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] == 2

        # Verify persistence
        t1_doc = await ctx.db.teams.find_one({"_id": ObjectId(t1)})
        assert t1_doc["division"] == "Atlantic"
        assert t1_doc["conference"] == "East"


# ─── Schedule config ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_schedule_config_returns_defaults_when_unset():
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        r = await ctx.client.get(f"/api/leagues/{league_id}/schedule-config")
        body = r.json()
        assert body["intra_division_games"] == 2
        assert body["intra_conference_games"] == 1
        assert body["inter_conference_games"] == 1
        assert body["configured"] is False


@pytest.mark.asyncio
async def test_put_schedule_config_validates_range():
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        # 99 games per matchup is outside the 0-10 range → 400
        r = await ctx.client.put(
            f"/api/leagues/{league_id}/schedule-config",
            json={
                "intra_division_games": 99,
                "intra_conference_games": 1,
                "inter_conference_games": 1,
            },
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_put_schedule_config_happy_path_persists():
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        r = await ctx.client.put(
            f"/api/leagues/{league_id}/schedule-config",
            json={
                "intra_division_games": 4,
                "intra_conference_games": 2,
                "inter_conference_games": 1,
            },
        )
        assert r.status_code == 200
        assert r.json()["saved"]["intra_division_games"] == 4

        # Read-back returns configured=True after save
        got = (await ctx.client.get(f"/api/leagues/{league_id}/schedule-config")).json()
        assert got["configured"] is True
        assert got["intra_division_games"] == 4


# ─── Veto threshold preview ────────────────────────────────────


@pytest.mark.asyncio
async def test_veto_threshold_preview_uses_ceil():
    """50% of a 12-team league must require 6 teams (not 5.5)."""
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"current_teams": 12, "trade_veto_threshold_pct": 50}},
        )
        r = await ctx.client.get(f"/api/leagues/{league_id}/veto-threshold-preview")
        body = r.json()
        assert body["pct"] == 50
        assert body["total_teams"] == 12
        assert body["teams_required"] == 6
        assert body["enabled"] is True
        assert "6 teams required" in body["description"]


@pytest.mark.asyncio
async def test_veto_threshold_preview_disabled_when_pct_zero():
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"current_teams": 10}},
        )
        r = await ctx.client.get(f"/api/leagues/{league_id}/veto-threshold-preview?pct=0")
        body = r.json()
        assert body["enabled"] is False
        assert body["teams_required"] == 0
        assert "disabled" in body["description"].lower()


@pytest.mark.asyncio
async def test_veto_threshold_preview_partial_majority_rounds_up():
    """An 8-team league at 51% needs ceil(8 × 0.51) = 5 teams (strict majority)."""
    async with isolated_router_app(leagues_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"current_teams": 8}},
        )
        r = await ctx.client.get(f"/api/leagues/{league_id}/veto-threshold-preview?pct=51")
        assert r.json()["teams_required"] == 5

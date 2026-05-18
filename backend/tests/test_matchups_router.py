"""Focused unit tests for `routes/matchups.py` read-side endpoints.

Schedule generation + simulate-week are integration-heavy (depend on
trade evaluator + awards + push) and are covered by
`test_schedule_config_and_division_crown.py` + `test_crown_flow.py`.
These tests pin the simple read endpoints.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import matchups as matchups_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_matchups(db, league_id="L1"):
    await db.matchups.insert_many([
        {"league_id": league_id, "week": 1, "status": "completed",
         "home_team_id": "TA", "home_team_name": "A",
         "away_team_id": "TB", "away_team_name": "B",
         "home_score": 100.0, "away_score": 80.0, "winner": "TA"},
        {"league_id": league_id, "week": 2, "status": "scheduled",
         "home_team_id": "TA", "home_team_name": "A",
         "away_team_id": "TC", "away_team_name": "C"},
        {"league_id": league_id, "week": 3, "status": "scheduled",
         "home_team_id": "TB", "home_team_name": "B",
         "away_team_id": "TC", "away_team_name": "C"},
    ])


@pytest.mark.asyncio
async def test_get_matchups_returns_all_sorted_by_week():
    async with isolated_router_app(matchups_routes) as ctx:
        await _seed_matchups(ctx.db)
        r = await ctx.client.get("/api/matchups/L1")
        assert r.status_code == 200
        body = r.json()
        assert [m["week"] for m in body] == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_matchups_filtered_by_week():
    async with isolated_router_app(matchups_routes) as ctx:
        await _seed_matchups(ctx.db)
        r = await ctx.client.get("/api/matchups/L1?week=2")
        body = r.json()
        assert len(body) == 1
        assert body[0]["week"] == 2


@pytest.mark.asyncio
async def test_current_week_returns_earliest_scheduled():
    async with isolated_router_app(matchups_routes) as ctx:
        await _seed_matchups(ctx.db)
        # Week 1 is completed, so current = min(scheduled) = 2
        r = await ctx.client.get("/api/matchups/L1/current-week")
        body = r.json()
        assert body["week"] == 2
        assert len(body["matchups"]) == 1


@pytest.mark.asyncio
async def test_current_week_defaults_to_1_when_nothing_scheduled():
    async with isolated_router_app(matchups_routes) as ctx:
        await ctx.db.matchups.insert_one({
            "league_id": "L1", "week": 5, "status": "completed",
            "home_team_id": "TA", "away_team_id": "TB",
        })
        r = await ctx.client.get("/api/matchups/L1/current-week")
        body = r.json()
        assert body["week"] == 1
        assert body["matchups"] == []


@pytest.mark.asyncio
async def test_week_results():
    async with isolated_router_app(matchups_routes) as ctx:
        await _seed_matchups(ctx.db)
        r = await ctx.client.get("/api/matchups/L1/results?week=1")
        body = r.json()
        assert len(body) == 1
        assert body[0]["winner"] == "TA"
        assert body[0]["home_score"] == 100.0


@pytest.mark.asyncio
async def test_get_matchups_empty_league_returns_empty_list():
    async with isolated_router_app(matchups_routes) as ctx:
        r = await ctx.client.get("/api/matchups/UNKNOWN")
        assert r.status_code == 200
        assert r.json() == []

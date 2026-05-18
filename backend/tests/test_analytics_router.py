"""Focused unit tests for `routes/analytics.py`."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import analytics as analytics_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_summary(db, *, league_id, season, team_id, week, pf, pa, win=False, loss=False, tie=False):
    await db.week_summaries.insert_one({
        "league_id": league_id, "season": season,
        "week": week, "team_id": team_id, "team_name": f"T{team_id}",
        "points_for": float(pf), "points_against": float(pa),
        "win": win, "loss": loss, "tie": tie,
    })


@pytest.mark.asyncio
async def test_weekly_analytics_team_specific():
    async with isolated_router_app(analytics_routes) as ctx:
        league_id = "L1"
        # Team A: 3 weeks of data
        for wk, pf, pa, w, l in [(1, 100, 80, True, False), (2, 90, 95, False, True), (3, 110, 100, True, False)]:
            await _seed_summary(ctx.db, league_id=league_id, season="2025-26",
                                team_id="TA", week=wk, pf=pf, pa=pa, win=w, loss=l)
        # Team B: parallel weeks so league avg is non-trivial
        for wk, pf in [(1, 60), (2, 70), (3, 80)]:
            await _seed_summary(ctx.db, league_id=league_id, season="2025-26",
                                team_id="TB", week=wk, pf=pf, pa=0)

        r = await ctx.client.get(
            f"/api/leagues/{league_id}/weekly-analytics",
            params={"team_id": "TA", "season": "2025-26"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["team_id"] == "TA"
        assert body["season"] == "2025-26"
        assert len(body["weeks"]) == 3
        assert body["weeks"][0]["pointsFor"] == 100.0
        assert body["weeks"][0]["leagueAvg"] == 80.0  # (100+60)/2
        assert body["season_summary"]["wins"] == 2
        assert body["season_summary"]["losses"] == 1
        assert body["season_summary"]["weeks_played"] == 3


@pytest.mark.asyncio
async def test_weekly_analytics_league_wide_no_team_filter():
    async with isolated_router_app(analytics_routes) as ctx:
        for wk, pf in [(1, 100), (1, 50)]:
            await _seed_summary(ctx.db, league_id="L1", season="2025-26",
                                team_id=f"T_{pf}", week=wk, pf=pf, pa=0)
        r = await ctx.client.get(
            "/api/leagues/L1/weekly-analytics", params={"season": "2025-26"},
        )
        body = r.json()
        assert body["team_id"] is None
        assert body["weeks"][0]["matchups_played"] == 1   # 2 teams = 1 matchup
        assert body["weeks"][0]["pointsFor"] == 150.0


@pytest.mark.asyncio
async def test_weekly_analytics_yoy_groups_seasons():
    async with isolated_router_app(analytics_routes) as ctx:
        league_id = "L1"
        await _seed_summary(ctx.db, league_id=league_id, season="2024-25",
                            team_id="TA", week=1, pf=80, pa=70, win=True)
        await _seed_summary(ctx.db, league_id=league_id, season="2025-26",
                            team_id="TA", week=1, pf=120, pa=90, win=True)
        r = await ctx.client.get(
            f"/api/leagues/{league_id}/weekly-analytics",
            params={"team_id": "TA", "season": "2025-26"},
        )
        yoy = r.json()["year_over_year"]
        seasons = [y["season"] for y in yoy]
        assert "2024-25" in seasons and "2025-26" in seasons


@pytest.mark.asyncio
async def test_backfill_404_when_no_matchups():
    async with isolated_router_app(analytics_routes) as ctx:
        r = await ctx.client.post("/api/leagues/L1/backfill-week-summaries")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_backfill_writes_summaries_idempotently():
    async with isolated_router_app(analytics_routes) as ctx:
        # Seed one completed matchup
        await ctx.db.matchups.insert_one({
            "league_id": "L1", "season": "2025-26", "week": 1, "status": "completed",
            "home_team_id": "TA", "home_team_name": "TA",
            "away_team_id": "TB", "away_team_name": "TB",
            "home_score": 100.0, "away_score": 80.0, "winner": "TA",
        })
        r1 = await ctx.client.post("/api/leagues/L1/backfill-week-summaries?season=2025-26")
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["rows_inserted"] == 2  # one per side

        # Second call: same matchups upsert → 0 new inserts, 2 updates
        r2 = await ctx.client.post("/api/leagues/L1/backfill-week-summaries?season=2025-26")
        b2 = r2.json()
        assert b2["rows_inserted"] == 0
        assert b2["rows_updated"] == 2

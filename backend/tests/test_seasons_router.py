"""Focused unit tests for `routes/seasons.py` health-score + season list endpoints.

The complete-season + renew-season flows touch dozens of collections and
are covered by the existing `test_player_dynasty_career.py` integration
suite. These tests pin the read-side + health-score scoring.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import seasons as seasons_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_league(db, **overrides):
    base = {
        "name": "Test League",
        "format": "head_to_head",
        "max_teams": 12,
        "commissioner_id": "test_user_0001",
    }
    base.update(overrides)
    res = await db.leagues.insert_one(base)
    return str(res.inserted_id)


@pytest.mark.asyncio
async def test_health_score_basics_only():
    """Minimal league with no cap/divisions/schedule/playoff/draft → only Basics passes."""
    async with isolated_router_app(seasons_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        r = await ctx.client.get(f"/api/leagues/{league_id}/health-score")
        assert r.status_code == 200
        body = r.json()
        # Only Basics is complete (16 points)
        assert body["score"] == 16
        missing = body["missing"]
        assert "basics" not in missing
        assert "cap" in missing
        assert "divisions" in missing


@pytest.mark.asyncio
async def test_health_score_cap_disabled_is_complete():
    async with isolated_router_app(seasons_routes) as ctx:
        league_id = await _seed_league(ctx.db, salary_cap_enabled=False)
        r = await ctx.client.get(f"/api/leagues/{league_id}/health-score")
        body = r.json()
        cap_section = next(s for s in body["sections"] if s["key"] == "cap")
        assert cap_section["complete"] is True


@pytest.mark.asyncio
async def test_health_score_fully_configured_hits_100():
    async with isolated_router_app(seasons_routes) as ctx:
        league_id = await _seed_league(
            ctx.db, salary_cap_enabled=True, salary_cap=88_000_000,
            playoff_teams=6,
        )
        # 2 teams in different divisions → divisions check passes
        await ctx.db.teams.insert_many([
            {"league_id": league_id, "name": "A", "division": "East", "owner_id": "u1"},
            {"league_id": league_id, "name": "B", "division": "West", "owner_id": "u2"},
        ])
        # Schedule + draft
        await ctx.db.matchups.insert_one({"league_id": league_id, "week": 1})
        await ctx.db.drafts.insert_one({"league_id": league_id, "name": "2025 Draft"})

        r = await ctx.client.get(f"/api/leagues/{league_id}/health-score")
        body = r.json()
        assert body["score"] == 100, body
        assert body["missing"] == []


@pytest.mark.asyncio
async def test_health_score_404_for_unknown_league():
    async with isolated_router_app(seasons_routes) as ctx:
        from bson import ObjectId
        r = await ctx.client.get(f"/api/leagues/{ObjectId()}/health-score")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_seasons_returns_descending_by_year():
    async with isolated_router_app(seasons_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        for yr in (2024, 2025, 2023):
            await ctx.db.league_seasons.insert_one({
                "league_id": league_id, "season_year": yr,
                "status": "complete", "snapshot_at": datetime.now(timezone.utc),
                "champion_team_name": f"Champ {yr}",
            })
        r = await ctx.client.get(f"/api/leagues/{league_id}/seasons")
        body = r.json()
        years = [s["season_year"] for s in body["seasons"]]
        assert years == [2025, 2024, 2023]


@pytest.mark.asyncio
async def test_list_seasons_include_team_stats():
    async with isolated_router_app(seasons_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await ctx.db.league_seasons.insert_one({
            "league_id": league_id, "season_year": 2025, "status": "complete",
            "snapshot_at": datetime.now(timezone.utc),
            "teams": [{"team_id": "T1", "team_name": "Cool Team",
                       "wins": 12, "losses": 4, "ties": 0,
                       "points_for": 1234.5, "points_against": 999.0,
                       "division": "East", "conference": "Eastern"}],
        })
        r = await ctx.client.get(
            f"/api/leagues/{league_id}/seasons?include_team_stats=true",
        )
        body = r.json()
        ts = body["seasons"][0]["team_stats"]
        assert ts[0]["wins"] == 12
        assert ts[0]["division"] == "East"


@pytest.mark.asyncio
async def test_get_specific_season_404_when_missing():
    async with isolated_router_app(seasons_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        r = await ctx.client.get(f"/api/leagues/{league_id}/seasons/1999")
        assert r.status_code == 404

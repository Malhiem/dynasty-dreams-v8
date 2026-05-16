"""Focused unit tests for `routes/ratings.py`.

Covers the public read endpoints — team rating, user rating (by id /
username / me), league rating, and tier definitions. The ELO-update
side of the router (post-matchup writes) lives in server.py and is
covered by the broader trade/matchup test suite; here we exercise the
read-side contract that the dashboard + profile screens rely on.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import ratings as ratings_routes  # noqa: E402

from tests.router_test_utils import (  # noqa: E402
    isolated_router_app,
    seed_league,
    seed_team,
)


@pytest.mark.asyncio
async def test_team_rating_returns_404_when_missing():
    async with isolated_router_app(ratings_routes) as ctx:
        r = await ctx.client.get("/api/teams/69d111111111111111111111/rating")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_team_rating_returns_payload_for_seeded_team():
    async with isolated_router_app(ratings_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id, name="Iron Sharks")
        # Seed rating + history
        await ctx.db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {
                "$set": {
                    "rating": 1610.0,
                    "peak_rating": 1650.5,
                    "rating_history": [
                        {"at": datetime.now(timezone.utc), "rating": 1500.0},
                        {"at": datetime.now(timezone.utc), "rating": 1610.0},
                    ],
                }
            },
        )
        r = await ctx.client.get(f"/api/teams/{team_id}/rating")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["team_id"] == team_id
        assert body["team_name"] == "Iron Sharks"
        assert body["rating"] == 1610.0
        assert body["peak_rating"] == 1650.5
        assert body["matchups_rated"] == 2
        assert isinstance(body["history"], list)
        assert body["history"][0]["at"] is not None
        # Tier mapping is exercised here; we don't pin the exact tier label
        # because TIERS may evolve, but it must be a non-empty string.
        assert isinstance(body["tier"], str) and body["tier"]


@pytest.mark.asyncio
async def test_user_rating_by_id_aggregates_over_teams():
    """A user's rating is the lifetime mean across their team rating_history's
    `rating_after` field (per the real implementation)."""
    async with isolated_router_app(ratings_routes) as ctx:
        u = await ctx.db.users.insert_one({
            "name": "Tester", "username": "tester", "email": "t@e.com",
        })
        uid = str(u.inserted_id)
        await ctx.db.teams.insert_many([
            {"name": "Team A", "owner_id": uid, "rating": 1600,
             "rating_history": [{"rating_after": 1500}, {"rating_after": 1700}]},
            {"name": "Team B", "owner_id": uid, "rating": 1500,
             "rating_history": [{"rating_after": 1500}, {"rating_after": 1500}]},
        ])
        r = await ctx.client.get(f"/api/users/{uid}/rating")
        body = r.json()
        assert body["teams_count"] == 2
        assert body["samples"] == 4
        # Mean of [1500, 1700, 1500, 1500] = 1550.
        assert body["rating"] == 1550.0


@pytest.mark.asyncio
async def test_user_rating_by_username_is_case_insensitive():
    async with isolated_router_app(ratings_routes) as ctx:
        u = await ctx.db.users.insert_one({
            "name": "Mixed", "username": "MixedCase", "email": "m@e.com",
        })
        uid = str(u.inserted_id)
        await ctx.db.teams.insert_one(
            {"name": "T", "owner_id": uid, "rating": 1550, "rating_history": []},
        )
        r = await ctx.client.get("/api/u/mixedcase/rating")
        assert r.status_code == 200
        assert r.json()["teams_count"] == 1


@pytest.mark.asyncio
async def test_user_rating_404_for_unknown_username():
    async with isolated_router_app(ratings_routes) as ctx:
        r = await ctx.client.get("/api/u/nope_doesnt_exist/rating")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_tier_definitions_returns_static_metadata():
    async with isolated_router_app(ratings_routes) as ctx:
        r = await ctx.client.get("/api/ratings/tiers")
        assert r.status_code == 200
        body = r.json()
        assert body["start_rating"] == ratings_routes.START_RATING
        assert body["k_factor"] == ratings_routes.K_FACTOR
        # Every tier exposes name + percentile bounds.
        assert all(
            {"name", "min_percentile", "max_percentile"} <= set(t.keys())
            for t in body["tiers"]
        )


@pytest.mark.asyncio
async def test_league_rating_returns_avg_and_top_three():
    async with isolated_router_app(ratings_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.teams.insert_many([
            {"league_id": league_id, "name": "Top", "rating": 1700, "owner_id": "u1"},
            {"league_id": league_id, "name": "Mid", "rating": 1500, "owner_id": "u2"},
            {"league_id": league_id, "name": "Low", "rating": 1300, "owner_id": "u3"},
        ])
        r = await ctx.client.get(f"/api/leagues/{league_id}/rating")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["teams_count"] == 3
        # The league-rating endpoint exposes the mean under `rating`, not
        # `avg_rating`. The full sorted standings live in `team_ratings`.
        assert body["rating"] == 1500.0
        assert body["team_ratings"][0]["team_name"] == "Top"
        assert body["team_ratings"][0]["rating"] == 1700.0

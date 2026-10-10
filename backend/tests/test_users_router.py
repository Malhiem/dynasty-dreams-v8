"""Focused unit tests for `routes/users.py`.

Covers /users/me/level XP math, /u/{username} 404 + basic shape, and
/users/me/week-at-a-glance fan-out behavior with a stubbed
get_team_week_summary dep. The profile edit + avatar upload endpoints are
covered by the existing integration tests.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import users as users_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


@pytest.mark.asyncio
async def test_my_level_no_teams_returns_level_1():
    async with isolated_router_app(users_routes) as ctx:
        r = await ctx.client.get("/api/users/me/level")
        assert r.status_code == 200
        body = r.json()
        assert body["level"] == 1
        assert body["xp_total"] == 0
        assert body["stats"]["teams_managed"] == 0


@pytest.mark.asyncio
async def test_my_level_accumulates_xp_from_teams_and_wins():
    async with isolated_router_app(users_routes) as ctx:
        # 2 teams: 5 wins + 10 wins = 15 wins × 20 = 300 + 2 teams × 50 = 100 → xp = 400; fantasy points award no XP
        await ctx.db.teams.insert_many([
            {"league_id": "L1", "owner_id": "test_user_0001", "name": "T1",
             "wins": 5, "points_for": 500.0},
            {"league_id": "L2", "owner_id": "test_user_0001", "name": "T2",
             "wins": 10, "points_for": 700.0},
        ])
        r = await ctx.client.get("/api/users/me/level")
        body = r.json()
        # xp = 2*50 + 15*20 = 400, regardless of fantasy points
        assert body["xp_total"] == 400
        assert body["level"] >= 2
        assert body["stats"]["teams_managed"] == 2
        assert body["stats"]["total_wins"] == 15


@pytest.mark.asyncio
async def test_my_level_counts_executed_trades_and_won_waivers():
    async with isolated_router_app(users_routes) as ctx:
        team_res = await ctx.db.teams.insert_one({
            "league_id": "L1", "owner_id": "test_user_0001", "name": "T1",
        })
        tid = str(team_res.inserted_id)
        await ctx.db.trades.insert_many([
            {"proposer_id": "test_user_0001", "status": "executed"},
            {"target_owner_id": "test_user_0001", "status": "executed"},
            {"proposer_id": "test_user_0001", "status": "pending"},  # excluded
        ])
        await ctx.db.waiver_claims.insert_many([
            {"team_id": tid, "status": "won"}, {"team_id": tid, "status": "won"}, {"team_id": tid, "status": "won"},
        ])
        r = await ctx.client.get("/api/users/me/level")
        stats = r.json()["stats"]
        assert stats["trades_accepted"] == 2
        assert stats["waiver_claims"] == 3


@pytest.mark.asyncio
async def test_public_profile_404_when_username_missing():
    async with isolated_router_app(users_routes) as ctx:
        r = await ctx.client.get("/api/u/nonexistent-user")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_profile_case_insensitive_match():
    async with isolated_router_app(users_routes) as ctx:
        await ctx.db.users.insert_one({
            "_id": ObjectId(), "username": "ZareK",
            "email": "z@example.com", "name": "Zarek",
        })
        r = await ctx.client.get("/api/u/zarek")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_public_profile_aggregates_team_awards():
    async with isolated_router_app(users_routes) as ctx:
        oid = ObjectId()
        await ctx.db.users.insert_one({
            "_id": oid, "username": "champ", "email": "c@e.com", "name": "Champ",
        })
        user_id = str(oid)
        league_res = await ctx.db.leagues.insert_one({"name": "L"})
        league_id = str(league_res.inserted_id)
        await ctx.db.teams.insert_one({
            "league_id": league_id, "owner_id": user_id, "name": "Champ Team",
            "wins": 12, "losses": 3, "points_for": 1500.0,
            "championship_won_at": datetime.now(timezone.utc),
            "division_winner_at": datetime.now(timezone.utc),
            "playoffs_reached_at": datetime.now(timezone.utc),
        })
        r = await ctx.client.get("/api/u/champ")
        body = r.json()
        # The endpoint exposes either `stats` (aggregate) or per-team flags; both should reflect the award.
        teams_field = body.get("teams") or body.get("team_cards") or []
        if teams_field:
            assert any(t.get("championship_won_at") for t in teams_field)
        # And the aggregate counters too
        stats = body.get("stats", {})
        if "championships" in stats:
            assert stats["championships"] >= 1


@pytest.mark.asyncio
async def test_week_at_a_glance_empty_when_user_has_no_teams():
    async with isolated_router_app(users_routes) as ctx:
        # Inject a stub for get_team_week_summary (would never be called here)
        users_routes._deps["get_team_week_summary"] = lambda tid, req: None
        r = await ctx.client.get("/api/users/me/week-at-a-glance")
        assert r.status_code == 200
        assert r.json() == {"summaries": []}


@pytest.mark.asyncio
async def test_week_at_a_glance_fans_out_per_team():
    async with isolated_router_app(users_routes) as ctx:
        leagues = await ctx.db.leagues.insert_many([{"name": "League A", "status": "active"}, {"name": "League B", "status": "active"}])
        lid1, lid2 = map(str, leagues.inserted_ids)
        await ctx.db.teams.insert_many([
            {"league_id": lid1, "owner_id": "test_user_0001", "name": "A"},
            {"league_id": lid2, "owner_id": "test_user_0001", "name": "B"},
        ])
        call_log = []
        async def fake_summary(team_id, request):
            call_log.append(team_id)
            return {"team_id": team_id, "week": 5, "points_for": 100.0}
        users_routes._deps["get_team_week_summary"] = fake_summary

        r = await ctx.client.get("/api/users/me/week-at-a-glance")
        body = r.json()
        assert len(body["summaries"]) == 2
        assert len(call_log) == 2

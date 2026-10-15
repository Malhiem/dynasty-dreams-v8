import asyncio
from copy import deepcopy

import pytest
from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import OperationFailure

from routes import scheduler
from services.combined_scheduler import Settings
from services.schedule_store import apply_preview, context
from tests.router_test_utils import isolated_router_app, seed_league


async def seed(ctx):
    lid = await seed_league(ctx.db)
    await ctx.db.leagues.update_one({"_id": ObjectId(lid)}, {"$set": {
        "max_teams": 8, "scoring_format": "h2h-points", "current_season_year": 2027,
        "season_start_date": "2026-10-07", "season_end_date": "2026-12-31", "regular_season_weeks": 4,
        "matchup_length_days": 7, "matchups_per_week": 2, "playoffs_enabled": False}})
    team_ids = [ObjectId() for _ in range(8)]
    await ctx.db.teams.insert_many([{"_id": tid, "league_id": lid, "name": f"Team {i}", "division": f"D{i // 2}", "conference": f"C{i // 4}"} for i, tid in enumerate(team_ids)])
    saved = await ctx.db.matchups.insert_one({"league_id": lid, "season": "2026-27", "week": 1,
        "home_team_id": str(team_ids[0]), "away_team_id": str(team_ids[1]), "status": "completed", "home_score": 24, "away_score": 10, "winner": str(team_ids[0])})
    return lid, saved.inserted_id


async def preview(ctx, lid):
    settings = Settings(weeks=4, games_per_week=2)
    c = await context(ctx.db, lid, ctx.user)
    return await scheduler.make_preview(ctx.db, lid, ctx.user, c, settings)


@pytest.mark.asyncio
async def test_preview_does_not_change_live_rows_and_apply_preserves_results_and_versions():
    async with isolated_router_app(scheduler) as ctx:
        lid, locked_id = await seed(ctx)
        original = await ctx.db.matchups.find_one({"_id": locked_id})
        plan = await preview(ctx, lid)
        assert plan["status"] == "feasible"
        assert await ctx.db.matchups.count_documents({"league_id": lid}) == 1
        result = await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
        assert result == {"status": "applied", "version": 1, "games": 32, "preserved_games": 1}
        saved = await ctx.db.matchups.find_one({"_id": locked_id})
        assert {k: saved[k] for k in original} == original
        assert await ctx.db.matchups.count_documents({"league_id": lid}) == 32
        assert await ctx.db.schedule_versions.count_documents({"league_id": lid}) == 1
        league = await ctx.db.leagues.find_one({"_id": ObjectId(lid)})
        assert league["schedule_version"] == 1
        assert league["combined_schedule_settings"]["games_per_week"] == 2
        with pytest.raises(HTTPException) as error:
            await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
        assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["settings", "team", "result", "season"])
async def test_stale_previews_are_rejected_without_mutation(change):
    async with isolated_router_app(scheduler) as ctx:
        lid, locked_id = await seed(ctx)
        plan = await preview(ctx, lid)
        if change == "settings": await ctx.db.leagues.update_one({"_id": ObjectId(lid)}, {"$set": {"max_teams": 9}})
        if change == "season": await ctx.db.leagues.update_one({"_id": ObjectId(lid)}, {"$set": {"current_season_year": 2028}})
        if change == "team": await ctx.db.teams.update_one({"league_id": lid}, {"$set": {"division": "Moved"}})
        if change == "result": await ctx.db.matchups.update_one({"_id": locked_id}, {"$set": {"home_score": 30}})
        before = await ctx.db.matchups.find({"league_id": lid}).to_list(None)
        with pytest.raises(HTTPException) as error:
            await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
        assert error.value.status_code == 409
        assert await ctx.db.matchups.find({"league_id": lid}).to_list(None) == before
        assert await ctx.db.schedule_versions.count_documents({"league_id": lid}) == 0


@pytest.mark.asyncio
async def test_write_failure_rolls_back_every_schedule_change(monkeypatch):
    async with isolated_router_app(scheduler) as ctx:
        lid, locked_id = await seed(ctx)
        plan = await preview(ctx, lid)
        before = await ctx.db.matchups.find({"league_id": lid}).to_list(None)
        original_insert = AsyncIOMotorCollection.insert_many
        async def fail_matchup_insert(collection, *args, **kwargs):
            if collection.name == "matchups": raise OperationFailure("injected failure")
            return await original_insert(collection, *args, **kwargs)
        monkeypatch.setattr(AsyncIOMotorCollection, "insert_many", fail_matchup_insert)
        with pytest.raises(HTTPException) as error:
            await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
        assert error.value.status_code == 503
        assert await ctx.db.matchups.find({"league_id": lid}).to_list(None) == before
        assert await ctx.db.schedule_versions.count_documents({"league_id": lid}) == 0
        assert (await ctx.db.scheduler_previews.find_one({"_id": ObjectId(plan["preview_id"])}))["state"] == "ready"
        assert "schedule_version" not in await ctx.db.leagues.find_one({"_id": ObjectId(lid)})


@pytest.mark.asyncio
async def test_simultaneous_apply_cannot_replace_schedule_twice():
    async with isolated_router_app(scheduler) as ctx:
        lid, _ = await seed(ctx)
        plan = await preview(ctx, lid)
        results = await asyncio.gather(*[apply_preview(ctx.db, lid, plan["preview_id"], ctx.user) for _ in range(2)], return_exceptions=True)
        assert sum(isinstance(r, dict) for r in results) == 1
        assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1
        assert await ctx.db.matchups.count_documents({"league_id": lid}) == 32
        assert await ctx.db.schedule_versions.count_documents({"league_id": lid}) == 1


@pytest.mark.asyncio
async def test_another_league_preview_and_expired_preview_cannot_be_applied():
    from datetime import datetime, timedelta, timezone
    async with isolated_router_app(scheduler) as ctx:
        first, _ = await seed(ctx); other, _ = await seed(ctx)
        plan = await preview(ctx, first)
        with pytest.raises(HTTPException) as error:
            await apply_preview(ctx.db, other, plan["preview_id"], ctx.user)
        assert error.value.status_code == 404
        await ctx.db.scheduler_previews.update_one({"_id": ObjectId(plan["preview_id"])}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        with pytest.raises(HTTPException) as error:
            await apply_preview(ctx.db, first, plan["preview_id"], ctx.user)
        assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_standalone_mongo_capability_fails_closed(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorDatabase
    async with isolated_router_app(scheduler) as ctx:
        lid, _ = await seed(ctx)
        plan = await preview(ctx, lid)
        before = await ctx.db.matchups.find({"league_id": lid}).to_list(None)
        original = AsyncIOMotorDatabase.command
        async def standalone(database, command, *args, **kwargs):
            if command == "hello": return {"ok": 1}
            return await original(database, command, *args, **kwargs)
        monkeypatch.setattr(AsyncIOMotorDatabase, "command", standalone)
        with pytest.raises(HTTPException) as error:
            await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
        assert error.value.status_code == 503 and "replica set" in error.value.detail
        assert await ctx.db.matchups.find({"league_id": lid}).to_list(None) == before


@pytest.mark.asyncio
async def test_active_playoff_bracket_and_historical_season_are_preserved():
    async with isolated_router_app(scheduler) as ctx:
        lid, _ = await seed(ctx)
        teams = await ctx.db.teams.find({"league_id": lid}).to_list(None)
        old = {"_id": ObjectId(), "league_id": lid, "season": "2025-26", "week": 1, "status": "completed",
               "home_team_id": str(teams[0]["_id"]), "away_team_id": str(teams[1]["_id"]), "home_score": 8, "away_score": 4}
        bracket = {**old, "_id": ObjectId(), "season": "2026-27", "week": 5, "is_playoff": True}
        pending = {**bracket, "_id": ObjectId(), "week": 6, "status": "scheduled", "home_score": 0, "away_score": 0}
        await ctx.db.matchups.insert_many([old, bracket, pending])
        plan = await preview(ctx, lid)
        await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
        assert await ctx.db.matchups.find_one({"_id": old["_id"]}) == old
        for row in [bracket, pending]:
            saved = await ctx.db.matchups.find_one({"_id": row["_id"]})
            assert {k: saved[k] for k in row} == row
        assert await ctx.db.matchups.count_documents({"league_id": lid, "is_playoff": True}) == 2


@pytest.mark.asyncio
async def test_new_version_keeps_prior_version_history_without_duplicate_live_games():
    async with isolated_router_app(scheduler) as ctx:
        lid, _ = await seed(ctx)
        for version in [1, 2]:
            plan = await preview(ctx, lid)
            result = await apply_preview(ctx.db, lid, plan["preview_id"], ctx.user)
            assert result["version"] == version
            assert await ctx.db.matchups.count_documents({"league_id": lid}) == 32
        assert await ctx.db.schedule_versions.count_documents({"league_id": lid}) == 2

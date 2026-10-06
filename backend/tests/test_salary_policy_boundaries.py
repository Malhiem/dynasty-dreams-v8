"""Retention season boundaries use the league calendar, never January 1."""
from datetime import datetime, timezone, timedelta
from services.salary_policy import active, applicable_season, season_end


def test_retention_exact_timestamp_boundary():
    league = {"current_season_year": 2026, "current_season_status": "in_progress",
              "season_end_date": "2027-04-18T03:00:00Z"}
    end = season_end(league)
    charge = {"season_year": 2026, "amount": 5000000}
    assert active(charge, league, end - timedelta(microseconds=1))
    assert not active(charge, league, end)
    assert not active(charge, league, end + timedelta(microseconds=1))
    assert applicable_season(league, end) == 2027
    assert active({"season_year": 2027}, league, end)


def test_date_only_end_includes_final_day():
    league = {"current_season_year": 2026, "season_end_date": "2027-04-18"}
    end = datetime(2027, 4, 19, tzinfo=timezone.utc)
    assert season_end(league) == end
    assert active({"season_year": 2026}, league, end - timedelta(microseconds=1))
    assert not active({"season_year": 2026}, league, end)


def test_renewed_league_old_calendar_does_not_expire_new_obligation():
    league = {"current_season_year": 2027, "current_season_status": "in_progress",
              "season_end_date": "2026-12-31"}
    assert active({"season_year": 2027}, league, datetime(2027, 5, 1, tzinfo=timezone.utc))
    assert not active({"season_year": 2026}, league)


def test_completion_releases_current_but_preserves_offseason_commitment():
    league = {"current_season_year": 2026, "current_season_status": "complete"}
    assert not active({"season_year": 2026}, league)
    assert active({"season_year": 2027}, league)
    assert not active({"season_year": 2027, "status": "cancelled"}, league)


async def test_failed_trade_write_restores_money_rosters_and_ownership():
    import pytest
    from bson import ObjectId
    from routes import roster
    from tests.router_test_utils import isolated_router_app
    from services.trade_recovery import recoverable_execution
    async with isolated_router_app(roster) as ctx:
        db = ctx.db
        lid, aid, bid, pid, trade_id = [ObjectId() for _ in range(5)]
        await db.leagues.insert_one({"_id": lid})
        before = [{"_id": aid, "league_id": str(lid), "roster": [str(pid)], "salary_used": 10000000, "dead_cap_schedule": []},
                  {"_id": bid, "league_id": str(lid), "roster": [], "salary_used": 0}]
        await db.teams.insert_many(before)
        contract = {"league_id": str(lid), "team_id": str(aid), "player_id": str(pid), "aav": 10000000, "status": "active"}
        await db.contracts.insert_one(contract)
        trade = {"_id": trade_id, "league_id": str(lid), "proposer_team_id": str(aid), "target_team_id": str(bid),
                 "assets_offered": [{"asset_type": "player", "player_id": str(pid), "salary_retained_pct": 50}], "assets_requested": []}
        await db.trades.insert_one(trade)
        expected_teams = await db.teams.find({"league_id": str(lid)}).sort("_id", 1).to_list(10)
        expected_contracts = await db.contracts.find({"league_id": str(lid)}).to_list(10)
        async def failing_execute(_):
            await db.teams.update_one({"_id": aid}, {"$set": {"roster": [], "salary_used": 5000000,
                                                     "dead_cap_schedule": [{"year": 2026, "amount": 5000000}]}})
            await db.teams.update_one({"_id": bid}, {"$set": {"roster": [str(pid)], "salary_used": 5000000}})
            await db.contracts.update_one({"player_id": str(pid)}, {"$set": {"team_id": str(bid)}})
            await db.salary_retentions.insert_one({"league_id": str(lid), "player_id": str(pid), "amount": 5000000})
            await db.player_ownership_periods.insert_one({"league_id": str(lid), "player_id": str(pid), "team_id": str(bid)})
            raise RuntimeError("injected retention persistence failure")
        with pytest.raises(RuntimeError, match="injected"):
            await recoverable_execution(db, trade, failing_execute)
        assert await db.teams.find({"league_id": str(lid)}).sort("_id", 1).to_list(10) == expected_teams
        assert await db.contracts.find({"league_id": str(lid)}).to_list(10) == expected_contracts
        assert await db.salary_retentions.count_documents({"league_id": str(lid)}) == 0
        assert await db.player_ownership_periods.count_documents({"league_id": str(lid)}) == 0
        assert (await db.trade_execution_journals.find_one({"_id": str(trade_id)}))["status"] == "rolled_back"
        async def success(_):
            return {"executed": True}
        assert await recoverable_execution(db, trade, success) == {"executed": True}
        assert (await db.trade_execution_journals.find_one({"_id": str(trade_id)}))["status"] == "completed"


async def test_automatic_completion_snapshots_then_releases_finances():
    from bson import ObjectId
    from routes import roster, seasons
    from services.salary_policy import payroll
    from tests.router_test_utils import isolated_router_app
    async with isolated_router_app([roster, seasons]) as ctx:
        db = ctx.db
        lid, aid, bid, pid, other = [ObjectId() for _ in range(5)]
        league = {"_id": lid, "current_season_year": 2026, "current_season_status": "in_progress",
                  "salary_cap_enabled": True, "salary_cap": 100000000, "scoring_format": "head_to_head"}
        await db.leagues.insert_one(league)
        await db.players.insert_many([{"_id": pid, "contract": {"aav": 10000000}}, {"_id": other, "contract": {"aav": 70000000}}])
        await db.teams.insert_many([{"_id": aid, "name": "A", "league_id": str(lid), "roster": [str(other)], "salary_used": 0},
                                   {"_id": bid, "name": "B", "league_id": str(lid), "roster": [str(pid)], "salary_used": 0}])
        await db.salary_retentions.insert_one({"league_id": str(lid), "player_id": str(pid), "retainer_team_id": str(aid), "amount": 5000000, "season_year": 2026})
        await db.matchups.insert_one({"league_id": str(lid), "is_playoff": True, "week": 20, "status": "completed"})
        await seasons._maybe_auto_snapshot_season(str(lid))
        snapshot = await db.league_seasons.find_one({"league_id": str(lid), "season_year": 2026})
        team = next(t for t in snapshot["teams"] if t["team_id"] == str(aid))
        assert team["salary_used"] == 75000000
        assert team["retention_history"][0]["amount"] == 5000000
        ended = await db.leagues.find_one({"_id": lid})
        state = await payroll(db, await db.teams.find_one({"_id": aid}), ended)
        assert state["used"] == 70000000
        assert state["retained"] == []


async def test_force_execution_bypasses_lock_without_losing_current_validation(monkeypatch):
    import logging
    from bson import ObjectId
    from routes import roster
    from services import trade_engine
    from utils import lineup_lock
    from tests.router_test_utils import isolated_router_app
    async with isolated_router_app([roster, trade_engine]) as ctx:
        db = ctx.db
        trade_engine._deps["logger"] = logging.getLogger("salary_test")
        lid, aid, bid, pid, trade_id = [ObjectId() for _ in range(5)]
        await db.leagues.insert_one({"_id": lid, "salary_cap_enabled": False})
        await db.players.insert_one({"_id": pid, "contract": {"aav": 10000000}})
        await db.teams.insert_many([{"_id": aid, "league_id": str(lid), "name": "A", "roster": [str(pid)]},
                                   {"_id": bid, "league_id": str(lid), "name": "B", "roster": []}])
        trade = {"_id": trade_id, "league_id": str(lid), "status": "accepted",
                 "proposer_team_id": str(aid), "target_team_id": str(bid),
                 "proposer_team_name": "A", "target_team_name": "B",
                 "assets_offered": [{"asset_type": "player", "player_id": str(pid)}], "assets_requested": []}
        await db.trades.insert_one(trade)
        monkeypatch.setattr(lineup_lock, "evaluate_lineup_lock", lambda league: {"locked": True})
        assert (await trade_engine._execute_trade(trade))["deferred"]
        assert (await db.teams.find_one({"_id": aid}))["roster"] == [str(pid)]
        assert (await trade_engine._execute_trade({**trade, "force_execute": True}))["executed"]
        assert (await db.teams.find_one({"_id": aid}))["roster"] == []
        assert (await db.teams.find_one({"_id": bid}))["roster"] == [str(pid)]


def test_forgiven_discount_uses_recorded_policy_and_season():
    from services.salary_policy import discount_active
    league = {"current_season_year": 2026, "retention_forgiveness_policy": "receiver_pays"}
    waived = {"season_year": 2026, "status": "cancelled", "forgiveness_policy": "league_waives"}
    assert discount_active(waived, league)
    assert not active(waived, league)
    assert not discount_active({**waived, "forgiveness_policy": "receiver_pays"}, league)
    assert not discount_active(waived, {**league, "current_season_year": 2027})


async def test_buyout_charges_only_applicable_season_and_enforces_trade_cap():
    import pytest
    from fastapi import HTTPException
    from bson import ObjectId
    from routes import roster
    from services.salary_policy import payroll, validate_trade
    from tests.router_test_utils import isolated_router_app
    async with isolated_router_app(roster) as ctx:
        db = ctx.db
        lid, aid, bid, pid = [ObjectId() for _ in range(4)]
        league = {"_id": lid, "current_season_year": 2026, "salary_cap_enabled": True, "salary_cap": 11000000}
        await db.leagues.insert_one(league)
        await db.players.insert_one({"_id": pid, "contract": {"aav": 10000000}})
        a = {"_id": aid, "league_id": str(lid), "name": "A", "roster": [str(pid)]}
        b = {"_id": bid, "league_id": str(lid), "name": "B", "roster": [], "dead_cap_schedule": [
            {"source": "buyout", "year": 2026, "amount": 2000000},
            {"source": "buyout", "year": 2027, "amount": 8000000}]}
        await db.teams.insert_many([a, b])
        assert (await payroll(db, b, league))["used"] == 2000000
        trade = {"league_id": str(lid), "proposer_team_id": str(aid), "target_team_id": str(bid),
                 "assets_offered": [{"asset_type": "player", "player_id": str(pid)}]}
        with pytest.raises(HTTPException, match="Trade exceeds salary cap"):
            await validate_trade(db, trade)
        assert (await payroll(db, b, {**league, "current_season_year": 2027}))["used"] == 8000000

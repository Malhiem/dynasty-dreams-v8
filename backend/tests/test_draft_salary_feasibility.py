"""Runtime salary rules against explicitly disposable Mongo only."""
import os
from uuid import uuid4
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from services.draft_salary import feasible_completion, load_context, evaluate, entry, team_summary, validate_lineup
from fastapi import HTTPException

@pytest.mark.parametrize("prices,slots,lower,upper,expected", [
    ([4,6,8,10,19],2,14,18,True),
    ([4,6,8,10,19],1,12,16,False),
    ([2,6,8,10,19],1,10,14,True),
    ([7,10],1,8,9,False),
    ([1,2],1,0,0,False),
    ([1,2],0,0,0,True),
    ([1],2,0,10,False),
])
def test_exact_completion(prices, slots, lower, upper, expected):
    options=[(str(i), {"ACT": p}) for i,p in enumerate(prices)]
    assert feasible_completion(("ACT",)*slots, options, lower, upper) is expected

def test_distinct_position_assignment():
    assert feasible_completion(("RW","LW"), [("a",{"RW":4,"LW":4})],0,20) is False
    assert feasible_completion(("RW","LW"), [("a",{"RW":4}), ("b",{"LW":6})],10,10) is True

@pytest.mark.asyncio
async def test_two_slots_strict_and_informal_and_canonical_summary():
    url=os.environ["MONGO_URL"]; name=os.environ["DB_NAME"]
    assert "draft" in name and "disposable" in name, "Dedicated draft disposable database required"
    client=AsyncIOMotorClient(url); db=client[name]
    league_id, team_id, draft_id=ObjectId(),ObjectId(),ObjectId()
    roster_id=ObjectId()
    league={"_id":league_id,"salary_cap_enabled":True,"salary_cap":64_000_000,
        "cap_floor_enabled":True,"cap_floor":60_000_000,"salary_adherence_mode":"strict",
        "draft_roster_target":3,"roster_spots":3,"default_rookie_aav":950000}
    team={"_id":team_id,"league_id":str(league_id),"owner_id":"owner","name":"Salary fixture",
        "roster":[str(roster_id)],"lineup":{str(roster_id):entry("ACT")}}
    draft={"_id":draft_id,"league_id":str(league_id),"player_criteria":"all","picks":[]}
    candidates=[{"_id":ObjectId(),"name":f"Salary {price}","position":"RW","salary":price*1_000_000} for price in [2,4,6,8,10,19]]
    try:
        await db.leagues.insert_one(league); await db.teams.insert_one(team); await db.drafts.insert_one(draft)
        await db.players.insert_many([{"_id":roster_id,"name":"Existing payroll","position":"RW","salary":46_000_000}]+candidates)
        ctx=await load_context(db,draft,team,league)
        assert [evaluate(ctx,str(p["_id"]))["allowed"] for p in candidates]==[False,True,True,True,True,False]
        summary=await team_summary(db,draft,team,league)
        assert summary["salary_used"]==46_000_000
        assert summary["remaining"]==18_000_000
        assert summary["remaining_slots"]==2
        completed={**ctx,"team":{**ctx["team"],"lineup":{str(roster_id):entry("ACT"),str(candidates[1]["_id"]):entry("ACT"),str(candidates[4]["_id"]):entry("ACT")}}}
        assert evaluate(completed,str(candidates[5]["_id"]))["allowed"] is False
        ctx["league"]={**league,"salary_adherence_mode":"informal"}
        assert all(evaluate(ctx,str(p["_id"]))["allowed"] for p in candidates)
    finally:
        await db.players.delete_many({"_id":{"$in":[roster_id]+[p["_id"] for p in candidates]}})
        await db.teams.delete_one({"_id":team_id}); await db.leagues.delete_one({"_id":league_id}); await db.drafts.delete_one({"_id":draft_id}); client.close()

@pytest.mark.asyncio
async def test_ir_charge_and_position_counts():
    assert "draft" in os.environ["DB_NAME"] and "disposable" in os.environ["DB_NAME"]
    client=AsyncIOMotorClient(os.environ["MONGO_URL"]); db=client[os.environ["DB_NAME"]]
    lid,tid,pid=ObjectId(),ObjectId(),ObjectId()
    league={"_id":lid,"roster_spots":4,"position_breakdown":{"active":{"RW":4}},"minors_spots":30,
        "ir_slots":1,"ir_salary_charge_pct":0,"salary_cap_enabled":True,"salary_cap":60_000_000}
    p={"_id":pid,"name":"IR player","position":"RW","salary":4_000_000,"status":"IR"}
    team={"_id":tid,"league_id":str(lid),"roster":[str(pid)],"lineup":{str(pid):entry("IR")}}
    try:
        await db.players.insert_one(p)
        summary=await team_summary(db,{"picks":[]},team,league)
        assert summary["salary_used"]==0
        assert summary["positions"]["IR"]["filled"]==1
        assert summary["positions"]["RW"]["filled"]==0
        assert summary["positions"]["MIN"]["capacity"]==30
        summary=await team_summary(db,{"picks":[]},team,{**league,"ir_salary_charge_pct":50})
        assert summary["salary_used"]==2_000_000
        with pytest.raises(HTTPException):
            validate_lineup(team,{str(pid):{**p,"status":"healthy"}},league)
    finally:
        await db.players.delete_one({"_id":pid}); client.close()


@pytest.mark.asyncio
async def test_pending_pick_recovery_restores_roster_without_advancing_draft():
    from services.draft_mutation import recover
    assert "draft" in os.environ["DB_NAME"] and "disposable" in os.environ["DB_NAME"]
    client = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = client[os.environ["DB_NAME"]]
    did, tid = ObjectId(), ObjectId()
    before = {"roster": [], "lineup": {}, "draft_queue": ["queued"]}
    try:
        await db.drafts.insert_one({"_id": did, "current_pick": 1, "picks": []})
        await db.teams.insert_one({"_id": tid, "roster": ["partial"], "lineup": {"partial": entry("ACT")}})
        await db.draft_mutations.insert_one({"draft_id": str(did), "draft_oid": did, "team_oid": tid,
            "overall": 1, "player_id": "partial", "before_team": before, "status": "pending"})
        await recover(db, str(did))
        team = await db.teams.find_one({"_id": tid})
        assert {key: team[key] for key in before} == before
        assert (await db.drafts.find_one({"_id": did}))["current_pick"] == 1
        assert (await db.draft_mutations.find_one({"draft_id": str(did)}))["status"] == "rolled_back"
    finally:
        await db.drafts.delete_one({"_id": did}); await db.teams.delete_one({"_id": tid})
        await db.draft_mutations.delete_many({"draft_id": str(did)}); client.close()


@pytest.mark.asyncio
async def test_draft_trade_feasibility_strict_rejects_and_informal_executes():
    from routes import roster
    from services import trade_engine
    from services.salary_policy import validate_trade
    from tests.router_test_utils import isolated_router_app
    import logging
    async with isolated_router_app([roster, trade_engine]) as ctx:
        db = ctx.db
        trade_engine._deps["logger"] = logging.getLogger("draft_trade_test")
        lid, aid, bid, pid, existing, candidate, did, trid = [ObjectId() for _ in range(8)]
        league = {"_id": lid, "salary_cap_enabled": True, "salary_cap": 64_000_000,
            "cap_floor_enabled": True, "cap_floor": 60_000_000, "salary_adherence_mode": "strict",
            "draft_roster_target": 2, "roster_spots": 2}
        await db.leagues.insert_one(league)
        await db.players.insert_many([{"_id":pid,"salary":19_000_000,"position":"RW"},
            {"_id":existing,"salary":46_000_000,"position":"RW"},
            {"_id":candidate,"salary":14_000_000,"position":"RW"}])
        await db.teams.insert_many([{"_id":aid,"name":"Sender","league_id":str(lid),"roster":[str(pid)]},
            {"_id":bid,"name":"Receiver","league_id":str(lid),"roster":[str(existing)]}])
        await db.drafts.insert_one({"_id":did,"league_id":str(lid),"status":"active","player_criteria":"all","picks":[],"salary_blocked":True})
        trade={"_id":trid,"league_id":str(lid),"status":"accepted","proposer_team_id":str(aid),
            "target_team_id":str(bid),"proposer_team_name":"Sender","target_team_name":"Receiver",
            "assets_offered":[{"asset_type":"player","player_id":str(pid)}],"assets_requested":[]}
        await db.trades.insert_one(trade)
        with pytest.raises(HTTPException):
            await validate_trade(db,trade)
        assert (await db.teams.find_one({"_id":bid}))["roster"]==[str(existing)]
        await db.leagues.update_one({"_id":lid},{"$set":{"salary_adherence_mode":"informal"}})
        assert (await trade_engine._execute_trade(trade))["executed"]
        assert (await db.teams.find_one({"_id":bid}))["roster"]==[str(existing),str(pid)]
        assert (await db.drafts.find_one({"_id":did}))["salary_blocked"] is False


def test_minors_and_ir_do_not_replace_required_active_positions():
    from services.draft_salary import vacancies
    league={"position_breakdown":{"active":{"RW":2}},"minors_spots":3,"bench_spots":0,"ir_slots":1,"draft_roster_target":2}
    team={"lineup":{"minor":entry("MIN"),"injured":entry("IR")}}
    assert vacancies(team,league)==("RW","RW")
    assert vacancies(team,{**league,"draft_roster_target":5})==("RW","RW","MIN","MIN")

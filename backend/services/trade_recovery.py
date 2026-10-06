"""Recoverable financial writes for trades on standalone Mongo.

The league lease prevents competing financial writes while the durable journal
captures pre-execution state. A failed write restores it; a crashed execution is
restored before retry. Completed journals are retained for internal diagnosis.
"""
from datetime import datetime, timezone
from bson import ObjectId
from services.salary_policy import trade_transfers


async def restore(db, journal):
    for saved in journal.get("teams", []):
        fields = ("roster", "salary_used", "dead_cap_schedule")
        update = {"$set": {k: saved[k] for k in fields if k in saved}}
        missing = {k: "" for k in fields if k not in saved}
        if missing:
            update["$unset"] = missing
        await db.teams.update_one({"_id": saved["_id"]}, update)
    for name, query in journal.get("queries", {}).items():
        collection = db[name]
        saved = journal["records"][name]
        ids = [doc["_id"] for doc in saved]
        await collection.delete_many({**query, "_id": {"$nin": ids}})
        for doc in saved:
            await collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)


async def recoverable_execution(db, trade, execute):
    tid = str(trade["_id"])
    previous = await db.trade_execution_journals.find_one({"_id": tid})
    if previous and previous.get("status") == "prepared":
        # An executed status is the commit marker, even if journal finalization failed.
        current = await db.trades.find_one({"_id": trade["_id"]})
        if current and current.get("status") == "executed":
            return {"already_executed": True}
        await restore(db, previous)
    transfers = trade_transfers(trade)
    pids = [asset["player_id"] for sender, receiver, asset in transfers]
    tids = list({t for s, d, a in transfers for t in (s, d) if t})
    if not tids:
        tids = [p["team_id"] for p in trade.get("parties") or []] or [trade["proposer_team_id"], trade["target_team_id"]]
    lid = trade["league_id"]
    queries = {
        "contracts": {"league_id": lid, "player_id": {"$in": pids}},
        "salary_retentions": {"league_id": lid, "player_id": {"$in": pids}},
        "player_ownership_periods": {"league_id": lid, "player_id": {"$in": pids}},
        "lineup_status_periods": {"league_id": lid, "player_id": {"$in": pids}},
        "roster_change_log": {"league_id": lid, "metadata.trade_id": tid},
        "draft_picks": {"league_id": lid, "current_team_id": {"$in": tids}},
    }
    journal = {"_id": tid, "status": "prepared", "league_id": lid,
               "created_at": datetime.now(timezone.utc), "queries": queries,
               "teams": await db.teams.find({"_id": {"$in": [ObjectId(t) for t in tids]}},
                         {"roster": 1, "salary_used": 1, "dead_cap_schedule": 1}).to_list(100),
               "records": {}}
    for name, query in queries.items():
        journal["records"][name] = await db[name].find(query).to_list(10000)
    await db.trade_execution_journals.replace_one({"_id": tid}, journal, upsert=True)
    try:
        result = await execute(trade)
    except Exception:
        current = await db.trades.find_one({"_id": trade["_id"]})
        if current and current.get("status") == "executed":
            await db.trade_execution_journals.update_one({"_id": tid}, {"$set": {"status": "completed"}})
            raise
        await restore(db, journal)
        await db.trade_execution_journals.update_one({"_id": tid}, {"$set": {"status": "rolled_back"}})
        raise
    await db.trade_execution_journals.update_one({"_id": tid}, {"$set": {"status": "completed"}})
    return result

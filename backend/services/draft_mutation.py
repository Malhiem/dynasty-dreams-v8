"""Recoverable pick + roster writes for standalone Mongo under league lease."""
from datetime import datetime, timezone
from fastapi import HTTPException


async def recover(db, draft_id):
    async for journal in db.draft_mutations.find({"draft_id": draft_id, "status": "pending"}):
        draft = await db.drafts.find_one({"_id": journal["draft_oid"]})
        committed = any(p.get("overall") == journal["overall"] and p.get("player_id") == journal["player_id"] for p in (draft or {}).get("picks", []))
        if not committed:
            await db.teams.update_one({"_id": journal["team_oid"]}, {"$set": journal["before_team"]})
        await db.draft_mutations.update_one({"_id": journal["_id"]}, {"$set": {"status": "committed" if committed else "rolled_back"}})


async def commit_pick(db, draft, team, pick, lineup, new_status, auto=False):
    """No turn advancement if the roster write fails; journal repairs crashes."""
    before = {"roster": team.get("roster") or [], "lineup": team.get("lineup") or {}, "draft_queue": team.get("draft_queue") or []}
    journal = await db.draft_mutations.insert_one({"draft_id": str(draft["_id"]), "draft_oid": draft["_id"],
        "team_oid": team["_id"], "overall": pick["overall"], "player_id": pick["player_id"], "before_team": before, "status": "pending"})
    roster = list(dict.fromkeys([*before["roster"], pick["player_id"]]))
    queue = [pid for pid in before["draft_queue"] if not auto or pid != pick["player_id"]]
    try:
        await db.teams.update_one({"_id": team["_id"]}, {"$set": {"roster": roster, "lineup": lineup, "draft_queue": queue}})
        result = await db.drafts.update_one({"_id": draft["_id"], "current_pick": pick["overall"], "status": "active"}, {
            "$push": {"picks": pick}, "$set": {"current_pick": pick["overall"] + 1, "status": new_status,
            "salary_blocked": False, "current_pick_started_at": datetime.now(timezone.utc).isoformat()}})
        if not result.matched_count:
            raise HTTPException(409, "Draft turn changed before selection committed")
    except Exception:
        await recover(db, str(draft["_id"]))
        raise
    await db.draft_mutations.update_one({"_id": journal.inserted_id}, {"$set": {"status": "committed"}})
    return result

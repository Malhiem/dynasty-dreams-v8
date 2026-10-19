"""Self-service exit: no successor, season, roster, or payment-policy gate."""
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError


async def leave_league(db, league_id, user_id):
    if not ObjectId.is_valid(league_id):
        raise HTTPException(400, "Invalid league ID")
    uid = str(user_id)
    identities = [uid] + ([ObjectId(uid)] if ObjectId.is_valid(uid) else [])
    lid = ObjectId(league_id)
    league_ids = [league_id, lid]
    exit_id = f"{league_id}:{uid}"

    async def commit(session):
        league = await db.leagues.find_one({"_id": lid}, session=session)
        if not league:
            raise HTTPException(404, "League not found")
        teams = await db.teams.find({"league_id": {"$in": league_ids}, "$or": [
            {"owner_id": {"$in": identities}}, {"co_owner_ids": {"$in": identities}},
        ]}, session=session).to_list(None)
        roles = any(str(league.get(key) or "") == uid for key in ("commissioner_id", "owner_id"))
        roles = roles or any(str(value) == uid for key in ("admin_ids", "co_commissioners") for value in league.get(key) or [])
        if not teams and not roles:
            previous = await db.league_exits.find_one({"_id": exit_id}, session=session)
            if previous:
                return {key: value for key, value in previous.items() if key != "_id"}
            raise HTTPException(403, "Not a member of this league")
        owned = [team["_id"] for team in teams if str(team.get("owner_id") or "") == uid]
        if owned:
            await db.teams.update_many({"_id": {"$in": owned}}, {"$set": {
                "owner_id": None, "owner_name": None, "ownership_vacant": True,
                "is_commissioner_team": False,
            }}, session=session)
        await db.teams.update_many({"league_id": {"$in": league_ids}, "co_owner_ids": {"$in": identities}},
            {"$pull": {"co_owner_ids": {"$in": identities}}}, session=session)
        changes = {}
        if str(league.get("commissioner_id") or "") == uid:
            changes.update(commissioner_id="", commissioner_name="Vacant", commissioner_vacant=True)
        if str(league.get("owner_id") or "") == uid:
            changes["owner_id"] = None
        for key in ("admin_ids", "co_commissioners"):
            changes[key] = [value for value in league.get(key) or [] if str(value) != uid]
        update = {"$set": changes}
        await db.leagues.update_one({"_id": lid}, update, session=session)
        result = {
            "status": "left", "league_id": league_id, "user_id": uid,
            "vacated_team_ids": [str(value) for value in owned],
            "commissioner_vacant": bool(changes.get("commissioner_vacant") or not league.get("commissioner_id")),
            "left_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.league_exits.replace_one({"_id": exit_id}, {"_id": exit_id, **result}, upsert=True, session=session)
        await db.league_membership_events.insert_one({"type": "left", **result}, session=session)
        return result

    hello = await db.command("hello")
    if not hello.get("setName") and hello.get("msg") != "isdbgrid":
        raise HTTPException(503, "Leaving could not be confirmed: MongoDB transaction support is unavailable")
    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(commit)
    except PyMongoError as exc:
        raise HTTPException(503, "Leaving could not be confirmed. Retry safely to reconcile the exit.") from exc


async def evict_league_rooms(db, sio, league_id, user_id):
    """Revoke this league's subscriptions without interrupting other leagues."""
    if sio is None:
        return
    drafts = await db.drafts.find({"league_id": league_id}, {"_id": 1}).to_list(None)
    forbidden = {f"league_{league_id}", *(f"draft_{draft['_id']}" for draft in drafts)}
    for sid, _ in list(sio.manager.get_participants("/", None)):
        try:
            session = await sio.get_session(sid)
            if str(session.get("user_id")) != str(user_id):
                continue
            for room in list(sio.rooms(sid)):
                if room in forbidden:
                    await sio.leave_room(sid, room)
            await sio.emit("team_membership_changed", {"action": "left", "league_id": league_id, "user_id": str(user_id)}, to=sid)
        except KeyError:
            continue

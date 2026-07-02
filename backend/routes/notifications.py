"""Notifications router — list, count, mark-as-read endpoints.

Extracted from server.py during iter 85 modularization. Kept thin because
every endpoint is a straight Mongo query on `db.notifications` scoped to the
authenticated user; the heavy work (creating notifications + emitting push)
lives in `server.py::create_notification` and `routes/push.py`.
"""
from bson import ObjectId
from fastapi import APIRouter, Request

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/notifications")
async def get_notifications(request: Request, unread_only: bool = False, limit: int = 50):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    query: dict = {"user_id": user["_id"]}
    if unread_only:
        query["read"] = False
    notifs = await db.notifications.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    for n in notifs:
        n["_id"] = str(n["_id"])
    return notifs


@router.get("/notifications/count")
async def get_unread_count(request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    count = await db.notifications.count_documents({"user_id": user["_id"], "read": False})
    return {"count": count}


@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    await db.notifications.update_one(
        {"_id": ObjectId(notif_id), "user_id": user["_id"]},
        {"$set": {"read": True}},
    )
    return {"message": "Marked as read"}


@router.post("/notifications/read-all")
async def mark_all_read(request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    result = await db.notifications.update_many(
        {"user_id": user["_id"], "read": False},
        {"$set": {"read": True}},
    )
    return {"message": f"Marked {result.modified_count} notifications as read"}


@router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, request: Request):
    """Iter 230at — Delete a single notification. Used by the mobile
    swipe-left-to-dismiss gesture in NotificationsPanel. Owner-scoped
    so users can only delete their own."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    result = await db.notifications.delete_one(
        {"_id": ObjectId(notif_id), "user_id": user["_id"]},
    )
    if result.deleted_count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Deleted"}



@router.get("/player-status/feed")
async def get_player_status_feed(
    request: Request,
    scope: str = "user",  # "user" | "league" | "team"
    league_id: str = None,
    team_id: str = None,
    days: int = 7,
    limit: int = 200,
):
    """Iter 232N.5 — Grouped-by-player feed of `player_status_change`
    notifications. Powers three surfaces:
      • Notifications inbox "Player Status" tab (scope="user")
      • League Home recent activity card (scope="league" or "team")
      • User Dashboard cross-league feed (scope="user")

    Returns `[{player_id, player_name, updates: [{flag, value, title,
    message, ts, league_id}, ...]}]` sorted so the player with the
    most-recent update comes first.
    """
    from datetime import datetime, timezone, timedelta
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
    query: dict = {
        "user_id": user["_id"],
        "type": "player_status_change",
        "created_at": {"$gte": cutoff},
    }
    if scope == "league" and league_id:
        query["league_id"] = league_id
    elif scope == "team" and team_id:
        # Filter by player_ids on the specified team's current roster.
        team = await db.teams.find_one({"_id": ObjectId(team_id)}, {"roster": 1, "league_id": 1})
        if team:
            roster_pids = [str(p) for p in (team.get("roster") or [])]
            if roster_pids:
                query["reason.player_id"] = {"$in": roster_pids}
            else:
                # Empty roster → no updates.
                return {"players": [], "total_updates": 0}
            # Also scope league_id when a team is given so cross-league
            # noise doesn't creep in for identical player_ids.
            if team.get("league_id"):
                query["league_id"] = team["league_id"]
        else:
            return {"players": [], "total_updates": 0}

    notifs = (
        await db.notifications.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    )

    grouped: dict = {}
    for n in notifs:
        reason = n.get("reason") or {}
        pid = reason.get("player_id")
        if not pid:
            # Legacy notifications (pre-232N.5) without reason.player_id
            # are dropped — the feed intentionally shows only rows that
            # can be grouped.
            continue
        bucket = grouped.setdefault(pid, {
            "player_id": pid,
            "player_name": reason.get("player_name") or "Player",
            "updates": [],
        })
        bucket["updates"].append({
            "notification_id": str(n["_id"]),
            "flag": reason.get("flag"),
            "value": bool(reason.get("value")),
            "title": n.get("title"),
            "message": n.get("message"),
            "ts": n.get("created_at"),
            "league_id": n.get("league_id"),
            "read": bool(n.get("read")),
        })

    players = list(grouped.values())
    # Sort by most-recent update per player (updates are already
    # sorted desc because notifs came back desc).
    players.sort(key=lambda p: p["updates"][0]["ts"] if p["updates"] else "", reverse=True)
    # Iter 232N.7 — Enrich each bucket with the cross-league trend
    # badge so the feed cards can render the same "hot / dropped /
    # traded" chip that appears on inline player rows.
    if players:
        from routes.player_trends import fetch_trends_map
        trends_map = await fetch_trends_map(db, [p["player_id"] for p in players])
        for bucket in players:
            bucket["trends"] = trends_map.get(bucket["player_id"])
    return {
        "players": players,
        "total_updates": sum(len(p["updates"]) for p in players),
    }

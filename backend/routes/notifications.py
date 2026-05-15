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

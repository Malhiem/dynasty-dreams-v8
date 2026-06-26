"""Iter 230 — Notification preferences router.

Per-user, per-event-type channel toggles. Channels: in_app, push, email.
Currently only `in_app` is wired end-to-end (toast + bell badge); push/email
are saved as preferences for future Expo/SendGrid wiring.

Endpoints:
  GET  /api/notifications/preferences           → current settings + catalog
  PUT  /api/notifications/preferences           → update a single event's channels
  POST /api/notifications/preferences/reset     → reset to factory defaults

The catalog (EVENTS + CATEGORIES) is included in the GET response so the
settings UI can render groups + labels without a separate fetch.
"""
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .notification_events import EVENTS, CATEGORIES, EVENT_IDS, default_preferences


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class PreferenceUpdateInput(BaseModel):
    event_id: str
    in_app: Optional[bool] = None
    push: Optional[bool] = None
    email: Optional[bool] = None


async def _load_or_init(user_id: str) -> Dict[str, Dict[str, bool]]:
    db = _deps["db"]
    doc = await db.notification_preferences.find_one({"user_id": user_id})
    if doc and isinstance(doc.get("preferences"), dict):
        # Merge in any newly-added events with their defaults so future
        # additions auto-populate for existing users.
        defaults = default_preferences()
        merged = {**defaults, **doc["preferences"]}
        # If a new event was added since the user's last save, persist the
        # merged shape so subsequent reads are fast.
        if set(merged.keys()) != set(doc["preferences"].keys()):
            await db.notification_preferences.update_one(
                {"user_id": user_id},
                {"$set": {"preferences": merged}},
            )
        return merged
    # First-time user: seed defaults.
    prefs = default_preferences()
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "preferences": prefs}},
        upsert=True,
    )
    return prefs


@router.get("/notifications/preferences")
async def get_preferences(request: Request):
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    prefs = await _load_or_init(user["_id"])
    return {
        "preferences": prefs,
        "events": EVENTS,
        "categories": CATEGORIES,
    }


@router.put("/notifications/preferences")
async def update_preference(input: PreferenceUpdateInput, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    if input.event_id not in EVENT_IDS:
        raise HTTPException(status_code=422, detail=f"Unknown event_id: {input.event_id}")
    prefs = await _load_or_init(user["_id"])
    current = prefs.get(input.event_id, {"in_app": False, "push": False, "email": False})
    if input.in_app is not None:
        current["in_app"] = bool(input.in_app)
    if input.push is not None:
        current["push"] = bool(input.push)
    if input.email is not None:
        current["email"] = bool(input.email)
    prefs[input.event_id] = current
    await db.notification_preferences.update_one(
        {"user_id": user["_id"]},
        {"$set": {f"preferences.{input.event_id}": current}},
    )
    return {"event_id": input.event_id, "preferences": current}


@router.post("/notifications/preferences/reset")
async def reset_preferences(request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    prefs = default_preferences()
    await db.notification_preferences.update_one(
        {"user_id": user["_id"]},
        {"$set": {"user_id": user["_id"], "preferences": prefs}},
        upsert=True,
    )
    return {"preferences": prefs}


async def channel_enabled(user_id: str, event_id: str, channel: str) -> bool:
    """Helper used by the emitter side. Returns True if `channel` is enabled
    for this user+event. Unknown events default to True (don't accidentally
    swallow notifications added before the catalog catches up). Channels
    not in the saved doc fall back to the event's default_channels list.
    """
    if event_id not in EVENT_IDS:
        return True
    db = _deps.get("db")
    if db is None:
        return True
    doc = await db.notification_preferences.find_one({"user_id": user_id})
    prefs = (doc or {}).get("preferences") or {}
    cfg = prefs.get(event_id)
    if cfg is None:
        # Fall back to catalog defaults.
        for e in EVENTS:
            if e["id"] == event_id:
                return channel in e["default_channels"]
        return True
    return bool(cfg.get(channel, False))

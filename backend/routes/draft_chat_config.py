"""Draft chat + config router — extracted from `routes/drafts.py` (iter 231w).

The final-final stretch: pulls the three small endpoints owning the
in-draft chat panel and the live config knob into their own module so
`routes/drafts.py` becomes a pure helpers + notifications module.

  • POST /api/drafts/{draft_id}/chat    — send_draft_chat
  • GET  /api/drafts/{draft_id}/chat    — get_draft_chat
  • PUT  /api/drafts/{draft_id}/config  — update_draft_config

Note: `routes/draft_config.py` (iter 231) owns the LEAGUE-LEVEL draft
config endpoints (keeper rules, expansion, NHL lottery). This new
module owns the DRAFT-INSTANCE config endpoint (time_per_pick,
total_rounds, snake, criteria, missed_pick_action). Different scope,
different lifecycle — keeping them separate avoids confusion.

Wired via the `setup(deps)` injection pattern in `server.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from draft_engine import DraftChatRequest, UpdateDraftConfigRequest


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


async def _broadcast(room: str, event: str, payload: dict):
    fn = _deps.get("broadcast_to_room")
    if fn is None:
        return None
    return await fn(room, event, payload)


@router.post("/drafts/{draft_id}/chat")
async def send_draft_chat(draft_id: str, input: DraftChatRequest, request: Request):
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    team = await _db().teams.find_one(
        {"league_id": draft["league_id"], "owner_id": user["_id"]},
    )
    sender = team["name"] if team else user["name"]

    msg = {
        "id": f"chat-{datetime.now(timezone.utc).timestamp()}",
        "type": "chat",
        "sender": sender,
        "text": input.text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$push": {"chat_messages": msg}},
    )
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    return msg


@router.get("/drafts/{draft_id}/chat")
async def get_draft_chat(draft_id: str):
    draft = await _db().drafts.find_one(
        {"_id": ObjectId(draft_id)},
        {"chat_messages": 1},
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft.get("chat_messages", [])


@router.put("/drafts/{draft_id}/config")
async def update_draft_config(draft_id: str, input: UpdateDraftConfigRequest, request: Request):
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can update draft config")

    updates = {}
    if input.time_per_pick is not None:
        updates["time_per_pick"] = input.time_per_pick
    if input.total_rounds is not None:
        updates["total_rounds"] = input.total_rounds
    if input.snake_draft is not None:
        updates["snake_draft"] = input.snake_draft
    if input.player_criteria is not None:
        updates["player_criteria"] = input.player_criteria
    if input.missed_pick_action is not None:
        updates["missed_pick_action"] = input.missed_pick_action
    # Iter 232N.26 — Persist the personal pick-timer cap. Because the
    # Pydantic model uses `Optional[int]` (no exclude_unset here), a
    # caller who wants to DISABLE the feature can pass 0 → we store
    # None so the worker treats it as "off". Any positive value is
    # copied through verbatim (draft_engine.py already enforces the
    # 30-86400 range).
    if "personal_pick_timer_seconds" in input.model_fields_set:
        raw = input.personal_pick_timer_seconds
        updates["personal_pick_timer_seconds"] = None if not raw else int(raw)

    if updates:
        await _db().drafts.update_one(
            {"_id": ObjectId(draft_id)},
            {"$set": updates},
        )
        await _broadcast(f"draft_{draft_id}", "draft_config_updated", updates)

    return {"updated": list(updates.keys())}

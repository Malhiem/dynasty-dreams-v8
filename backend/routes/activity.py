"""Activity Feed router.

Extracted from server.py during iter 89 modularization. Bundles the two
read endpoints:
  - GET /activity/{league_id}      (raw activity feed, paginated)
  - GET /leagues/{league_id}/transactions  (normalized transaction view)

The write side (`log_activity`) is intentionally kept in server.py — it's
called from dozens of places across trade/waiver/roster flows; moving it
would force a sprawling import refactor for no architectural gain.
"""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/activity/{league_id}")
async def get_activity_feed(
    league_id: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
):
    db = _deps["db"]
    query: dict = {"league_id": league_id}
    if event_type:
        # Support comma-separated event types.
        types = [t.strip() for t in event_type.split(",") if t.strip()]
        if len(types) == 1:
            query["event_type"] = types[0]
        elif types:
            query["event_type"] = {"$in": types}
    skip = (page - 1) * limit
    items = (
        await db.activity_feed.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    total = await db.activity_feed.count_documents(query)
    for item in items:
        item["_id"] = str(item["_id"])
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/leagues/{league_id}/transactions")
async def get_league_transactions(
    league_id: str,
    limit: int = 30,
    since: Optional[str] = None,
    team_id: Optional[str] = None,
    category: Optional[str] = None,
    position: Optional[str] = None,
):
    """Returns the most recent player transactions for a league in a normalized shape.

    Types: roster_add, roster_drop, waiver_won, waiver_lost, trade_executed,
    lineup_change.

    Filters:
      - `since`:    ISO date string ("2026-04-01") — only events on/after this date.
      - `team_id`:  filter by metadata.team_id (the actor team).
      - `category`: one of `adds_drops` (roster_add/roster_drop/waiver_won/waiver_lost),
                    `trades` (trade_executed), `lineup_changes` (lineup_change).
                    Defaults to all categories.
      - `position`: one of C / LW / RW / W / D / G — matches `metadata.player_position`
                    or any `metadata.moves[].position` (lineup changes). `W` matches
                    both LW and RW.
    """
    db = _deps["db"]

    # Iter 124 — category subfilter for the League History Transactions tab.
    category_map = {
        "adds_drops": ["roster_add", "roster_drop", "waiver_won", "waiver_lost"],
        "trades": ["trade_executed"],
        "lineup_changes": ["lineup_change"],
    }
    all_types = [
        "roster_add",
        "roster_drop",
        "waiver_won",
        "waiver_lost",
        "trade_executed",
        "lineup_change",
    ]
    types = category_map.get(category, all_types) if category else all_types

    query: dict = {
        "league_id": league_id,
        "event_type": {"$in": types},
    }
    if since:
        try:
            from datetime import datetime as _dt
            cutoff = _dt.fromisoformat(since.replace("Z", "+00:00"))
            query["created_at"] = {"$gte": cutoff}
        except Exception:
            pass
    if team_id:
        # Team filter has to span BOTH the single-actor activity rows
        # (metadata.team_id) AND trade rows that store team_ids on either
        # side (metadata.from_team_id / metadata.to_team_id), so a trade
        # involving the filtered team still surfaces.
        query["$or"] = [
            {"metadata.team_id": team_id},
            {"metadata.from_team_id": team_id},
            {"metadata.to_team_id": team_id},
            {"metadata.team_ids": team_id},
        ]

    if position:
        pos_targets: list[str] = []
        p = position.upper()
        if p == "W":
            pos_targets = ["LW", "RW", "W"]
        else:
            pos_targets = [p]
        # Match across the canonical metadata.player_position OR any
        # moves[].position entry (lineup_change rows).
        pos_clauses = [
            {"metadata.player_position": {"$in": pos_targets}},
            {"metadata.moves.position": {"$in": pos_targets}},
            {"metadata.players.position": {"$in": pos_targets}},
        ]
        if "$or" in query:
            query = {"$and": [query, {"$or": pos_clauses}]}
        else:
            query["$or"] = pos_clauses

    cursor = db.activity_feed.find(query).sort("created_at", -1).limit(max(1, min(limit, 500)))
    items = await cursor.to_list(limit)
    out = []
    for it in items:
        it["_id"] = str(it["_id"])
        meta = it.get("metadata") or {}
        out.append({
            "id": it["_id"],
            "type": it.get("event_type"),
            "description": it.get("message") or it.get("description"),
            "team_id": meta.get("team_id"),
            "team_name": meta.get("team_name"),
            "player_id": meta.get("player_id"),
            "player_name": meta.get("player_name"),
            "player_position": meta.get("player_position"),
            "bid_amount": meta.get("bid_amount"),
            "winning_team_name": meta.get("winning_team_name"),
            "winning_bid": meta.get("winning_bid"),
            "competing_claims": meta.get("competing_claims") or [],
            # Iter 124 — surface the lineup-change moves so the UI can
            # render per-player section transitions.
            "moves": meta.get("moves") or [],
            "move_count": meta.get("move_count"),
            "created_at": it.get("created_at"),
        })
    return {"league_id": league_id, "transactions": out, "count": len(out)}



# Pydantic body for legacy activity-feed chat (separate from /chat/* channels)


class _LeagueChatBody(BaseModel):
    text: str


@router.post("/activity/{league_id}/chat")
async def post_league_chat(league_id: str, input: _LeagueChatBody, request: Request):
    """Legacy activity-feed chat — appends a 'chat' event to the league
    activity feed. Distinct from /chat/* channels; preserved for the
    homepage activity ticker."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    log_activity = _deps["log_activity"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    sender = team["name"] if team else user.get("name") or user.get("email") or "Member"
    await log_activity(league_id, "chat", input.text, user["_id"], {"sender": sender})
    return {"message": "Chat posted"}

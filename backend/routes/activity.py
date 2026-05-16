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

from fastapi import APIRouter

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
):
    """Returns the most recent player transactions for a league in a normalized shape.

    Types: roster_add, roster_drop, waiver_won, waiver_lost, trade_executed.

    Filters:
      - `since`:  ISO date string ("2026-04-01") — only events on/after this date.
      - `team_id`: filter by metadata.team_id (the actor team).
    """
    db = _deps["db"]
    query: dict = {
        "league_id": league_id,
        "event_type": {
            "$in": [
                "roster_add",
                "roster_drop",
                "waiver_won",
                "waiver_lost",
                "trade_executed",
            ]
        },
    }
    if since:
        try:
            from datetime import datetime as _dt
            cutoff = _dt.fromisoformat(since.replace("Z", "+00:00"))
            query["created_at"] = {"$gte": cutoff}
        except Exception:
            pass
    if team_id:
        query["metadata.team_id"] = team_id
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
            "bid_amount": meta.get("bid_amount"),
            "winning_team_name": meta.get("winning_team_name"),
            "winning_bid": meta.get("winning_bid"),
            "competing_claims": meta.get("competing_claims") or [],
            "created_at": it.get("created_at"),
        })
    return {"league_id": league_id, "transactions": out, "count": len(out)}

"""Iter 231ai — Prospect pool list + watchlist endpoints.

Backed by the prospect data populated by iter 231ah's
`/admin/prospects/backfill` (1,368 NHL prospects from the 2020-2025
draft classes).

Routes:
    GET    /api/prospects                  — List + filter the pool.
                                              Query: ?year=2025&position=C
                                              &search=schaefer&limit=200.
    GET    /api/prospects/filters          — Distinct year + position
                                              values for the UI filter
                                              dropdowns (one call).
    GET    /api/prospects/watchlist        — Current user's watchlist
                                              with full prospect docs.
    POST   /api/prospects/watchlist/{pid}  — Add a prospect to the
                                              current user's watchlist.
    DELETE /api/prospects/watchlist/{pid}  — Remove a prospect from
                                              the current user's
                                              watchlist.

Watchlist storage: `users.prospect_watchlist: List[str]` (player_ids).
Per-user, not per-team, so the watchlist follows the user across
leagues/seasons.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from bson import ObjectId

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _serialize(p: dict, *, watchlist_ids: Optional[set] = None) -> dict:
    """Strip the Mongo `_id` to a string and expose only what the UI
    needs. Idempotent — safe to call on the same dict twice."""
    return {
        "id": str(p["_id"]),
        "name": p.get("name") or p.get("display_name") or "Unknown",
        "position": p.get("position") or "F",
        "team": p.get("team") or p.get("amateur_league") or "",
        "team_name": p.get("team_name") or "",
        "amateur_league": p.get("amateur_league") or "",
        "draft_year": p.get("draft_year"),
        "draft_round": p.get("draft_round"),
        "draft_pick_overall": p.get("draft_pick_overall"),
        "drafted_by_team": p.get("drafted_by_team") or "",
        "drafted_by_team_name": p.get("drafted_by_team_name") or "",
        "country_code": p.get("country_code") or "",
        "height_inches": p.get("height_inches"),
        "weight_lbs": p.get("weight_lbs"),
        "age": p.get("age"),
        "season": p.get("season"),
        "points": p.get("points") or 0,
        "games_played": p.get("games_played") or 0,
        "goals": p.get("goals") or 0,
        "assists": p.get("assists") or 0,
        "central_scouting_rank": p.get("central_scouting_rank"),
        "seed_source": p.get("seed_source"),
        "in_watchlist": bool(watchlist_ids and str(p["_id"]) in watchlist_ids),
    }


@router.get("/prospects")
async def list_prospects(
    request: Request,
    year: Optional[int] = Query(None, description="Filter by draft year (e.g. 2025)."),
    position: Optional[str] = Query(None, description="Filter by position (C, LW, RW, D, G)."),
    search: Optional[str] = Query(None, description="Name substring search (case-insensitive)."),
    drafted_by: Optional[str] = Query(None, description="3-letter NHL team abbrev (e.g. NYI)."),
    only_watchlist: bool = Query(False, description="Return only prospects in the current user's watchlist."),
    limit: int = Query(200, ge=1, le=500),
):
    """List + filter the prospect pool. Auth required so we can flag
    each row's `in_watchlist` for the calling user."""
    user = await _get_user(request)
    watchlist_ids = set(user.get("prospect_watchlist") or [])

    query: dict = {"player_type": "prospect"}
    if year is not None:
        query["draft_year"] = year
    if position:
        # Allow comma-separated multi-position (e.g. "LW,RW").
        positions = [p.strip().upper() for p in position.split(",") if p.strip()]
        query["position"] = {"$in": positions} if len(positions) > 1 else positions[0]
    if drafted_by:
        query["drafted_by_team"] = drafted_by.upper()
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if only_watchlist:
        if not watchlist_ids:
            return {"prospects": [], "count": 0}
        query["_id"] = {"$in": [ObjectId(pid) for pid in watchlist_ids if ObjectId.is_valid(pid)]}

    # Sort: most-recent draft year first, then by overall pick (best
    # available within each class first).
    cursor = (
        _db().players.find(query)
        .sort([("draft_year", -1), ("draft_pick_overall", 1)])
        .limit(limit)
    )
    rows = [_serialize(p, watchlist_ids=watchlist_ids) async for p in cursor]
    return {
        "prospects": rows,
        "count": len(rows),
        "filters": {
            "year": year, "position": position, "search": search,
            "drafted_by": drafted_by, "only_watchlist": only_watchlist,
        },
    }


@router.get("/prospects/filters")
async def prospect_filters(request: Request):
    """Distinct year + position + drafted-by values for filter dropdowns."""
    await _get_user(request)  # Auth gate only; payload doesn't depend on user.
    years_cursor = _db().players.aggregate([
        {"$match": {"player_type": "prospect", "draft_year": {"$ne": None}}},
        {"$group": {"_id": "$draft_year"}},
        {"$sort": {"_id": -1}},
    ])
    years = [row["_id"] async for row in years_cursor]
    positions_cursor = _db().players.aggregate([
        {"$match": {"player_type": "prospect", "position": {"$ne": None}}},
        {"$group": {"_id": "$position"}},
        {"$sort": {"_id": 1}},
    ])
    positions = [row["_id"] async for row in positions_cursor]
    teams_cursor = _db().players.aggregate([
        {"$match": {"player_type": "prospect", "drafted_by_team": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$drafted_by_team"}},
        {"$sort": {"_id": 1}},
    ])
    teams = [row["_id"] async for row in teams_cursor]
    return {"years": years, "positions": positions, "drafted_by_teams": teams}


# ─── Watchlist ─────────────────────────────────────────────────────


@router.get("/prospects/watchlist")
async def get_watchlist(request: Request):
    """Return the current user's full watchlist with prospect details."""
    user = await _get_user(request)
    watchlist_ids = list(user.get("prospect_watchlist") or [])
    if not watchlist_ids:
        return {"prospects": [], "count": 0}
    valid_oids = [ObjectId(pid) for pid in watchlist_ids if ObjectId.is_valid(pid)]
    cursor = _db().players.find({"_id": {"$in": valid_oids}})
    watchlist_set = set(watchlist_ids)
    rows = [_serialize(p, watchlist_ids=watchlist_set) async for p in cursor]
    return {"prospects": rows, "count": len(rows)}


@router.post("/prospects/watchlist/{prospect_id}")
async def add_to_watchlist(prospect_id: str, request: Request):
    """Add a prospect to the current user's watchlist (idempotent)."""
    user = await _get_user(request)
    if not ObjectId.is_valid(prospect_id):
        raise HTTPException(status_code=400, detail="Invalid prospect_id")
    prospect = await _db().players.find_one({
        "_id": ObjectId(prospect_id), "player_type": "prospect",
    })
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    # Iter 231ai — `user["_id"]` is a STRING (server.py:172 coerces from
    # ObjectId for safe JSON serialisation). Coerce back when writing
    # to Mongo so the update query actually matches a row.
    await _db().users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$addToSet": {"prospect_watchlist": prospect_id}},
    )
    return {
        "prospect_id": prospect_id,
        "name": prospect.get("name"),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "in_watchlist": True,
    }


@router.delete("/prospects/watchlist/{prospect_id}")
async def remove_from_watchlist(prospect_id: str, request: Request):
    """Remove a prospect from the current user's watchlist (idempotent)."""
    user = await _get_user(request)
    await _db().users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$pull": {"prospect_watchlist": prospect_id}},
    )
    return {
        "prospect_id": prospect_id,
        "removed_at": datetime.now(timezone.utc).isoformat(),
        "in_watchlist": False,
    }

"""Personalized league recommendations — extracted from server.py (iter 115).

Endpoint:
    GET /api/recommendations/leagues — ranked list (user's own leagues + open
    public leagues scored against commitment / scoring / draft preferences)
"""
from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Query, Request


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


_COMMITMENT_FORMAT_MAP = {
    "casual":   ["redraft", "best_ball"],
    "serious":  ["keeper"],
    "hardcore": ["dynasty"],
}


@router.get("/recommendations/leagues")
async def recommend_leagues(
    request: Request,
    commitment: str = Query("any", description="casual | serious | hardcore | any"),
    scoring: str = Query("any", description="head_to_head | rotisserie | total_points | any"),
    draft_style: str = Query("any", description="snake | auction | any"),
    limit: int = Query(5, ge=1, le=20),
):
    """Returns a ranked list — the user's own in-progress leagues first, then
    open public leagues scored against the three preference dimensions."""
    db = _db()
    user = await _get_user(request)

    # User's own leagues (continue where you left off)
    own_team_docs = await db.teams.find({"owner_id": user["_id"]}).to_list(200)
    own_league_ids = list({t["league_id"] for t in own_team_docs})
    own_leagues = []
    if own_league_ids:
        cursor = db.leagues.find({"_id": {"$in": [ObjectId(lid) for lid in own_league_ids]}})
        own_leagues = await cursor.to_list(50)

    # Candidate open leagues (not private, room available, not user's own)
    cursor = db.leagues.find({
        "is_private": {"$ne": True},
        "$expr": {"$lt": ["$current_teams", "$max_teams"]},
        "_id": {"$nin": [l["_id"] for l in own_leagues]},
    })
    candidates = await cursor.to_list(200)

    def score(lg: dict) -> int:
        s = 0
        fmt = lg.get("format", "")
        sc = lg.get("scoring_format", "")
        dr = lg.get("draft_type", "")

        if commitment in _COMMITMENT_FORMAT_MAP and fmt in _COMMITMENT_FORMAT_MAP[commitment]:
            s += 40
        elif commitment == "any":
            s += 10

        if scoring != "any" and sc == scoring:
            s += 30
        elif scoring == "any":
            s += 10

        if draft_style != "any" and dr == draft_style:
            s += 20
        elif draft_style == "any":
            s += 5

        fill = (lg.get("current_teams", 0) / max(1, lg.get("max_teams", 1)))
        if fill < 0.75:
            s += 10
        return s

    scored = [(score(lg), lg) for lg in candidates]
    scored.sort(key=lambda t: t[0], reverse=True)
    ranked = scored[:limit]

    def _format(lg: dict, reason: str, is_own: bool, s: int) -> dict:
        return {
            "id": str(lg["_id"]),
            "name": lg["name"],
            "format": lg.get("format", ""),
            "scoring_format": lg.get("scoring_format", ""),
            "draft_type": lg.get("draft_type", ""),
            "current_teams": lg.get("current_teams", 0),
            "max_teams": lg.get("max_teams", 0),
            "entry_fee": lg.get("entry_fee"),
            "invite_code": lg.get("invite_code"),
            "premium": bool(lg.get("premium", False)),
            "is_own": is_own,
            "match_score": s,
            "match_reason": reason,
        }

    results = []
    for lg in own_leagues[:3]:
        results.append(_format(lg, "Continue where you left off", is_own=True, s=100))
    for s, lg in ranked:
        reason_parts = []
        if commitment != "any" and lg.get("format") in _COMMITMENT_FORMAT_MAP.get(commitment, []):
            reason_parts.append(f"matches your {commitment} commitment")
        if scoring != "any" and lg.get("scoring_format") == scoring:
            reason_parts.append(f"{scoring.replace('_',' ')} scoring")
        if draft_style != "any" and lg.get("draft_type") == draft_style:
            reason_parts.append(f"{draft_style} draft")
        reason = ", ".join(reason_parts) or "Great open league with room to join"
        results.append(_format(lg, reason, is_own=False, s=s))

    return {
        "has_active_leagues": len(own_leagues) > 0,
        "preferences": {"commitment": commitment, "scoring": scoring, "draft_style": draft_style},
        "recommendations": results[:limit + 3],
    }

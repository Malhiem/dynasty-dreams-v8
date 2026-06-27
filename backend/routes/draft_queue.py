"""Draft queue + shortlist router — extracted from `routes/drafts.py`
(iter 231k) to continue reducing drafts.py footprint.

This module owns the per-team auto-pick queue + watch-list endpoints
(used by the Draft Room sidebar). Both are owner-only writes with a
commissioner override. Reads are open to any authenticated user.

  • PUT  /api/teams/{team_id}/draft-queue  — persist auto-pick queue
  • GET  /api/teams/{team_id}/draft-queue  — read auto-pick queue
  • PUT  /api/teams/{team_id}/shortlist    — persist scouting shortlist
  • GET  /api/teams/{team_id}/shortlist    — read shortlist

Wired via the `setup(deps)` injection pattern shared across modular
routers; see `server.py`.
"""
from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


class DraftQueueRequest(BaseModel):
    player_ids: list[str] = Field(default_factory=list)


class ShortlistRequest(BaseModel):
    player_ids: list[str] = Field(default_factory=list)


def _dedupe_capped(ids: list[str], cap: int) -> list[str]:
    """Strip duplicates while preserving order; clamp at `cap` entries."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            cleaned.append(pid)
        if len(cleaned) >= cap:
            break
    return cleaned


@router.put("/teams/{team_id}/draft-queue")
async def update_team_draft_queue(team_id: str, payload: DraftQueueRequest, request: Request):
    """Owner-only: persist the team's auto-pick queue (list of player ids).

    The auto-pick endpoint reads this list when a manager's clock
    expires and drafts the first undrafted entry before falling back
    to the global top-ranked eligible player.
    """
    user = await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await _db().leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_owner = team.get("owner_id") == user["_id"]
    is_comm = league and league.get("commissioner_id") == user["_id"]
    if not (is_owner or is_comm):
        raise HTTPException(
            status_code=403,
            detail="Only the team's owner or league commissioner can edit the draft queue",
        )
    cleaned = _dedupe_capped(payload.player_ids, cap=100)
    await _db().teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"draft_queue": cleaned}},
    )
    return {"team_id": team_id, "draft_queue": cleaned, "size": len(cleaned)}


@router.get("/teams/{team_id}/draft-queue")
async def get_team_draft_queue(team_id: str, request: Request):
    await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "draft_queue": list(team.get("draft_queue") or [])}


@router.put("/teams/{team_id}/shortlist")
async def update_team_shortlist(team_id: str, payload: ShortlistRequest, request: Request):
    """Owner-or-commissioner: persist the team's draft Shortlist (the
    ordered watch-list the manager curates while scouting)."""
    user = await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await _db().leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_owner = team.get("owner_id") == user["_id"]
    is_comm = league and league.get("commissioner_id") == user["_id"]
    if not (is_owner or is_comm):
        raise HTTPException(
            status_code=403,
            detail="Only the team's owner or league commissioner can edit the shortlist",
        )
    cleaned = _dedupe_capped(payload.player_ids, cap=200)
    await _db().teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"shortlist": cleaned}},
    )
    return {"team_id": team_id, "shortlist": cleaned, "size": len(cleaned)}


@router.get("/teams/{team_id}/shortlist")
async def get_team_shortlist(team_id: str, request: Request):
    await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "shortlist": list(team.get("shortlist") or [])}

"""Cap Floor Watchlist (iter 122).

Endpoint
--------
GET /api/leagues/{league_id}/cap-floor-watchlist
    Returns every team's cap-floor compliance state for the current year,
    plus the league-configured warning threshold and the in-watchlist
    boundary. Used by the Salary Cap page commissioner card and (future)
    weekly notification dispatcher.

Auth: any league member can read (read-only data, no sensitive info).

Response shape
--------------
{
  "league_id": "...",
  "floor_enabled": bool,
  "floor": int,                       # current-year floor, 0 if disabled
  "warning_threshold": int,           # $ amount within which we flag teams
  "year": int,
  "teams": [
    {
      "team_id": "...",
      "team_name": "...",
      "owner_id": "...",
      "payroll": int,                  # sum(active contract AAVs) + dead cap
      "delta_to_floor": int,           # payroll - floor (negative => below)
      "status": "above" | "watchlist" | "below",
    }, ...
  ]
}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


# Default warning threshold ($5M) — generous enough that committees see
# at-risk teams a few moves before the deadline. Override per league via
# `salary_cap_floor_warning_threshold` field on the league document.
DEFAULT_WARNING_THRESHOLD = 5_000_000


async def _team_payroll_current_year(db, team_id: str) -> int:
    """Sum the team's active-contract AAVs for the current calendar year
    + any dead-cap entries scheduled for it. Mirrors the salary-cap page
    "cur" calculation so the watchlist agrees with the user's screen."""
    year = datetime.now(timezone.utc).year
    payroll = 0
    cursor = db.contracts.find({"team_id": team_id, "status": "active"})
    async for c in cursor:
        salary = int(c.get("aav") or c.get("salary") or 0)
        start = int(c.get("start_year") or year)
        end = int(c.get("end_year") or start)
        if start <= year <= end:
            payroll += salary
    team = await db.teams.find_one({"_id": ObjectId(team_id)}, {"dead_cap_schedule": 1})
    if team:
        for row in (team.get("dead_cap_schedule") or []):
            if int(row.get("year") or 0) == year:
                payroll += int(row.get("total") or 0)
    return payroll


@router.get("/leagues/{league_id}/cap-floor-watchlist")
async def get_cap_floor_watchlist(league_id: str, request: Request):
    db = _db()
    await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league_id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    floor_enabled = bool(league.get("cap_floor_enabled"))
    floor = int(league.get("cap_floor") or 0) if floor_enabled else 0
    threshold = int(
        league.get("salary_cap_floor_warning_threshold") or DEFAULT_WARNING_THRESHOLD
    )
    year = datetime.now(timezone.utc).year

    teams = await db.teams.find({"league_id": league_id}).to_list(60)
    rows = []
    for t in teams:
        tid = str(t["_id"])
        payroll = await _team_payroll_current_year(db, tid)
        delta = payroll - floor  # negative when below floor
        if not floor_enabled or floor <= 0:
            status = "above"
        elif delta < 0:
            status = "below"
        elif delta <= threshold:
            status = "watchlist"
        else:
            status = "above"
        rows.append({
            "team_id": tid,
            "team_name": t.get("name"),
            "owner_id": t.get("owner_id"),
            "payroll": payroll,
            "delta_to_floor": delta,
            "status": status,
        })

    # Sort: below first, then watchlist, then above — commissioners need
    # the at-risk rows at the top.
    status_rank = {"below": 0, "watchlist": 1, "above": 2}
    rows.sort(key=lambda r: (status_rank.get(r["status"], 9), r["delta_to_floor"]))

    return {
        "league_id": league_id,
        "floor_enabled": floor_enabled,
        "floor": floor,
        "warning_threshold": threshold,
        "year": year,
        "teams": rows,
        "summary": {
            "below_count": sum(1 for r in rows if r["status"] == "below"),
            "watchlist_count": sum(1 for r in rows if r["status"] == "watchlist"),
            "above_count": sum(1 for r in rows if r["status"] == "above"),
        },
    }

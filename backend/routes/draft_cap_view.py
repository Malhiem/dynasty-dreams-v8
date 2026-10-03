"""Iter 232N.62 — Draft-room cap view.

Powers the in-draft "Cap View" side rail + player-card cap-hit chips
+ greying-out of players who would exceed the current user's remaining
cap.

Endpoint:
  GET /api/drafts/{draft_id}/cap-status
    → {
        salary_cap_enabled, salary_cap,
        default_rookie_aav, minors_cap_treatment,
        approaching_pct,    # 90 by default; UI treats >= as "approaching"
        my_team_id,         # convenience — the caller's team in this league
        teams: [
          {
            team_id, name,
            salary_used, salary_cap, remaining,
            percent_used,   # 0..100
            over_cap,       # bool
            approaching,    # bool — percent_used >= 90
            picks_count,    # number of picks made so far
          },
          ...
        ],
      }

All values are Ints in dollars. Non-cap leagues return
`salary_cap_enabled: false` and empty teams array so the frontend can
short-circuit cleanly.
"""
from __future__ import annotations

import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)
    from routes import draft_roster
    draft_roster.setup(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


def _resolve_player_aav(player: dict, default_rookie_aav: int) -> int:
    """Iter 232N.62 — Same resolution rule the roster + trade block use:
    ``player.contract.aav → player.cap_hit → player.salary → default_rookie_aav``.

    Zero-valued entries are treated as "no data" and fall through to
    the default, matching what the UI would render as a projected AAV
    for a draft-eligible player."""
    contract = player.get("contract") or {}
    for candidate in (
        contract.get("aav"),
        player.get("cap_hit"),
        player.get("salary"),
    ):
        if candidate:
            try:
                v = int(candidate)
                if v > 0:
                    return v
            except (ValueError, TypeError):
                continue
    return int(default_rookie_aav)


from routes.draft_roster import router as roster_router
router.include_router(roster_router)

@router.get("/drafts/{draft_id}/cap-status")
async def get_draft_cap_status(draft_id: str, request: Request):
    """Iter 232N.62 — Per-team cap usage for the draft's active league.

    Sums every pick's resolved AAV per team so the caller can render the
    Cap View side rail with the correct "used / cap" bars.
    """
    user = await _get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = _db()
    try:
        draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        draft = None
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league_id = draft.get("league_id")
    if not league_id:
        raise HTTPException(status_code=400, detail="Draft has no league_id")

    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    from routes.league_guards import require_league_member
    await require_league_member(db, user, league_id)
    salary_cap_enabled = bool(league.get("salary_cap_enabled"))
    salary_cap = int(league.get("salary_cap") or 0)
    # 232N.62 — league admin can set a fallback AAV for unpriced
    # players (default rookie ELC). Falls back to 950_000 (2026 CBA
    # league-minimum) when unset.
    default_rookie_aav = int(league.get("default_rookie_aav") or 950_000)
    minors_cap_treatment = league.get("minors_cap_treatment") or "full"

    if not salary_cap_enabled or salary_cap <= 0:
        return {
            "draft_id": draft_id,
            "league_id": league_id,
            "salary_cap_enabled": False,
            "salary_cap": 0,
            "default_rookie_aav": default_rookie_aav,
            "minors_cap_treatment": minors_cap_treatment,
            "approaching_pct": 90,
            "my_team_id": None,
            "teams": [],
        }

    # Build team roster of the league (id → name + owner_id).
    teams: dict[str, dict] = {}
    async for t in db.teams.find({"league_id": league_id}):
        tid = str(t["_id"])
        teams[tid] = {
            "team_id": tid,
            "name": t.get("name"),
            "owner_id": t.get("owner_id"),
            "salary_used": 0,
            "picks_count": 0,
        }

    # Sum AAV of every picked player per team using the same resolver
    # as roster/trade block (contract.aav → cap_hit → salary → default).
    my_team_id: Optional[str] = None
    async for pick in db.draft_picks.find({
        "draft_id": draft_id, "player_id": {"$ne": None},
    }):
        tid = pick.get("team_id")
        pid = pick.get("player_id")
        if not tid or not pid or tid not in teams:
            continue
        try:
            player = await db.players.find_one({"_id": ObjectId(pid)})
        except Exception:
            player = None
        aav = _resolve_player_aav(player or {}, default_rookie_aav)
        teams[tid]["salary_used"] += aav
        teams[tid]["picks_count"] += 1

    # Determine "my_team_id" — the caller's team in this league.
    caller_uid = str(user["_id"])
    for tid, t in teams.items():
        if str(t.get("owner_id") or "") == caller_uid:
            my_team_id = tid
            break

    APPROACHING_PCT = 90

    def _decorate(t: dict) -> dict:
        used = int(t["salary_used"])
        remaining = salary_cap - used
        pct = round((used / salary_cap) * 100, 1) if salary_cap else 0
        return {
            "team_id": t["team_id"],
            "name": t["name"],
            "salary_used": used,
            "salary_cap": salary_cap,
            "remaining": remaining,
            "percent_used": pct,
            "over_cap": remaining < 0,
            "approaching": pct >= APPROACHING_PCT,
            "picks_count": t["picks_count"],
        }

    from services.draft_salary import team_summary
    decorated = []
    async for team in db.teams.find({"league_id": league_id}):
        decorated.append(await team_summary(db, draft, team, league))
    decorated.sort(key=lambda x: (-x["percent_used"], x["name"] or ""))

    return {
        "draft_id": draft_id,
        "league_id": league_id,
        "salary_cap_enabled": True,
        "salary_cap": salary_cap,
        "default_rookie_aav": default_rookie_aav,
        "minors_cap_treatment": minors_cap_treatment,
        "approaching_pct": APPROACHING_PCT,
        "my_team_id": my_team_id,
        "teams": decorated,
    }

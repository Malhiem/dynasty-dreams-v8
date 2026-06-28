"""Draft order router — extracted from `routes/drafts.py` (iter 231v).

Owns the two endpoints that read + configure a league's draft order:

  • GET /api/leagues/{league_id}/draft-order
  • PUT /api/leagues/{league_id}/draft-order/config

These two cluster together because they share the
`draft_order_method` / `draft_order_scheduled_at` schema on the
leagues collection, the same DRAFT_ORDER_METHODS enum, and the same
fall-back-to-reverse-standings behaviour. Splitting them off lets us
ratchet drafts.py below the 600-line target.

Wired via the `setup(deps)` injection pattern in `server.py`.
"""
from __future__ import annotations

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


# Valid values for the league's `draft_order_method` field. `nhl_lottery`
# sources its scheduled date globally from system_settings; the other
# two are configured per-league.
DRAFT_ORDER_METHODS = {"nhl_lottery", "lottery_generator", "manual_entry"}


@router.get("/leagues/{league_id}/draft-order")
async def get_league_draft_order(league_id: str, year: Optional[int] = None):
    """Iter 137 + 138 — compute the canonical draft order for a given year.

    Returns the ordered seeds plus the configured method + schedule so the
    Draft Board can render a "pick order: set / pending" status banner.
    """
    db = _db()
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    # Iter 138 — fetch method + scheduled timestamp (per-league or global)
    method = (league.get("draft_order_method") or "manual_entry").strip()
    scheduled_at = league.get("draft_order_scheduled_at")
    schedule_source = "league"
    if method == "nhl_lottery":
        sysdoc = await db.system_settings.find_one({"_id": "draft_lottery"})
        scheduled_at = (sysdoc or {}).get("nhl_lottery_date")
        schedule_source = "system"
    # ISO-string the datetime if it's a real datetime object
    if hasattr(scheduled_at, "isoformat"):
        scheduled_at = scheduled_at.isoformat()

    # 1. Try locked-in pick_number on this year's round-1 picks
    yr = int(year) if year else None
    rd1_query: dict = {"league_id": league_id, "round": 1}
    if yr:
        rd1_query["year"] = yr
    round1 = await db.draft_picks.find(rd1_query).to_list(200)
    with_number = [p for p in round1 if p.get("pick_number") is not None]
    if with_number and len(with_number) == len(teams):
        ordered = sorted(with_number, key=lambda p: int(p["pick_number"]))
        return {
            "league_id": league_id,
            "year": yr,
            "source": "lottery_applied",
            "is_set": True,
            "method": method,
            "scheduled_at": scheduled_at,
            "schedule_source": schedule_source,
            "order": [
                {
                    "team_id": str(p.get("original_team_id")),
                    "seed": int(p["pick_number"]),
                    "source": "lottery_applied",
                }
                for p in ordered
            ],
        }

    # 2. Fall back to reverse standings (worst first).
    def _key(t: dict):
        pts = float(t.get("points_for") or 0.0)
        wins = int(t.get("wins") or 0)
        losses = int(t.get("losses") or 0)
        return (wins, -losses, pts, t.get("name", ""))
    sorted_teams = sorted(teams, key=_key)
    return {
        "league_id": league_id,
        "year": yr,
        "source": "reverse_standings",
        "is_set": False,
        "method": method,
        "scheduled_at": scheduled_at,
        "schedule_source": schedule_source,
        "order": [
            {"team_id": str(t["_id"]), "seed": i + 1, "source": "reverse_standings"}
            for i, t in enumerate(sorted_teams)
        ],
    }


class DraftOrderConfigRequest(BaseModel):
    method: Optional[str] = None  # one of DRAFT_ORDER_METHODS
    scheduled_at: Optional[str] = None  # ISO datetime, "" or null to clear


@router.put("/leagues/{league_id}/draft-order/config")
async def update_league_draft_order_config(
    league_id: str, payload: DraftOrderConfigRequest, request: Request,
):
    """Commissioner-only. Sets the league's draft-order method and the
    scheduled date (for `lottery_generator` and `manual_entry`). For
    `nhl_lottery` the date is sourced globally from system settings and
    cannot be set here.
    """
    db = _db()
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may set the draft order config")

    update: dict = {}
    if payload.method is not None:
        if payload.method not in DRAFT_ORDER_METHODS:
            raise HTTPException(status_code=400, detail=f"method must be one of {sorted(DRAFT_ORDER_METHODS)}")
        update["draft_order_method"] = payload.method
        # If switching to nhl_lottery, clear any per-league date
        if payload.method == "nhl_lottery":
            update["draft_order_scheduled_at"] = None
    if payload.scheduled_at is not None:
        if payload.scheduled_at == "":
            update["draft_order_scheduled_at"] = None
        else:
            update["draft_order_scheduled_at"] = payload.scheduled_at
    if not update:
        return {"ok": True, "league_id": league_id, "changed": False}
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": update})
    return {"ok": True, "league_id": league_id, "changed": True, **update}

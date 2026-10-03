"""Iter 232i — Commissioner-granted bonus draft picks.

Real-world dynasty leagues frequently need to layer extra picks on
top of the standard `rounds × teams` grid: **compensation** picks
for a team that had a starter's contract terminated, **expansion**
picks for a newly-added franchise. This router surfaces the CRUD
lifecycle behind that need.

The picks are persisted directly onto the draft doc as
`draft.bonus_picks: [{...}]` because they conceptually belong to a
specific draft (not the league globally) and because the engine
(`get_team_for_pick`) needs O(1) access to the list without a
separate collection lookup on every pick.

Guardrails (enforced here, mirrored by pytest guards):
  • Commissioner-only route (same pattern as every other draft-admin
    route in this codebase).
  • Bonus picks can be added or removed **pre- or mid-draft** — the
    only constraint is the target position must NOT have been
    reached yet. Adding at `overall_position <= draft.current_pick`
    is rejected with a 409.
  • The commissioner picks the position mode:
      - `end_of_round`: pick slots in immediately after round N's
        last pick (overall = round_end + 1 + N of prior bonuses in
        the same round).
      - `overall`: pick slots in at a specific `overall_position`.
    Both modes resolve to a concrete `overall` int before storage.
  • Tradeability is per-pick — commissioner decides. When pick
    trading is enabled and a bonus pick is marked tradeable, we
    also insert a matching row into `draft_picks` so the trade
    center can operate on it.
"""
from typing import Optional, Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


class AddBonusPickRequest(BaseModel):
    team_id: str = Field(..., description="The team that receives the extra pick.")
    bonus_kind: Literal["compensation", "expansion"]
    position_mode: Literal["end_of_round", "overall"]
    after_round: Optional[int] = Field(
        default=None,
        description="For position_mode='end_of_round': insert AFTER the last pick of this round.",
    )
    overall_position: Optional[int] = Field(
        default=None,
        description="For position_mode='overall': insert at this overall pick number.",
    )
    tradeable: bool = True
    note: Optional[str] = Field(default=None, max_length=200)


async def _load_draft_and_authorise(draft_id: str, request) -> tuple[dict, str]:
    """Resolve the draft, verify commissioner, and return
    (draft_doc, user_id). Raises 404 / 403 as appropriate."""
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=404, detail="Draft not found")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    user = await _get_user(request)
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if (
        league.get("commissioner_id") != user["_id"]
        and user["_id"] not in (league.get("co_commissioners") or [])
    ):
        raise HTTPException(status_code=403, detail="Only commissioners can manage bonus picks")
    return draft, user["_id"]


def _resolve_overall(draft: dict, body: AddBonusPickRequest) -> int:
    """Turn either position_mode into a concrete overall pick #.

    For `end_of_round`: overall = (after_round × team_count) + 1 +
    (count of existing bonus picks that also live at end of the same
    round). That way multiple compensation picks queued after round
    2 slot in order rather than colliding.

    For `overall`: use `overall_position` verbatim, clamped to the
    valid range `[1, total_picks + 1]`.
    """
    team_count = len(draft.get("team_abbrs") or [])
    if team_count <= 0:
        raise HTTPException(status_code=422, detail="Draft has no teams yet")
    existing = list(draft.get("bonus_picks") or [])
    total_rounds = int(draft.get("total_rounds") or 0)
    base_total = total_rounds * team_count

    if body.position_mode == "end_of_round":
        if body.after_round is None:
            raise HTTPException(status_code=422, detail="after_round is required for end_of_round mode")
        r = int(body.after_round)
        if r < 1 or r > total_rounds:
            raise HTTPException(status_code=422, detail=f"after_round must be between 1 and {total_rounds}")
        # Position slots in after the round's last natural pick.
        # Count bonus picks already at this exact end-of-round anchor.
        anchor_overall = r * team_count + 1
        anchor_count = sum(
            1 for bp in existing
            if bp.get("position_mode") == "end_of_round"
            and int(bp.get("after_round") or 0) == r
        )
        return anchor_overall + anchor_count

    # position_mode == "overall"
    if body.overall_position is None:
        raise HTTPException(status_code=422, detail="overall_position is required for overall mode")
    pos = int(body.overall_position)
    if pos < 1:
        raise HTTPException(status_code=422, detail="overall_position must be >= 1")
    # Allow inserting at the very end (base_total + existing bonuses + 1).
    max_allowed = base_total + len(existing) + 1
    if pos > max_allowed:
        raise HTTPException(
            status_code=422,
            detail=f"overall_position must be <= {max_allowed}",
        )
    return pos


def _shift_bonus_and_picks(existing_bonus: list[dict], insert_at: int) -> list[dict]:
    """Return a new bonus_picks list with every entry at
    `overall >= insert_at` bumped by 1. Preserves ordering by
    `overall` ascending so callers don't have to re-sort."""
    out = []
    for bp in existing_bonus:
        ov = int(bp.get("overall", 0))
        if ov >= insert_at:
            bp2 = dict(bp)
            bp2["overall"] = ov + 1
            out.append(bp2)
        else:
            out.append(dict(bp))
    out.sort(key=lambda b: int(b.get("overall", 0)))
    return out


@router.get("/drafts/{draft_id}/bonus-picks")
async def list_bonus_picks(draft_id: str, request: Request):
    """Anyone with an auth token can read the bonus-picks list — same
    visibility policy as the draft board itself. We surface a sanitised
    view with `team_name` and `team_abbr` populated for the UI."""
    draft, _ = await _load_draft_and_authorise(draft_id, request)
    return {"bonus_picks": draft.get("bonus_picks") or []}


@router.post("/drafts/{draft_id}/bonus-picks")
async def add_bonus_pick(draft_id: str, body: AddBonusPickRequest, request: Request):
    draft, _uid = await _load_draft_and_authorise(draft_id, request)
    # Resolve team + abbr up front so we store a stable snapshot even
    # if the team is renamed later.
    try:
        team = await _db().teams.find_one({"_id": ObjectId(body.team_id)})
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid team_id")
    if not team or team.get("league_id") != draft.get("league_id"):
        raise HTTPException(status_code=422, detail="Team does not belong to this league")
    team_map = draft.get("team_map") or {}
    team_abbr = None
    for abbr, meta in team_map.items():
        if meta.get("id") == body.team_id or meta.get("_id") == body.team_id:
            team_abbr = abbr
            break
    if not team_abbr:
        # Fallback: derive from team_abbrs based on team.name — rare
        # but happens when team_map wasn't seeded on older drafts.
        abbrs = draft.get("team_abbrs") or []
        raw_name = str(team.get("name") or "").upper()
        for a in abbrs:
            if raw_name.startswith(a):
                team_abbr = a
                break
    if not team_abbr:
        raise HTTPException(
            status_code=422,
            detail="Could not resolve team abbreviation in this draft",
        )

    overall = _resolve_overall(draft, body)
    # Guardrail: can't add a pick at a position that's already passed.
    current_pick = int(draft.get("current_pick") or 1)
    if overall <= current_pick and draft.get("status") == "active":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot insert a bonus pick at overall #{overall} — the draft is "
                f"already on pick #{current_pick}. Choose a later position."
            ),
        )

    new_bonus_entry = {
        "id": str(ObjectId()),
        "team_id": body.team_id,
        "team_name": team.get("name") or "Unknown",
        "team_abbr": team_abbr,
        "bonus_kind": body.bonus_kind,
        "position_mode": body.position_mode,
        "after_round": body.after_round,
        "overall": overall,
        "tradeable": bool(body.tradeable),
        "note": (body.note or "").strip() or None,
    }
    shifted = _shift_bonus_and_picks(draft.get("bonus_picks") or [], overall)
    # Insert the new one in the right position and re-sort by overall.
    shifted.append(new_bonus_entry)
    shifted.sort(key=lambda b: int(b.get("overall", 0)))

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"bonus_picks": shifted}},
    )

    # If pick trading is enabled AND draft_picks have been seeded,
    # also shift + insert the corresponding tradeable pick row so the
    # trade center picks up the change immediately.
    trading_on = bool(draft.get("pick_trading_enabled"))
    if trading_on:
        # Shift existing draft_picks with overall >= new pos.
        await _db().draft_picks.update_many(
            {"draft_id": draft_id, "overall": {"$gte": overall}},
            {"$inc": {"overall": 1}},
        )
        await _db().draft_picks.insert_one({
            "league_id": draft.get("league_id"),
            "draft_id": draft_id,
            "year": int((draft.get("year") or 2026)),
            "round": None,  # bonus picks aren't tied to a round
            "slot": None,
            "overall": overall,
            "original_team_id": body.team_id,
            "original_team_name": team.get("name") or "Unknown",
            "current_team_id": body.team_id,
            "current_team_name": team.get("name") or "Unknown",
            "trade_history": [],
            "tradeable": bool(body.tradeable),
            "is_bonus": True,
            "bonus_kind": body.bonus_kind,
            "bonus_note": (body.note or "").strip() or None,
        })

    return {"bonus_pick": new_bonus_entry, "bonus_picks": shifted}


@router.delete("/drafts/{draft_id}/bonus-picks/{bonus_id}")
async def remove_bonus_pick(draft_id: str, bonus_id: str, request: Request):
    draft, _uid = await _load_draft_and_authorise(draft_id, request)
    existing = list(draft.get("bonus_picks") or [])
    target = next((bp for bp in existing if bp.get("id") == bonus_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Bonus pick not found")
    overall = int(target.get("overall") or 0)
    current_pick = int(draft.get("current_pick") or 1)
    if overall <= current_pick and draft.get("status") == "active":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot remove a bonus pick that has already been reached "
                f"(pick #{overall}). Undo the pick first if you want to remove it."
            ),
        )

    # Drop + shift everything at overall > this one back by 1.
    updated = []
    for bp in existing:
        if bp.get("id") == bonus_id:
            continue
        bp2 = dict(bp)
        if int(bp2.get("overall", 0)) > overall:
            bp2["overall"] = int(bp2["overall"]) - 1
        updated.append(bp2)
    updated.sort(key=lambda b: int(b.get("overall", 0)))

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"bonus_picks": updated}},
    )

    # Same shift on draft_picks collection if it exists.
    if bool(draft.get("pick_trading_enabled")):
        await _db().draft_picks.delete_one({
            "draft_id": draft_id, "overall": overall, "is_bonus": True,
        })
        await _db().draft_picks.update_many(
            {"draft_id": draft_id, "overall": {"$gt": overall}},
            {"$inc": {"overall": -1}},
        )

    return {"deleted": bonus_id, "bonus_picks": updated}

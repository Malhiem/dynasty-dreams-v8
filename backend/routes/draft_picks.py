"""Per-pick router — extracted from `routes/drafts.py` (iter 231l).

Currently owns the per-pick *defer-to-user* endpoints. The companion
make-pick / undo-pick / seed-picks endpoints stay in drafts.py for now
because they have deep cross-dependencies on internal helpers
(`_perform_one_auto_pick`, `_handle_post_pick_logic`, the pick-trade
materialization). Those will move in a future iter.

  • POST /api/drafts/{draft_id}/picks/{pick_no}/defer
        Record an owner's defer-to-user choice.
  • GET  /api/drafts/{draft_id}/picks/{pick_no}/defer
        Read the persisted choice + the draft-level options the user
        can choose from.

Wired via the `setup(deps)` injection pattern; see `server.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter()
_deps: dict = {}

# Valid defer-to-user choices (kept here so the module is self-contained
# rather than reaching back into drafts.py for a constant).
_VALID_DEFER_CHOICES = {"auto-best", "auto-queue", "pick-anytime"}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


class DeferPickChoiceRequest(BaseModel):
    """Owner's choice when their pick timer expires and the draft's
    `missed_pick_action == "defer-to-user"`.
    """
    choice: str  # see _VALID_DEFER_CHOICES


@router.post("/drafts/{draft_id}/picks/{pick_no}/defer")
async def set_pick_defer_choice(
    draft_id: str,
    pick_no: int,
    body: DeferPickChoiceRequest,
    request: Request,
):
    """Records the owner's defer-to-user choice for a specific pick.

    Only callable by the team's owner (or an admin); persists onto the
    pick document. If the pick hasn't been materialized yet, the choice
    is pre-claimed under `draft.pick_defer_choices.{pick_no}` and rolled
    onto the pick when it appears.

    Valid choices:
      • auto-best    — engine auto-selects the best available player NOW
      • auto-queue   — engine auto-selects the next-available from the
                       team's draft queue
      • pick-anytime — the pick is skipped (other rounds continue);
                       owner can return and pick anytime before draft end
    """
    user = await _get_user(request)
    if body.choice not in _VALID_DEFER_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"choice must be one of {sorted(_VALID_DEFER_CHOICES)}",
        )

    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("missed_pick_action") != "defer-to-user":
        raise HTTPException(
            status_code=400,
            detail="This draft's missed_pick_action is not 'defer-to-user'.",
        )

    # Locate the pick (1-indexed). If not yet materialized, pre-claim it.
    picks = draft.get("picks") or []
    pick = next(
        (p for p in picks if int(p.get("pick_no", 0)) == int(pick_no)),
        None,
    )
    if pick is None:
        await _db().drafts.update_one(
            {"_id": ObjectId(draft_id)},
            {"$set": {
                f"pick_defer_choices.{pick_no}": {
                    "choice": body.choice,
                    "team_id": None,  # client may not know yet
                    "claimed_at": datetime.now(timezone.utc).isoformat(),
                    "claimed_by": user["_id"],
                },
            }},
        )
        return {
            "draft_id": draft_id,
            "pick_no": pick_no,
            "choice": body.choice,
            "stored": "pending",
        }

    # Auth: only the owner of the pick (or an admin) may set the choice.
    pick_team_id = pick.get("team_id")
    if user.get("role") != "admin":
        team = await _db().teams.find_one(
            {"_id": ObjectId(pick_team_id)},
        ) if pick_team_id else None
        if not team or team.get("owner_id") != user["_id"]:
            raise HTTPException(
                status_code=403,
                detail="Only the pick's owner can set this.",
            )

    # Atomic update on the pick itself.
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id), "picks.pick_no": int(pick_no)},
        {"$set": {
            "picks.$.defer_choice": body.choice,
            "picks.$.defer_chosen_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "draft_id": draft_id,
        "pick_no": pick_no,
        "team_id": pick_team_id,
        "choice": body.choice,
        "stored": "on_pick",
    }


@router.get("/drafts/{draft_id}/picks/{pick_no}/defer")
async def get_pick_defer_choice(draft_id: str, pick_no: int, request: Request):
    """Returns the persisted defer choice + the draft-level options the
    user can choose from. Surfaces both the per-pick state AND the
    available `defer_user_options` so the draft-room dialog has a single
    fetch instead of two."""
    await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    picks = draft.get("picks") or []
    pick = next(
        (p for p in picks if int(p.get("pick_no", 0)) == int(pick_no)),
        None,
    )
    pending = (draft.get("pick_defer_choices") or {}).get(str(pick_no))
    available = draft.get("defer_user_options") or [
        "auto-best", "auto-queue", "pick-anytime",
    ]
    return {
        "draft_id": draft_id,
        "pick_no": pick_no,
        "available_options": available,
        "defer_choice": (pick or {}).get("defer_choice")
            or (pending or {}).get("choice"),
        "defer_chosen_at": (pick or {}).get("defer_chosen_at")
            or (pending or {}).get("claimed_at"),
    }

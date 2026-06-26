"""Iter 230d — NHL data sync dispatcher.

Wraps player-doc updates with automatic notification side-effects. Any
incoming NHL data sync (live-poll, daily roster refresh, news scraper,
manual admin patch) routes through `apply_player_diff_and_notify`, which:

  1. Fetches the current `players` document.
  2. Diffs the incoming fields against the current state.
  3. Persists the update via a single `update_one($set=...)`.
  4. For status fields we care about (`injury_status`, `league_status`),
     classifies the transition and calls the shared
     `notify_player_status_change` helper so every team rostering the
     player gets the right notification — without each caller having to
     know how to drive `create_notification`.

This decouples "what changed" (data ingestion's job) from "who do we
ping" (notifier's job).
"""
from typing import Awaitable, Callable, Dict, Optional

from bson import ObjectId

from services.player_status_notifier import notify_player_status_change


# Sets of `injury_status` strings the front-end treats as "out".
# Source of truth = the same constants used in routes/players.py
# eligibility filters (IR / OUT / INJURED RESERVE).
_INACTIVE_INJURY_STATUSES = {"IR", "OUT", "INJURED RESERVE", "LTIR", "SUSPENDED"}
_ACTIVE_INJURY_STATUSES = {"", "HEALTHY", "ACTIVE", "DAY-TO-DAY", "PROBABLE", "DTD"}


def _classify_injury_transition(prev: str, new: str) -> Optional[str]:
    """Returns the change_kind for `notify_player_status_change` or None
    if the transition isn't notification-worthy."""
    prev_n = (prev or "").upper().strip()
    new_n = (new or "").upper().strip()
    if prev_n == new_n:
        return None
    # Becoming inactive → injured.
    if new_n in _INACTIVE_INJURY_STATUSES and prev_n not in _INACTIVE_INJURY_STATUSES:
        return "injured"
    # Becoming active again → recovered.
    if prev_n in _INACTIVE_INJURY_STATUSES and new_n in _ACTIVE_INJURY_STATUSES:
        return "recovered"
    # Both inactive but the label changed (e.g. DTD → IR) → status change.
    return "injury_status_changed"


def _classify_league_transition(prev: str, new: str) -> Optional[str]:
    """Returns the change_kind for an NHL-vs-AHL movement, or None."""
    prev_n = (prev or "").upper().strip()
    new_n = (new or "").upper().strip()
    if prev_n == new_n:
        return None
    if prev_n == "NHL" and new_n in ("AHL", "MINORS"):
        return "sent_down"
    if prev_n in ("AHL", "MINORS") and new_n == "NHL":
        return "called_up"
    return None


async def apply_player_diff_and_notify(
    db,
    *,
    player_id: str,
    new_fields: Dict,
    create_notification: Optional[Callable[..., Awaitable]] = None,
) -> Dict:
    """Apply an NHL-data-sourced update to a player doc + fan out any
    triggered status-change notifications. Returns a summary dict for
    callers/tests.

    `new_fields` is the incoming patch dict (e.g. {"injury_status": "IR",
    "stats": {...}}). Only the fields that actually differ from current
    state are written, and only `injury_status` / `league_status`
    transitions trigger notifications.
    """
    try:
        oid = ObjectId(player_id)
    except Exception:
        return {"updated": False, "notifications_sent": 0, "reason": "bad_player_id"}

    current = await db.players.find_one({"_id": oid})
    if not current:
        return {"updated": False, "notifications_sent": 0, "reason": "not_found"}

    diff: Dict = {}
    for k, v in new_fields.items():
        if current.get(k) != v:
            diff[k] = v
    if not diff:
        return {"updated": False, "notifications_sent": 0, "reason": "no_change"}

    # Capture transitions BEFORE we persist, so we have prev values.
    transitions = []
    if "injury_status" in diff:
        change_kind = _classify_injury_transition(
            current.get("injury_status", ""),
            diff["injury_status"],
        )
        if change_kind:
            transitions.append((change_kind, diff["injury_status"]))
    if "league_status" in diff:
        change_kind = _classify_league_transition(
            current.get("league_status", ""),
            diff["league_status"],
        )
        if change_kind:
            transitions.append((change_kind, diff["league_status"]))

    await db.players.update_one({"_id": oid}, {"$set": diff})

    total_sent = 0
    for change_kind, new_value in transitions:
        detail = None
        if change_kind in ("injured", "injury_status_changed"):
            detail = f"Status: {new_value}"
        elif change_kind in ("sent_down", "called_up"):
            detail = f"Now playing in {new_value}"
        sent = await notify_player_status_change(
            db,
            player_id=player_id,
            change_kind=change_kind,
            create_notification=create_notification,
            detail_message=detail,
        )
        total_sent += sent

    return {
        "updated": True,
        "diff_keys": list(diff.keys()),
        "transitions": [t[0] for t in transitions],
        "notifications_sent": total_sent,
    }

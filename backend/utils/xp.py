"""Shared XP + level snapshot helper.

Iter 232N.24 — Extracted from routes/users.py so the same formula
powers both the `/users/me/level` endpoint AND the real-time
`xp_awarded` toasts fired when a manager completes a qualifying
action (trade accepted, matchup won, waiver claim won, etc.). Keeps
the two in lockstep — if we retune the XP curve, both surfaces update
together.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

LEVEL_TITLES = [
    (1, 5, "Bench Warmer"),
    (6, 15, "Rink Regular"),
    (16, 30, "Line Captain"),
    (31, 50, "Hat Trick Hero"),
    (51, 75, "Playoff Contender"),
    (76, 999, "Stanley Cup Dynasty"),
]

# XP earned per qualifying action. Keep in sync with the total-XP
# formula in `routes/users.py::get_my_level` so the "+25 XP" toast
# matches what the badge shows after a page refresh.
XP_DELTAS = {
    "trade_accepted": 25,
    "matchup_won": 20,
    "waiver_claim_won": 5,
    "draft_completed": 40,
}


def _title_for_level(level: int) -> str:
    for lo, hi, title in LEVEL_TITLES:
        if lo <= level <= hi:
            return title
    return "Rookie"


def level_from_xp(xp: int) -> dict:
    """Convert raw XP → level snapshot. Mirrors the loop in users.py."""
    xp = max(int(xp), 0)
    level = 1
    xp_remaining = xp
    while True:
        cost = 100 + level * 50
        if xp_remaining < cost:
            break
        xp_remaining -= cost
        level += 1
    xp_required = 100 + level * 50
    return {
        "level": level,
        "title": _title_for_level(level),
        "xp_in_level": xp_remaining,
        "xp_to_next_level": xp_required - xp_remaining,
        "xp_required_for_next": xp_required,
        "progress_pct": round((xp_remaining / xp_required) * 100, 1),
    }


async def compute_user_xp(db, user_id) -> int:
    """Career XP for a user, using the same formula as /users/me/level."""
    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    total_team_count = len(teams)
    total_wins = sum(t.get("wins", 0) or 0 for t in teams)
    total_points_for = sum(t.get("points_for", 0.0) or 0.0 for t in teams)
    total_live_points = sum(t.get("live_points", 0.0) or 0.0 for t in teams)

    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    team_ids = [str(t["_id"]) for t in teams]
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": team_ids},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": team_ids},
    }) if teams else 0

    return int(
        total_team_count * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + (total_points_for + total_live_points) / 5
    )


async def emit_xp_gain(
    db,
    user_id: Any,
    *,
    source: str,
    broadcast_fn: Callable[..., Coroutine[Any, Any, Any]] | None,
    delta: int | None = None,
    meta: dict | None = None,
) -> dict | None:
    """Broadcast a `xp_awarded` websocket event to the `user_{id}` room.

    Best-effort — broadcast failures are swallowed so the caller
    (e.g. trade execution) never regresses because of a toast side
    effect. Returns the emitted payload or None if broadcast_fn
    wasn't provided.
    """
    if broadcast_fn is None or not user_id:
        return None
    amount = int(delta if delta is not None else XP_DELTAS.get(source, 0))
    if amount <= 0:
        return None
    xp = await compute_user_xp(db, user_id)
    snap = level_from_xp(xp)
    payload = {
        "delta": amount,
        "source": source,
        "xp_total": xp,
        "meta": meta or {},
        **snap,
    }
    try:
        await broadcast_fn(f"user_{user_id}", "xp_awarded", payload)
    except Exception:
        return None
    return payload

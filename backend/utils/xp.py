"""Shared level snapshots and idempotent personal-room XP notifications.

Career qualification and historical attribution live in services.profile_career.
The speed-champion notification deliberately does not add cumulative XP.
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

# Notification deltas for the qualifying actions in services.profile_career.
XP_DELTAS = {
    "trade_accepted": 25,
    "matchup_won": 20,
    "waiver_claim_won": 5,
    "draft_completed": 40,
    # Iter 232N.27 — Bonus XP for the manager with the fastest average
    # pick time when a draft completes. NOT baked into the /level
    # formula (it's a one-off flourish rather than a career counter),
    # so `emit_xp_gain(delta=50, source='draft_speed_champion')` writes
    # the toast without ever pushing the user's cumulative XP.
    "draft_speed_champion": 50,
}


def _title_for_level(level: int) -> str:
    for lo, hi, title in LEVEL_TITLES:
        if lo <= level <= hi:
            return title
    return "Rookie"


def level_from_xp(xp: int) -> dict:
    """Convert raw XP to the shared level snapshot."""
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
    """Career XP from the same summary used by both profile endpoints."""
    from services.profile_career import career_summary
    return (await career_summary(db, user_id))["xp_total"]


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
    event_id = (meta or {}).get('trade_id') or (meta or {}).get('draft_id') or (meta or {}).get('claim_id') or (meta or {}).get('matchup_id')
    notification_key = f'{source}:{event_id}:{user_id}' if event_id else None
    if notification_key:
        from pymongo.errors import DuplicateKeyError
        try:
            await db.xp_notifications.insert_one({'_id': notification_key})
        except DuplicateKeyError:
            return None
    try:
        xp = await compute_user_xp(db, user_id)
        snap = level_from_xp(xp)
        payload = {
            "delta": amount,
            "source": source,
            "xp_total": xp,
            "meta": meta or {},
            **snap,
        }
        await broadcast_fn(f"user_{user_id}", "xp_awarded", payload)
    except Exception:
        if notification_key:
            await db.xp_notifications.delete_one({'_id': notification_key})
        return None
    return payload


async def award_draft_completion_bonuses(
    db,
    *,
    draft_id: str,
    broadcast_fn: Callable[..., Coroutine[Any, Any, Any]] | None,
) -> dict:
    """Iter 232N.27 — Called once when a draft flips to `completed`.

    Computes the "speed demon" (fastest average pick time) and hands
    out a +50 XP badge to that team's owner + co-owners. Returns a
    dict describing what was awarded (or {} if no candidate qualifies).

    Best-effort: any exception during aggregation or broadcast is
    swallowed so the draft-complete transition never regresses.
    """
    try:
        from bson import ObjectId
        draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        if not draft:
            return {}
        if draft.get('status') not in ('complete', 'completed'):
            return {}
        from services.profile_career import draft_team_ids, participants_for_teams
        recipients = draft.get('xp_user_ids')
        if recipients is None:
            recipients = await participants_for_teams(db, draft_team_ids(draft))
            await db.drafts.update_one({'_id': draft['_id'], 'xp_user_ids': {'$exists': False}},
                                      {'$set': {'xp_user_ids': recipients}})
        for uid in recipients:
            await emit_xp_gain(db, uid, source='draft_completed', broadcast_fn=broadcast_fn,
                               meta={'draft_id': draft_id})
        picks = draft.get("picks") or []
        # Group pick-time samples by team_id.
        buckets: dict[str, list[int]] = {}
        for p in picks:
            tid = p.get("team_id")
            t = p.get("time_taken_seconds")
            if tid and isinstance(t, (int, float)) and t >= 0:
                buckets.setdefault(tid, []).append(int(t))
        # Require ≥ 3 picks per team so single-pick outliers can't win.
        eligible = {tid: samples for tid, samples in buckets.items() if len(samples) >= 3}
        if not eligible:
            return {}
        # Fastest-average team.
        winner_tid, winner_samples = min(
            eligible.items(), key=lambda kv: sum(kv[1]) / len(kv[1])
        )
        winner_avg = round(sum(winner_samples) / len(winner_samples), 1)
        team = await db.teams.find_one({"_id": ObjectId(winner_tid)})
        if not team:
            return {}
        meta = {
            "draft_id": draft_id,
            "team_id": winner_tid,
            "team_name": team.get("name"),
            "avg_pick_seconds": winner_avg,
            "picks_made": len(winner_samples),
        }
        award = {"winner_team_id": winner_tid, "meta": meta, "recipients": []}
        for uid in [team.get("owner_id")] + list(team.get("co_owner_ids") or []):
            if uid:
                await emit_xp_gain(
                    db, uid,
                    source="draft_speed_champion",
                    broadcast_fn=broadcast_fn,
                    meta=meta,
                )
                award["recipients"].append(str(uid))
        return award
    except Exception:
        return {}

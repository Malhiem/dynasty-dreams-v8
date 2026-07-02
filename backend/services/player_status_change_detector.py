"""Iter 232N.3 — Player status-flag change detector.

Diffs the currently-computed `status_flags` for a set of players
against the last snapshot stored on their document
(`player.last_status_flags`). For every flag that flipped, fans out a
websocket toast to every user who currently rosters that player, and
records a persistent notification so the change survives a page
refresh.

This module deliberately does NOT hook into a specific update
pathway — call `detect_and_emit_status_changes(db, player_ids, ...)`
from any flow that mutates player data (injury sync, roster sync,
manual commissioner edits). An admin-only endpoint at
`/api/players/sync-status-flags` is also exposed for cron / on-demand
sweeps.

Design notes
------------
  • `previously_drafted_pids` is precomputed once per league so the
    diff for a batch of players doesn't fan out N queries.
  • The websocket event `player_status_change` is emitted on the
    per-user room (`user_{owner_id}`) so only the affected manager
    sees the toast — no all-league fanout.
  • The persistent notification uses `create_notification` (already
    part of the app's notification pipeline) so it also lands in
    the inbox and drives the badge count.
  • Only flag *flips* (false → true) emit events — clearing a flag
    (true → false) also emits so managers know when a player is
    healthy / signed / recalled.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from bson import ObjectId

from routes.player_status import (
    compute_player_status_flags,
    get_previously_drafted_pids,
)


_FLAG_META = {
    "injured": {
        "on_title": "Injury: {name}",
        "on_msg": "{name} moved to IR/LTIR — lineup slot may need attention.",
        "off_title": "Cleared: {name}",
        "off_msg": "{name} activated from injury reserve.",
    },
    "in_minors": {
        "on_title": "Sent down: {name}",
        "on_msg": "{name} is playing in the minors (AHL/ECHL).",
        "off_title": "Called up: {name}",
        "off_msg": "{name} recalled from the minors.",
    },
    "unsigned": {
        "on_title": "Contract lapsed: {name}",
        "on_msg": "{name} is currently unsigned.",
        "off_title": "Signed: {name}",
        "off_msg": "{name} has an active NHL contract.",
    },
    # `undrafted` intentionally omitted — it's a league-scoped
    # bookkeeping flag, not a player-development milestone.
}


async def _owners_for_player(db, player_id: str) -> list[tuple[str, str]]:
    """Return [(owner_user_id, league_id), ...] for every fantasy team
    that currently rosters the given player. Owners are deduplicated."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    async for team in db.teams.find(
        {"roster": player_id}, {"owner_id": 1, "co_owner_ids": 1, "league_id": 1},
    ):
        league_id = str(team.get("league_id") or "")
        for oid in [team.get("owner_id")] + list(team.get("co_owner_ids") or []):
            if not oid:
                continue
            key = (str(oid), league_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


async def detect_and_emit_status_changes(
    db,
    player_ids: Iterable[str],
    broadcast_fn: Optional[Callable] = None,
    create_notification_fn: Optional[Callable] = None,
    league_id_for_undrafted: Optional[str] = None,
) -> dict:
    """Diff the current status_flags for each player in `player_ids`
    against the snapshot stored on the document; emit toasts +
    notifications for every flip.

    Returns a summary dict `{"scanned": N, "changed": M, "events": [...]}`
    that callers (or tests) can inspect.
    """
    previously_drafted_pids: set = set()
    if league_id_for_undrafted:
        previously_drafted_pids = await get_previously_drafted_pids(
            db, league_id_for_undrafted,
        )

    events: list[dict] = []
    scanned = 0
    changed = 0

    for pid in player_ids:
        try:
            oid = ObjectId(pid)
        except Exception:
            continue
        player = await db.players.find_one({"_id": oid})
        if not player:
            continue
        scanned += 1

        current = compute_player_status_flags(
            player, previously_drafted_pids if league_id_for_undrafted else None,
        )
        prev = player.get("last_status_flags") or {}
        # Diff each flag except `undrafted` (not a milestone).
        flipped: dict[str, tuple[bool, bool]] = {}
        for key in _FLAG_META.keys():
            was = bool(prev.get(key, False))
            now = bool(current.get(key, False))
            if was != now:
                flipped[key] = (was, now)

        # Always store the current snapshot so a first-run sweep
        # doesn't spam every owner with legacy flags.
        first_run = not player.get("last_status_flags")
        await db.players.update_one(
            {"_id": oid}, {"$set": {"last_status_flags": current}},
        )
        if not flipped or first_run:
            continue
        changed += 1

        owners = await _owners_for_player(db, str(oid))
        for flag, (_was, now) in flipped.items():
            meta = _FLAG_META[flag]
            template = "on" if now else "off"
            title = meta[f"{template}_title"].format(name=player.get("name", "Player"))
            message = meta[f"{template}_msg"].format(name=player.get("name", "Player"))
            payload = {
                "player_id": str(oid),
                "player_name": player.get("name"),
                "flag": flag,
                "value": bool(now),
                "title": title,
                "message": message,
            }
            events.append(payload)

            for owner_id, league_id in owners:
                if broadcast_fn:
                    try:
                        await broadcast_fn(
                            f"user_{owner_id}",
                            "player_status_change",
                            {**payload, "league_id": league_id},
                        )
                    except Exception:
                        pass
                if create_notification_fn:
                    try:
                        await create_notification_fn(
                            user_id=owner_id,
                            notif_type="player_status_change",
                            title=title,
                            message=message,
                            league_id=league_id or None,
                            link=f"/players/{oid}",
                            reason={
                                "flag": flag,
                                "value": bool(now),
                                # Iter 232N.5 — Player identity in the
                                # reason blob so the grouped-by-player
                                # feed can render without a JOIN.
                                "player_id": str(oid),
                                "player_name": player.get("name"),
                            },
                        )
                    except Exception:
                        pass

    return {"scanned": scanned, "changed": changed, "events": events}

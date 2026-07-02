"""Iter 232N.2 — Shared helpers for player `status_flags`.

Consolidates the rules used to compute `{injured, in_minors, unsigned,
undrafted}` so every consumer (draft eligible-players, Players page,
Waivers page, Roster page, Trade Block cards) emits the same shape
without duplicating the logic.

Design notes:
  • `compute_player_status_flags(player, previously_drafted_pids)` is
    purely functional — pass a player dict and (optionally) the set of
    player-ids that have been drafted in this league before. The
    `undrafted` flag is only stamped when the caller passes a real set
    (guarded on `previously_drafted_pids is not None`) so an
    off-league query doesn't misleadingly flag every player as
    undrafted.
  • `get_previously_drafted_pids(db, league_id, exclude_draft_id=None)`
    returns the set the frontend needs the flag computed against.
    Cheap async iterator over `drafts.picks[]` for the given league.
"""
from __future__ import annotations

from typing import Optional

from bson import ObjectId


async def get_previously_drafted_pids(
    db,
    league_id: str,
    exclude_draft_id: Optional[ObjectId] = None,
) -> set[str]:
    """Return the set of player_ids drafted in ANY prior draft in this
    league. When `exclude_draft_id` is provided (e.g. the current
    active draft), that draft is excluded from the union so the
    current draft's own picks aren't counted as "previously drafted".
    """
    if not league_id:
        return set()
    query: dict = {
        "league_id": league_id,
        "status": {"$in": ["scheduled", "active", "completed"]},
    }
    if exclude_draft_id is not None:
        query["_id"] = {"$ne": exclude_draft_id}
    out: set[str] = set()
    try:
        async for past in db.drafts.find(query, {"picks": 1}):
            for p in past.get("picks") or []:
                pid = p.get("player_id")
                if pid:
                    out.add(str(pid))
    except Exception:
        return set()
    return out


def compute_player_status_flags(
    player: dict,
    previously_drafted_pids: Optional[set[str]] = None,
) -> dict:
    """Compute the four status flags for a single player dict.

    `previously_drafted_pids` is required to stamp `undrafted` — when
    omitted the flag is False by default (safer than misleading True).
    """
    player_type = (player.get("player_type") or "skater")
    is_prospect = player_type == "prospect"
    roster_status = (player.get("roster_status") or "").lower()
    injury_status = (player.get("injury_status") or "").lower()
    amateur = (player.get("amateur_league") or "").upper()

    injured = bool(
        roster_status in ("ir", "ltir")
        or (injury_status and injury_status not in ("healthy", "active", ""))
    )
    in_minors = bool(
        roster_status == "minors"
        or (is_prospect and amateur in ("AHL", "ECHL"))
    )
    # `unsigned` is authoritative only for prospects — NHL players under
    # contract are never unsigned in this dataset.
    unsigned = bool(is_prospect and (player.get("signed") is False))

    undrafted = False
    if previously_drafted_pids is not None:
        pid_str = str(player.get("_id") or player.get("id") or player.get("player_id") or "")
        if pid_str:
            undrafted = pid_str not in previously_drafted_pids

    return {
        "injured": injured,
        "in_minors": in_minors,
        "unsigned": unsigned,
        "undrafted": undrafted,
    }

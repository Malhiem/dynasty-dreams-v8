"""Iter 230 — Player status change notifier.

Single entry-point for notifying fantasy team owners (and co-owners) when
a real-world player they roster has a status change: injury, recovery,
demotion to minors, NHL call-up, or a non-injury status update (e.g.
DTD → Day-to-Day's expected return date shifted).

Usage:
  from services.player_status_notifier import notify_player_status_change
  await notify_player_status_change(
      db,
      player_id=str(player["_id"]),
      change_kind="injured" | "recovered" | "sent_down" | "called_up"
                 | "injury_status_changed",
      create_notification=create_notification_fn,  # injected from server.py deps
      detail_message="ACL surgery — out 6-8 months",  # optional human-readable
  )

Used by:
  • routes/admin.py — admin-triggered status updates
  • Future: services/fetch_nhl_news.py — automated NHL data sync
"""
from typing import Awaitable, Callable, Optional

from bson import ObjectId

from routes.notification_events import (
    EVT_PLAYER_INJURED,
    EVT_PLAYER_RECOVERED,
    EVT_PLAYER_SENT_DOWN,
    EVT_PLAYER_CALLED_UP,
    EVT_PLAYER_INJURY_STATUS,
)


_CHANGE_KIND_TO_EVENT = {
    "injured": EVT_PLAYER_INJURED,
    "recovered": EVT_PLAYER_RECOVERED,
    "sent_down": EVT_PLAYER_SENT_DOWN,
    "called_up": EVT_PLAYER_CALLED_UP,
    "injury_status_changed": EVT_PLAYER_INJURY_STATUS,
}

_CHANGE_KIND_TO_TITLE = {
    "injured": "Player injured",
    "recovered": "Player recovered",
    "sent_down": "Player sent down to minors",
    "called_up": "Player called up from minors",
    "injury_status_changed": "Player injury status changed",
}


async def notify_player_status_change(
    db,
    *,
    player_id: str,
    change_kind: str,
    create_notification: Optional[Callable[..., Awaitable]] = None,
    detail_message: Optional[str] = None,
) -> int:
    """Fan out a per-event notification to every team that currently
    rosters this player. Returns the number of notifications emitted.

    No-ops silently if `create_notification` is None or the change_kind
    isn't recognised — keeps callers safe from import-cycle pitfalls.
    """
    if create_notification is None or change_kind not in _CHANGE_KIND_TO_EVENT:
        return 0

    try:
        player = await db.players.find_one({"_id": ObjectId(player_id)})
    except Exception:
        return 0
    if not player:
        return 0

    player_name = player.get("name") or "A player"
    event_id = _CHANGE_KIND_TO_EVENT[change_kind]
    title = _CHANGE_KIND_TO_TITLE[change_kind]
    body = detail_message or f"{player_name} — status changed"

    # Find all teams that have this player on their roster.
    teams = await db.teams.find(
        {"roster": player_id},
        {"_id": 1, "league_id": 1, "owner_id": 1, "co_owner_ids": 1, "name": 1},
    ).to_list(500)

    sent = 0
    for team in teams:
        league_id = team.get("league_id")
        recipients: set = set()
        if team.get("owner_id"):
            recipients.add(team["owner_id"])
        for co in (team.get("co_owner_ids") or []):
            if co:
                recipients.add(co)
        team_body = f"{player_name} — {body}" if detail_message else f"{player_name} on {team.get('name', 'your team')}"
        for uid in recipients:
            try:
                await create_notification(
                    uid,
                    event_id,
                    title,
                    team_body,
                    league_id,
                    f"/players/{player_id}",
                )
                sent += 1
            except Exception:
                pass

    return sent

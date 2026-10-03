"""Shared league-access guards.

`require_league_member(db, user, league_id)` — ensures the caller
is authenticated AND is a member (commissioner, co-commissioner, or
team owner) of the specified league.  Returns the league document.

`verify_team_in_league(db, team_id, league_id)` — ensures the given
team actually belongs to the specified league.  Returns the team doc.

Both raise HTTPException on failure.
"""

from bson import ObjectId
from fastapi import HTTPException

__all__ = ["require_league_member", "verify_team_in_league"]


async def require_league_member(db, user: dict, league_id: str) -> dict:
    """Raise 403 unless *user* is a member of *league_id*.

    A user counts as a member if they are:
      - the commissioner
      - a co-commissioner
      - a platform admin (is_admin flag)
      - owner of at least one active team in the league

    Returns the league document on success.
    """
    try:
        oid = ObjectId(league_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league ID")

    league = await db.leagues.find_one({"_id": oid})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    uid = user["_id"]
    uid_str = str(uid)

    # Platform admins always pass
    if user.get("is_admin") or user.get("role") == "admin" or "admin" in (user.get("roles") or []):
        return league

    # Commissioner / co-commissioner (handle mixed ObjectId / str types)
    comm_id = league.get("commissioner_id")
    if comm_id is not None and str(comm_id) == uid_str:
        return league
    co_comms = (league.get("co_commissioners") or []) + (league.get("admin_ids") or [])
    if any(str(c) == uid_str for c in co_comms):
        return league

    # Team owner inside this league (check both ObjectId and str owner_id)
    team = await db.teams.find_one(
        {"league_id": league_id, "$or": [{"owner_id": uid}, {"owner_id": uid_str}, {"co_owner_ids": uid}, {"co_owner_ids": uid_str}]},
        {"_id": 1},
    )
    if team:
        return league

    raise HTTPException(status_code=403, detail="Not a member of this league")


async def verify_team_in_league(db, team_id: str, league_id: str) -> dict:
    """Raise 404 unless *team_id* belongs to *league_id*.

    Returns the team document on success.
    """
    try:
        tid = ObjectId(team_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid team ID")

    team = await db.teams.find_one({"_id": tid})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if team.get("league_id") != league_id:
        raise HTTPException(
            status_code=404,
            detail="Team does not belong to the specified league",
        )

    return team

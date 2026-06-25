"""Per-team slot-locked invite tokens.

Iter 228y — Distinct from `league_invites.py` which issues a league-wide
`invite_code` for public discovery / bulk owner emails. This module
instead mints a **single-use, slot-locked token** so a commissioner can:

  • Lock a specific team to a specific email (private league flow).
  • Mint an "anyone can claim" link for a single team slot.
  • Add a co-owner to a team that already has a primary owner.

Endpoints:
  - POST   /api/leagues/{league_id}/teams/{team_id}/invites
  - GET    /api/team-invites/{token}/preview          (public, no auth)
  - POST   /api/team-invites/{token}/accept           (auth required)
  - DELETE /api/team-invites/{invite_id}              (commissioner)
  - GET    /api/leagues/{league_id}/team-invites      (commissioner)

Co-owner semantics:
  - `role="owner"` → claim a vacant team slot. Rejected if team already
    has `owner_id`.
  - `role="co_owner"` → append the accepting user to `co_owner_ids`.
    Rejected if the team has no primary owner yet, or if the user is
    already attached to the team in any capacity.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator


router = APIRouter()
_deps: dict = {}

DEFAULT_EXPIRES_DAYS = 14
MAX_EXPIRES_DAYS = 60


def setup(deps: dict) -> None:
    _deps.update(deps)


def _frontend_base() -> str:
    return os.environ.get(
        "FRONTEND_URL",
        "https://dynasty-preview.preview.emergentagent.com",
    )


# ─── Models ──────────────────────────────────────────────────


class TeamInviteCreate(BaseModel):
    email: Optional[str] = None  # case-insensitive; locks the invite to this address when set
    role: str = "owner"  # "owner" | "co_owner"
    expires_in_days: int = DEFAULT_EXPIRES_DAYS

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in ("owner", "co_owner"):
            raise ValueError("role must be 'owner' or 'co_owner'")
        return v

    @field_validator("expires_in_days")
    @classmethod
    def _check_expiry(cls, v: int) -> int:
        if v < 1 or v > MAX_EXPIRES_DAYS:
            raise ValueError(f"expires_in_days must be 1..{MAX_EXPIRES_DAYS}")
        return v


class TeamInviteResponse(BaseModel):
    id: str
    token: str
    invite_url: str
    league_id: str
    team_id: str
    team_name: Optional[str]
    league_name: Optional[str]
    email: Optional[str]
    role: str
    status: str  # "pending" | "accepted" | "revoked" | "expired"
    created_at: datetime
    expires_at: datetime
    used_at: Optional[datetime] = None
    used_by_user_id: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────


def _is_commish(league: dict, user: dict) -> bool:
    return league.get("commissioner_id") == user["_id"] or user["_id"] in (
        league.get("co_commissioners") or []
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invite_status(inv: dict) -> str:
    if inv.get("revoked_at"):
        return "revoked"
    if inv.get("used_at"):
        return "accepted"
    exp = inv.get("expires_at")
    if isinstance(exp, datetime):
        # Treat naive datetimes (from older docs) as UTC for the comparison.
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            return "expired"
    return "pending"


def _to_response(inv: dict, *, team_name: Optional[str], league_name: Optional[str]) -> TeamInviteResponse:
    return TeamInviteResponse(
        id=str(inv["_id"]),
        token=inv["token"],
        invite_url=f"{_frontend_base()}/team-invites/{inv['token']}",
        league_id=inv["league_id"],
        team_id=inv["team_id"],
        team_name=team_name,
        league_name=league_name,
        email=inv.get("email"),
        role=inv.get("role", "owner"),
        status=_invite_status(inv),
        created_at=inv["created_at"],
        expires_at=inv["expires_at"],
        used_at=inv.get("used_at"),
        used_by_user_id=inv.get("used_by_user_id"),
    )


# ─── Endpoints ───────────────────────────────────────────────


@router.post("/leagues/{league_id}/teams/{team_id}/invites")
async def create_team_invite(
    league_id: str,
    team_id: str,
    payload: TeamInviteCreate,
    request: Request,
):
    """Commissioner mints a slot-locked invite token for a specific team."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")
    team = await db.teams.find_one({
        "_id": _safe_object_id(team_id, "team_id"),
        "league_id": league_id,
    })
    if not team:
        raise HTTPException(status_code=404, detail="Team not found in league")

    role = payload.role
    if role == "owner" and team.get("owner_id"):
        raise HTTPException(
            status_code=400,
            detail="Team already has an owner. Mint a co_owner invite instead.",
        )
    if role == "co_owner" and not team.get("owner_id"):
        raise HTTPException(
            status_code=400,
            detail="Team has no primary owner yet. Mint an owner invite first.",
        )

    now = _now()
    expires_at = now + timedelta(days=payload.expires_in_days)
    email = (payload.email or "").strip().lower() or None

    doc = {
        "token": secrets.token_urlsafe(16),
        "league_id": league_id,
        "team_id": team_id,
        "email": email,
        "role": role,
        "created_by": user["_id"],
        "created_at": now,
        "expires_at": expires_at,
        "used_at": None,
        "used_by_user_id": None,
        "revoked_at": None,
    }
    res = await db.team_invites.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_response(doc, team_name=team.get("name"), league_name=league.get("name"))


@router.get("/team-invites/{token}/preview")
async def preview_team_invite(token: str):
    """Public lookup of an invite token. Returns minimal metadata so the
    `/team-invites/{token}` landing page can render before login.
    """
    db = _deps["db"]
    inv = await db.team_invites.find_one({"token": token})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")
    status = _invite_status(inv)
    team = None
    league = None
    try:
        team = await db.teams.find_one({"_id": ObjectId(inv["team_id"])})
    except Exception:
        team = None
    try:
        league = await db.leagues.find_one({"_id": ObjectId(inv["league_id"])})
    except Exception:
        league = None
    return {
        "token": token,
        "status": status,
        "team_id": inv["team_id"],
        "team_name": (team or {}).get("name"),
        "league_id": inv["league_id"],
        "league_name": (league or {}).get("name"),
        "email_lock": inv.get("email"),
        "role": inv.get("role", "owner"),
        "expires_at": inv["expires_at"],
    }


@router.post("/team-invites/{token}/accept")
async def accept_team_invite(token: str, request: Request):
    """Authenticated user redeems a slot-locked invite.

    - role=owner → user becomes the primary owner of the team.
    - role=co_owner → user is appended to team.co_owner_ids.
    Both paths broadcast `team_membership_changed` on `league_{id}`.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    broadcast_to_room = _deps["broadcast_to_room"]
    log_activity = _deps.get("log_activity")

    user = await get_current_user(request)
    inv = await db.team_invites.find_one({"token": token})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")

    status = _invite_status(inv)
    if status != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is {status}")

    locked_email = (inv.get("email") or "").lower()
    user_email = (user.get("email") or "").lower()
    if locked_email and user_email != locked_email:
        raise HTTPException(
            status_code=403,
            detail=f"This invite is locked to {locked_email}. Sign in with that account to accept.",
        )

    try:
        team = await db.teams.find_one({"_id": ObjectId(inv["team_id"])})
    except Exception:
        team = None
    if not team:
        raise HTTPException(status_code=404, detail="Team no longer exists")

    role = inv.get("role", "owner")
    existing_co = list(team.get("co_owner_ids") or [])

    if role == "owner":
        if team.get("owner_id") and team["owner_id"] != user["_id"]:
            raise HTTPException(
                status_code=400,
                detail="Team already has an owner",
            )
        if user["_id"] in existing_co:
            # Promote co-owner → owner. Strip them from the co_owner list.
            existing_co = [u for u in existing_co if u != user["_id"]]
        update = {
            "owner_id": user["_id"],
            "owner_name": user.get("name") or user.get("email"),
            "co_owner_ids": existing_co,
            "is_pending": False,
        }
        await db.teams.update_one({"_id": team["_id"]}, {"$set": update})
        # Bump league.current_teams when this slot was previously vacant.
        if not team.get("owner_id"):
            await db.leagues.update_one(
                {"_id": ObjectId(inv["league_id"])},
                {"$inc": {"current_teams": 1}},
            )
    else:  # co_owner
        if not team.get("owner_id"):
            raise HTTPException(
                status_code=400,
                detail="Team has no primary owner; cannot add a co-owner",
            )
        if team["owner_id"] == user["_id"]:
            raise HTTPException(
                status_code=400,
                detail="You're already the primary owner of this team",
            )
        if user["_id"] in existing_co:
            raise HTTPException(
                status_code=400,
                detail="You're already a co-owner of this team",
            )
        existing_co.append(user["_id"])
        await db.teams.update_one(
            {"_id": team["_id"]},
            {"$set": {"co_owner_ids": existing_co}},
        )

    now = _now()
    await db.team_invites.update_one(
        {"_id": inv["_id"]},
        {"$set": {"used_at": now, "used_by_user_id": user["_id"]}},
    )

    try:
        await broadcast_to_room(
            f"league_{inv['league_id']}",
            "team_membership_changed",
            {
                "team_id": inv["team_id"],
                "role": role,
                "user_id": user["_id"],
            },
        )
        # Iter 229f — Also broadcast to the affected user's personal
        # room so their global sidebar dropdown can self-refresh even
        # if they're not actively viewing this league.
        await broadcast_to_room(
            f"user_{user['_id']}",
            "team_membership_changed",
            {
                "team_id": inv["team_id"],
                "league_id": inv["league_id"],
                "role": role,
                "user_id": user["_id"],
            },
        )
    except Exception:
        pass

    if log_activity:
        try:
            label = "joined as co-owner" if role == "co_owner" else "claimed"
            await log_activity(
                inv["league_id"],
                "team_invite_accepted",
                f"{user.get('name') or user.get('email')} {label} {team.get('name')}",
                user["_id"],
            )
        except Exception:
            pass

    return {
        "team_id": inv["team_id"],
        "team_name": team.get("name"),
        "league_id": inv["league_id"],
        "role": role,
        "co_owner_ids": existing_co,
    }


@router.delete("/team-invites/{invite_id}")
async def revoke_team_invite(invite_id: str, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    inv = await db.team_invites.find_one({"_id": _safe_object_id(invite_id, "invite_id")})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")
    league = await db.leagues.find_one({"_id": ObjectId(inv["league_id"])})
    if not league or not _is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")
    if inv.get("used_at"):
        raise HTTPException(status_code=400, detail="Invite already accepted")
    await db.team_invites.update_one(
        {"_id": inv["_id"]},
        {"$set": {"revoked_at": _now()}},
    )
    return {"id": invite_id, "status": "revoked"}


@router.get("/leagues/{league_id}/team-invites")
async def list_league_team_invites(
    league_id: str,
    request: Request,
    team_id: Optional[str] = None,
    include_used: bool = False,
):
    """Commissioner-only roll-up of all slot invites in the league.

    Useful for the Commissioner → Owner Invites page so each team row can
    show its outstanding tokens with revoke / copy-link controls.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _is_commish(league, user):
        raise HTTPException(status_code=403, detail="Commissioner access required")

    query: dict = {"league_id": league_id}
    if team_id:
        query["team_id"] = team_id
    invites = await db.team_invites.find(query).sort("created_at", -1).to_list(500)
    team_ids = list({i["team_id"] for i in invites})
    teams_by_id: dict = {}
    for tid in team_ids:
        try:
            t = await db.teams.find_one({"_id": ObjectId(tid)})
            if t:
                teams_by_id[tid] = t
        except Exception:
            continue

    out: List[dict] = []
    for inv in invites:
        status = _invite_status(inv)
        if not include_used and status == "accepted":
            continue
        t = teams_by_id.get(inv["team_id"]) or {}
        out.append(_to_response(
            inv,
            team_name=t.get("name"),
            league_name=league.get("name"),
        ).model_dump())
    return {"league_id": league_id, "invites": out, "count": len(out)}

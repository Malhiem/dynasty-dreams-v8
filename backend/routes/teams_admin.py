"""Iter 231ah — Admin endpoints for prospect pool + teams continuity.

Routes:
    POST /api/admin/prospects/backfill — Pull the last 6 NHL draft
        classes (2020-2025) from the NHL public API and upsert into
        the `players` collection. Idempotent.
    GET  /api/admin/prospects/stats    — Read-only counts of the
        current prospect pool by draft year + seed source.
    POST /api/leagues/{lid}/teams/{tid}/admin-managed  — Toggle the
        team-runs-with-admin continuity flag (moved here from
        `team_invites.py` in iter231ah for proper module separation).

Auth: shared `is_league_admin` for the per-league endpoint; platform
admin for the prospect endpoints.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from bson import ObjectId

from routes._authz import is_league_admin
from services.prospect_backfill import (
    DEFAULT_YEARS,
    backfill_prospects,
    get_pool_stats,
)

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _is_platform_admin(user: dict) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    return user.get("email") == admin_email


# ─── Prospects ────────────────────────────────────────────────────


class BackfillRequest(BaseModel):
    years: Optional[list[int]] = Field(
        default=None,
        description="Optional list of NHL draft years (e.g. [2020, 2021]). Defaults to the last 6 (2020-2025).",
    )


@router.post("/admin/prospects/backfill")
async def backfill_prospect_pool(payload: BackfillRequest, request: Request):
    """Pull the last 6 NHL draft classes into the `players` collection.

    Platform-admin only. Idempotent — re-running just refreshes the
    upsert. Writes an audit row to `admin_user_actions`.
    """
    user = await _get_user(request)
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform admin only")

    years = tuple(payload.years) if payload.years else DEFAULT_YEARS
    result = await backfill_prospects(_db(), years=years)

    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "platform",
        "action": "prospect_pool_backfill",
        "reason": f"Platform admin backfilled NHL draft years {list(years)}.",
        "metadata": result,
        "mocked": False,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    return result


@router.get("/admin/prospects/stats")
async def prospect_pool_stats(request: Request):
    """Read-only prospect-pool counts. Platform admin only."""
    user = await _get_user(request)
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform admin only")
    return await get_pool_stats(_db())


# ─── Admin-managed team toggle (moved from team_invites.py) ────────


class AdminManagedToggleRequest(BaseModel):
    enabled: bool = Field(..., description="Set True to have league admin manage this team; False to clear.")


@router.post("/leagues/{league_id}/teams/{team_id}/admin-managed")
async def set_team_admin_managed(
    league_id: str,
    team_id: str,
    payload: AdminManagedToggleRequest,
    request: Request,
):
    """Iter 231ae (moved here in iter231ah) — Toggle the `admin_managed`
    flag on a team. Used for owner-removal continuity.

    Auth: shared `is_league_admin` helper.
    """
    user = await _get_user(request)
    league = await _db().leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not is_league_admin(user, league):
        raise HTTPException(status_code=403, detail="Commissioner / co-commissioner / admin only")

    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("league_id") != league_id:
        raise HTTPException(status_code=400, detail="Team does not belong to this league")

    prior = bool(team.get("admin_managed", False))
    now_iso = datetime.now(timezone.utc).isoformat()
    update: dict = {
        "admin_managed": payload.enabled,
        "admin_managed_at": now_iso if payload.enabled else None,
        "admin_managed_by": str(user["_id"]),
    }
    await _db().teams.update_one({"_id": ObjectId(team_id)}, {"$set": update})

    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "commissioner",
        "target_user_id": team.get("owner_id"),
        "action": "team_admin_managed_toggle",
        "reason": (
            f"League admin {'enabled' if payload.enabled else 'disabled'} "
            f"manual management of team {team.get('name') or team_id}."
        ),
        "metadata": {
            "league_id": league_id,
            "league_name": league.get("name"),
            "team_id": team_id,
            "team_name": team.get("name"),
            "enabled": payload.enabled,
            "prior": prior,
        },
        "mocked": False,
        "ts": now_iso,
    })

    return {
        "team_id": team_id,
        "admin_managed": payload.enabled,
        "prior": prior,
        "updated_at": now_iso,
    }

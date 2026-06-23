"""
Iter 217 — Versioned roster snapshots.

Backs the iter 215 `reset_team` admin action with real rollback
capability. Snapshots can be taken automatically (on key events like
trade execution / waiver claim / draft completion) or manually by
the commissioner / admin.

Collection: `roster_snapshots`
  { team_id, league_id, owner_id, taken_at, taken_by, reason,
    roster, lineup, ir, taxi, salary_cap, faab_remaining,
    metadata }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Query

router = APIRouter(tags=["roster-snapshots"])
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


async def _require_user(request: Request) -> dict:
    user = await _deps["get_current_user"](request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def _load_team(team_id: str) -> dict:
    try:
        t = await _db().teams.find_one({"_id": ObjectId(team_id)})
    except Exception:
        t = None
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return t


async def _gate_team_access(user: dict, team: dict, require_admin_or_commish: bool = True) -> None:
    """Owner can READ their own snapshots; commish + admin can read AND
    write/restore. Pass `require_admin_or_commish=False` for read."""
    uid = str(user["_id"])
    is_admin = user.get("role") == "admin"
    is_owner = team.get("owner_id") == uid
    lg = await _db().leagues.find_one({"_id": ObjectId(team["league_id"])}) if team.get("league_id") else None
    is_commish = lg and (str(lg.get("commissioner_id")) == uid or uid in (lg.get("co_commissioners") or []))
    if is_admin or is_commish:
        return
    if not require_admin_or_commish and is_owner:
        return
    raise HTTPException(status_code=403, detail="Commissioner or admin access required")


# Helper to snapshot any team — callable from other routes too
async def take_snapshot(db, team: dict, *, taken_by: str, reason: str = "manual",
                        metadata: Optional[dict] = None) -> str:
    snap = {
        "team_id": str(team["_id"]),
        "league_id": team.get("league_id"),
        "owner_id": team.get("owner_id"),
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "taken_by": taken_by,
        "reason": reason,
        "roster": team.get("roster") or [],
        "lineup": team.get("lineup") or {},
        "ir": team.get("ir") or [],
        "taxi": team.get("taxi") or [],
        "salary_cap_used_cents": team.get("salary_cap_used_cents"),
        "faab_remaining": team.get("faab_remaining"),
        "metadata": metadata or {},
    }
    res = await db.roster_snapshots.insert_one(snap)
    return str(res.inserted_id)


@router.post("/teams/{team_id}/snapshots")
async def create_snapshot(team_id: str, request: Request):
    """Body: { reason?: str, metadata?: dict }. Manual snapshot."""
    user = await _require_user(request)
    team = await _load_team(team_id)
    await _gate_team_access(user, team)
    payload = await request.json() if request.headers.get("content-length") else {}
    sid = await take_snapshot(
        _db(), team,
        taken_by=user.get("email") or str(user["_id"]),
        reason=(payload.get("reason") or "manual"),
        metadata=payload.get("metadata"),
    )
    return {"ok": True, "snapshot_id": sid}


@router.get("/teams/{team_id}/snapshots")
async def list_snapshots(team_id: str, request: Request, limit: int = Query(50, ge=1, le=200)):
    user = await _require_user(request)
    team = await _load_team(team_id)
    await _gate_team_access(user, team, require_admin_or_commish=False)
    rows = await _db().roster_snapshots.find({"team_id": team_id}).sort(
        "taken_at", -1
    ).limit(limit).to_list(limit)
    return {
        "snapshots": [{
            "id": str(s["_id"]),
            "taken_at": _iso(s.get("taken_at")),
            "taken_by": s.get("taken_by"),
            "reason": s.get("reason"),
            "roster_size": len(s.get("roster") or []),
            "metadata": s.get("metadata"),
        } for s in rows],
    }


@router.get("/teams/{team_id}/snapshots/{snap_id}")
async def get_snapshot(team_id: str, snap_id: str, request: Request):
    user = await _require_user(request)
    team = await _load_team(team_id)
    await _gate_team_access(user, team, require_admin_or_commish=False)
    try:
        s = await _db().roster_snapshots.find_one({"_id": ObjectId(snap_id), "team_id": team_id})
    except Exception:
        s = None
    if not s:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {
        "id": str(s["_id"]),
        "team_id": s.get("team_id"),
        "league_id": s.get("league_id"),
        "owner_id": s.get("owner_id"),
        "taken_at": _iso(s.get("taken_at")),
        "taken_by": s.get("taken_by"),
        "reason": s.get("reason"),
        "roster": s.get("roster") or [],
        "lineup": s.get("lineup") or {},
        "ir": s.get("ir") or [],
        "taxi": s.get("taxi") or [],
        "salary_cap_used_cents": s.get("salary_cap_used_cents"),
        "faab_remaining": s.get("faab_remaining"),
        "metadata": s.get("metadata"),
    }


@router.post("/teams/{team_id}/snapshots/{snap_id}/restore")
async def restore_snapshot(team_id: str, snap_id: str, request: Request):
    """Restore the team's roster + lineup + IR + taxi + cap + FAAB to
    the values captured in the snapshot. Takes an automatic
    pre-restore snapshot so this restore is itself reversible."""
    user = await _require_user(request)
    team = await _load_team(team_id)
    await _gate_team_access(user, team)
    try:
        s = await _db().roster_snapshots.find_one({"_id": ObjectId(snap_id), "team_id": team_id})
    except Exception:
        s = None
    if not s:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    # Pre-restore safety snapshot
    pre_sid = await take_snapshot(
        _db(), team,
        taken_by=user.get("email") or str(user["_id"]),
        reason=f"pre_restore_of_{snap_id}",
        metadata={"restore_target_snapshot": snap_id},
    )
    await _db().teams.update_one(
        {"_id": team["_id"]},
        {"$set": {
            "roster": s.get("roster") or [],
            "lineup": s.get("lineup") or {},
            "ir": s.get("ir") or [],
            "taxi": s.get("taxi") or [],
            "salary_cap_used_cents": s.get("salary_cap_used_cents"),
            "faab_remaining": s.get("faab_remaining"),
            "last_restored_from": snap_id,
            "last_restored_at": datetime.now(timezone.utc).isoformat(),
            "last_restored_by": user.get("email"),
        }},
    )
    return {"ok": True, "restored_from_snapshot": snap_id,
            "pre_restore_snapshot_id": pre_sid}

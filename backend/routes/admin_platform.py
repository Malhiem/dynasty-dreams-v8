"""
Iter 201a — Platform Admin Dashboard backend.

Provides aggregate metrics + cross-league commissioner action log for
platform admins (users with `role == 'admin'`). Distinct from the
per-league `ops_console` which serves league commissioners only.

Endpoints
─────────
GET  /api/admin/platform/metrics          — counts + timeseries
GET  /api/admin/platform/commish-actions  — cross-league audit feed
POST /api/admin/platform/commish-actions/{id}/revert — undo a commish action
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/admin/platform", tags=["admin-platform"])

_deps: dict = {}


def setup(db, get_current_user):
    """Wire shared dependencies (mirror of other route modules)."""
    _deps["db"] = db
    _deps["get_current_user"] = get_current_user


async def _require_admin(request: Request) -> dict:
    user = await _deps["get_current_user"](request)
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def _iso(dt) -> str | None:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


# ─────────────────────────────────────────────────────────────────────
# 1. Platform Metrics — high-level counts + 14-day timeseries
# ─────────────────────────────────────────────────────────────────────
@router.get("/metrics")
async def platform_metrics(request: Request):
    """Return a dashboard payload with:
      * counts: users, leagues, teams, trades, drafts (all-time + this week)
      * timeseries: 14-day daily signups + new leagues
      * activity: trades_this_week, transactions_this_week, active_drafts
    """
    await _require_admin(request)
    db = _deps["db"]

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    fourteen_ago = now - timedelta(days=14)

    # ── Counts ──
    users_total = await db.users.count_documents({})
    leagues_total = await db.leagues.count_documents({})
    teams_total = await db.teams.count_documents({})
    trades_total = await db.trades.count_documents({})
    drafts_total = await db.drafts.count_documents({})

    # ── This-week deltas (created_at is stored as ISO string in this project) ──
    week_ago_iso = week_ago.isoformat()
    users_week = await db.users.count_documents({"created_at": {"$gte": week_ago_iso}})
    leagues_week = await db.leagues.count_documents({"created_at": {"$gte": week_ago_iso}})
    trades_week = await db.trades.count_documents({"created_at": {"$gte": week_ago_iso}})
    transactions_week = await db.activity_feed.count_documents({"created_at": {"$gte": week_ago_iso}})
    active_drafts = await db.drafts.count_documents({"status": {"$in": ["in_progress", "active", "paused"]}})

    # ── 14-day daily timeseries (signups + new leagues) ──
    user_buckets: dict[str, int] = {}
    league_buckets: dict[str, int] = {}
    for d in range(14, -1, -1):
        key = (now - timedelta(days=d)).date().isoformat()
        user_buckets[key] = 0
        league_buckets[key] = 0

    async for u in db.users.find(
        {"created_at": {"$gte": fourteen_ago.isoformat()}},
        {"created_at": 1},
    ):
        ca = u.get("created_at")
        if isinstance(ca, str):
            key = ca[:10]
            if key in user_buckets:
                user_buckets[key] += 1
    async for lg in db.leagues.find(
        {"created_at": {"$gte": fourteen_ago.isoformat()}},
        {"created_at": 1},
    ):
        ca = lg.get("created_at")
        if isinstance(ca, str):
            key = ca[:10]
            if key in league_buckets:
                league_buckets[key] += 1

    timeseries = [
        {"date": d, "new_users": user_buckets[d], "new_leagues": league_buckets[d]}
        for d in sorted(user_buckets.keys())
    ]

    return {
        "counts": {
            "users": users_total,
            "leagues": leagues_total,
            "teams": teams_total,
            "trades": trades_total,
            "drafts": drafts_total,
        },
        "this_week": {
            "new_users": users_week,
            "new_leagues": leagues_week,
            "trades": trades_week,
            "transactions": transactions_week,
            "active_drafts": active_drafts,
        },
        "timeseries_14d": timeseries,
        "generated_at": _iso(now),
    }


# ─────────────────────────────────────────────────────────────────────
# 2. Commissioner Action Log — cross-league audit feed
# ─────────────────────────────────────────────────────────────────────
# Commissioner-flavored event types we want surfaced in the admin
# moderation feed (anything a commish can do that changes league state).
_COMMISH_EVENT_TYPES = {
    "playoff_winner_marked",
    "playoff_prize_distributed",
    "ops_force_lineup_set",
    "ops_force_roster_move",
    "ops_force_trade_approve",
    "ops_force_trade_reject",
    "ops_force_pause_draft",
    "ops_force_resume_draft",
    "ops_violation_notified",
    "ops_violation_force_fixed",
    "lineup_override",
    "trade_override",
    "waiver_override",
    "team_owner_changed",
    "team_renamed",
    "draft_pick_traded",
    "schedule_regenerated",
    "playoff_format_changed",
    "setup_wizard_completed",
}


@router.get("/commish-actions")
async def commish_actions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    league_id: Optional[str] = None,
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[str] = None,  # ISO 8601
):
    """Aggregated commissioner action feed across ALL leagues. Used by the
    platform admin to spot suspicious patterns. Filterable by league,
    actor, event_type, and a `since` cutoff. Joins league_id → league
    name + user_id → email for display."""
    await _require_admin(request)
    db = _deps["db"]

    query: dict = {"event_type": {"$in": list(_COMMISH_EVENT_TYPES)}}
    if league_id:
        query["league_id"] = league_id
    if user_id:
        query["user_id"] = user_id
    if event_type:
        if event_type not in _COMMISH_EVENT_TYPES:
            raise HTTPException(status_code=400, detail="event_type not in commissioner action whitelist")
        query["event_type"] = event_type
    if since:
        query["created_at"] = {"$gte": since}

    rows = await db.activity_feed.find(query).sort("created_at", -1).limit(limit).to_list(limit)

    # ── Hydrate league + user labels ──
    league_ids = {r.get("league_id") for r in rows if r.get("league_id")}
    user_ids = {r.get("user_id") for r in rows if r.get("user_id")}
    league_lookup: dict = {}
    for lid in league_ids:
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            if lg:
                league_lookup[lid] = lg.get("name")
        except Exception:
            continue
    user_lookup: dict = {}
    for uid in user_ids:
        try:
            u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "name": 1, "role": 1})
            if u:
                user_lookup[uid] = {
                    "email": u.get("email"),
                    "name": u.get("name"),
                    "role": u.get("role"),
                }
        except Exception:
            continue

    entries = []
    for r in rows:
        entries.append({
            "id": str(r["_id"]),
            "event_type": r.get("event_type"),
            "message": r.get("message"),
            "league_id": r.get("league_id"),
            "league_name": league_lookup.get(r.get("league_id")),
            "user_id": r.get("user_id"),
            "user": user_lookup.get(r.get("user_id")),
            "metadata": r.get("metadata") or {},
            "created_at": r.get("created_at"),
            "reverted": bool(r.get("reverted")),
            "reverted_at": r.get("reverted_at"),
            "reverted_by": r.get("reverted_by"),
        })
    return {"entries": entries, "limit": limit, "total": len(entries)}


# ─────────────────────────────────────────────────────────────────────
# 3. Revert a commissioner action (admin-only, writes a paired audit row)
# ─────────────────────────────────────────────────────────────────────
@router.post("/commish-actions/{action_id}/revert")
async def revert_commish_action(action_id: str, request: Request):
    """Mark a prior commissioner action as `reverted` and write a paired
    `platform_admin_revert` audit row pointing back to it. We DO NOT
    auto-undo the state change here — reverting is an audit trail only.
    The platform admin is expected to issue the corrective action via the
    league's own commissioner UI. The flag exists so the action feed can
    visibly mark reverted entries."""
    user = await _require_admin(request)
    db = _deps["db"]

    try:
        oid = ObjectId(action_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid action_id")

    target = await db.activity_feed.find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=404, detail="Action not found")
    if target.get("reverted"):
        raise HTTPException(status_code=400, detail="Action already reverted")
    if target.get("event_type") not in _COMMISH_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Only commissioner-action events can be reverted")

    now = datetime.now(timezone.utc).isoformat()
    admin_label = user.get("email") or str(user.get("_id"))
    await db.activity_feed.update_one(
        {"_id": oid},
        {"$set": {
            "reverted": True,
            "reverted_at": now,
            "reverted_by": str(user["_id"]),
            "reverted_by_email": admin_label,
        }},
    )
    revert_doc = {
        "league_id": target.get("league_id"),
        "event_type": "platform_admin_revert",
        "message": f"Reverted '{target.get('event_type')}': {target.get('message') or ''}".strip(),
        "user_id": str(user["_id"]),
        "metadata": {
            "original_action_id": action_id,
            "original_event_type": target.get("event_type"),
            "original_user_id": target.get("user_id"),
            "original_message": target.get("message"),
            "original_metadata": target.get("metadata") or {},
        },
        "created_at": now,
    }
    res = await db.activity_feed.insert_one(revert_doc)
    return {
        "ok": True,
        "action_id": action_id,
        "revert_audit_id": str(res.inserted_id),
        "reverted_by": admin_label,
        "reverted_at": now,
    }

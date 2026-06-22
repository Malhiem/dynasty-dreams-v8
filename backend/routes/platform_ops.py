"""
Iter 209 — Platform Health & Operations admin endpoints.

Surfaces operator-level dashboards for:
  • Moderator Notes — per-user running notes attached by admins
  • League Health — leagues with inactive commissioners, orphaned teams,
    dead-mid-season indicators
  • Sync / Data Status — NHL career-stats cache health + sync heartbeats
  • Support Ticket metrics — aggregates over the user_reports collection
  • Server / Error Logs — recent ERROR lines from supervisor logs

All endpoints are admin-only.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from collections import Counter
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/admin/platform")
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


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
# Moderator Notes
# ─────────────────────────────────────────────────────────────────────
@router.get("/users/{user_id}/mod-notes")
async def list_mod_notes(user_id: str, request: Request):
    await _require_admin(request)
    rows = await _db().user_mod_notes.find(
        {"user_id": user_id}
    ).sort("created_at", -1).to_list(200)
    return {
        "notes": [{
            "note_id": str(r["_id"]),
            "user_id": r.get("user_id"),
            "author_email": r.get("author_email"),
            "body": r.get("body"),
            "category": r.get("category"),
            "created_at": _iso(r.get("created_at")),
        } for r in rows]
    }


@router.post("/users/{user_id}/mod-notes")
async def add_mod_note(user_id: str, request: Request):
    """Body: { "body": "...", "category": "general|warning|positive|other" }"""
    admin = await _require_admin(request)
    payload = await request.json()
    body = (payload.get("body") or "").strip()[:2000]
    category = payload.get("category") or "general"
    if not body:
        raise HTTPException(status_code=400, detail="body is required")
    if category not in ("general", "warning", "positive", "other"):
        raise HTTPException(status_code=400, detail="invalid category")
    doc = {
        "user_id": user_id,
        "author_id": str(admin["_id"]),
        "author_email": admin.get("email"),
        "body": body,
        "category": category,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().user_mod_notes.insert_one(doc)
    return {"ok": True, "note_id": str(res.inserted_id)}


@router.delete("/users/{user_id}/mod-notes/{note_id}")
async def delete_mod_note(user_id: str, note_id: str, request: Request):
    await _require_admin(request)
    try:
        oid = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    res = await _db().user_mod_notes.delete_one({"_id": oid, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# League Health Dashboard
# ─────────────────────────────────────────────────────────────────────
@router.get("/league-health")
async def league_health(request: Request, days_inactive: int = Query(30, ge=1, le=365)):
    """Surface leagues with health issues:
       - inactive_commissioners: no commish login in N days
       - orphaned_teams: teams without an owner_id
       - dead_leagues: status=active, last_activity > N days
       - capacity_issues: leagues with fewer teams than expected
    """
    await _require_admin(request)
    db = _db()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_inactive)
    cutoff_iso = cutoff.isoformat()

    leagues = await db.leagues.find({}).to_list(2000)

    inactive_commish = []
    orphaned = []
    dead = []
    capacity = []

    for lg in leagues:
        lid = str(lg["_id"])
        commish_id = lg.get("commissioner_id")
        # Commissioner activity
        if commish_id:
            try:
                commish = await db.users.find_one({"_id": ObjectId(commish_id)})
            except Exception:
                commish = None
            if commish:
                last_audit = await db.user_login_audit.find_one(
                    {"user_id": str(commish_id)}, sort=[("ts", -1)]
                )
                if not last_audit or (last_audit.get("ts") or "") < cutoff_iso:
                    inactive_commish.append({
                        "league_id": lid,
                        "league_name": lg.get("name"),
                        "commissioner_email": commish.get("email"),
                        "last_login": (last_audit or {}).get("ts"),
                    })

        # Teams in this league
        team_rows = await db.teams.find({"league_id": lid}).to_list(100)
        orphan_count = sum(1 for t in team_rows if not t.get("owner_id"))
        if orphan_count > 0:
            orphaned.append({
                "league_id": lid,
                "league_name": lg.get("name"),
                "orphaned_team_count": orphan_count,
                "total_teams": len(team_rows),
            })
        expected_teams = lg.get("max_teams") or lg.get("num_teams")
        if expected_teams and len(team_rows) < int(expected_teams):
            capacity.append({
                "league_id": lid,
                "league_name": lg.get("name"),
                "current_teams": len(team_rows),
                "expected_teams": int(expected_teams),
            })

        # Dead leagues — active status but no recent matchups
        if lg.get("status") == "active":
            last_matchup = await db.matchups.find_one(
                {"league_id": lid}, sort=[("created_at", -1)]
            )
            last_activity = (last_matchup or {}).get("created_at")
            if last_activity and (
                (isinstance(last_activity, str) and last_activity < cutoff_iso)
                or (hasattr(last_activity, "isoformat") and last_activity < cutoff)
            ):
                dead.append({
                    "league_id": lid,
                    "league_name": lg.get("name"),
                    "last_matchup_at": _iso(last_activity),
                })

    return {
        "total_leagues": len(leagues),
        "days_inactive": days_inactive,
        "inactive_commissioners": inactive_commish,
        "orphaned_teams": orphaned,
        "dead_leagues": dead,
        "capacity_issues": capacity,
    }


# ─────────────────────────────────────────────────────────────────────
# Sync / Data Status Monitor
# ─────────────────────────────────────────────────────────────────────
@router.get("/sync-status")
async def sync_status(request: Request):
    """NHL data sync health. Surfaces:
       - players collection size + last-synced timestamps
       - career-stats cache hit/miss counts (in-memory)
       - recent sync errors (from db.sync_events collection if populated)
    """
    await _require_admin(request)
    db = _db()
    players_total = await db.players.count_documents({})
    players_with_nhl_id = await db.players.count_documents({"nhl_id": {"$exists": True, "$ne": None}})
    players_stale = 0
    last_sync = None
    last_doc = await db.players.find_one(
        {"last_synced_at": {"$exists": True}}, sort=[("last_synced_at", -1)]
    )
    if last_doc:
        last_sync = _iso(last_doc.get("last_synced_at"))
    cutoff_stale = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    players_stale = await db.players.count_documents({
        "$or": [
            {"last_synced_at": {"$lt": cutoff_stale}},
            {"last_synced_at": {"$exists": False}},
        ],
    })

    # Career cache stats (read from players module's module-level cache)
    career_cache_size = 0
    try:
        from routes.players import _career_cache as _cc
        career_cache_size = len(_cc)
    except Exception:
        pass

    recent_errors = await db.sync_events.find(
        {"level": "error"}
    ).sort("ts", -1).to_list(20)

    is_healthy = bool(last_sync) and players_total > 0

    return {
        "healthy": is_healthy,
        "players_total": players_total,
        "players_with_nhl_id": players_with_nhl_id,
        "players_stale_24h": players_stale,
        "last_sync_at": last_sync,
        "career_cache_size": career_cache_size,
        "recent_errors": [{
            "ts": _iso(r.get("ts")),
            "source": r.get("source"),
            "message": r.get("message"),
        } for r in recent_errors],
    }


# ─────────────────────────────────────────────────────────────────────
# Support Ticket Dashboard (built on user_reports collection)
# ─────────────────────────────────────────────────────────────────────
@router.get("/support-metrics")
async def support_metrics(request: Request, days: int = Query(30, ge=1, le=365)):
    """Aggregate metrics from user_reports for the operator dashboard."""
    await _require_admin(request)
    db = _db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = await db.user_reports.find({"created_at": {"$gte": cutoff}}).to_list(2000)

    open_count = 0
    resolved_count = 0
    dismissed_count = 0
    by_category: Counter[str] = Counter()
    response_times_hours: list[float] = []

    for r in rows:
        st = r.get("status", "open")
        if st == "open":
            open_count += 1
        elif st == "resolved":
            resolved_count += 1
        elif st == "dismissed":
            dismissed_count += 1
        by_category[r.get("category") or "other"] += 1
        created = r.get("created_at")
        resolved = r.get("resolved_at")
        if created and resolved:
            try:
                a = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(resolved).replace("Z", "+00:00"))
                response_times_hours.append((b - a).total_seconds() / 3600)
            except Exception:
                pass

    avg_response = (
        round(sum(response_times_hours) / len(response_times_hours), 1)
        if response_times_hours else None
    )

    return {
        "days": days,
        "total_reports": len(rows),
        "open": open_count,
        "resolved": resolved_count,
        "dismissed": dismissed_count,
        "avg_response_hours": avg_response,
        "by_category": [
            {"category": k, "count": v}
            for k, v in by_category.most_common()
        ],
    }


# ─────────────────────────────────────────────────────────────────────
# Server / Uptime / Error Logs
# ─────────────────────────────────────────────────────────────────────
_LOG_DIR = Path("/var/log/supervisor")
_ERR_PATTERN = re.compile(r"(?i)(ERROR|CRITICAL|Traceback|Exception)")


@router.get("/server-logs")
async def server_logs(
    request: Request,
    service: str = Query("backend", pattern=r"^(backend|frontend)$"),
    lines: int = Query(100, ge=10, le=500),
):
    """Tail recent supervisor log lines, filtering to error-likely
    entries. Restricts to err and out logs."""
    await _require_admin(request)
    candidates = list(_LOG_DIR.glob(f"{service}.err.log*")) + list(
        _LOG_DIR.glob(f"{service}.out.log*")
    )
    if not candidates:
        return {"service": service, "lines": []}

    # Tail the most-recent file (mtime sort)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    target = candidates[0]
    try:
        with open(target, "r", errors="ignore") as f:
            tail = f.readlines()[-lines:]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read log: {e}")

    # Mark error lines
    out = []
    for line in tail:
        is_err = bool(_ERR_PATTERN.search(line))
        out.append({
            "is_error": is_err,
            "line": line.rstrip("\n"),
        })
    error_count = sum(1 for x in out if x["is_error"])
    return {
        "service": service,
        "log_file": target.name,
        "lines": out,
        "error_count": error_count,
        "tail_size": len(out),
    }


@router.get("/uptime")
async def uptime(request: Request):
    """Quick health check: backend boot time + counts of recent
    high-traffic operations (waiver runs, lineup-locks)."""
    await _require_admin(request)
    db = _db()
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    # Recent waiver runs / trade events / lineup audits as throughput
    # signals.
    waivers_24h = await db.waiver_runs.count_documents({"ts": {"$gte": cutoff_24h}})
    trades_24h = await db.trades.count_documents({"created_at": {"$gte": cutoff_24h}})
    logins_24h = await db.user_login_audit.count_documents({"ts": {"$gte": cutoff_24h}})

    # Backend process uptime by reading the supervisor log mtime
    backend_log = _LOG_DIR / "backend.err.log"
    backend_started = None
    if backend_log.exists():
        # supervisor rewrites the log on restart — use modification time
        # of the *.0 rotated file when present; else use the live one.
        # This is an approximation; "exact boot time" would require a
        # supervisor-RPC call which isn't wired up.
        backend_started = datetime.fromtimestamp(
            backend_log.stat().st_mtime, tz=timezone.utc
        ).isoformat()

    return {
        "now": now.isoformat(),
        "backend_log_mtime": backend_started,
        "waivers_24h": waivers_24h,
        "trades_24h": trades_24h,
        "logins_24h": logins_24h,
    }

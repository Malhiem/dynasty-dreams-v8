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


def _tail_log_file(service: str, lines: int = 100) -> dict:
    """Internal helper used by both the public server-logs endpoint and
    the critical-alert sweeper. Returns the same shape as /server-logs."""
    candidates = list(_LOG_DIR.glob(f"{service}.err.log*")) + list(
        _LOG_DIR.glob(f"{service}.out.log*")
    )
    if not candidates:
        return {"service": service, "lines": [], "error_count": 0, "tail_size": 0, "log_file": None}
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    target = candidates[0]
    try:
        with open(target, "r", errors="ignore") as f:
            tail = f.readlines()[-lines:]
    except Exception:
        return {"service": service, "lines": [], "error_count": 0, "tail_size": 0, "log_file": target.name}
    rows = [{"is_error": bool(_ERR_PATTERN.search(line)), "line": line.rstrip("\n")} for line in tail]
    return {
        "service": service,
        "log_file": target.name,
        "lines": rows,
        "error_count": sum(1 for x in rows if x["is_error"]),
        "tail_size": len(rows),
    }


@router.get("/server-logs")
async def server_logs(
    request: Request,
    service: str = Query("backend", pattern=r"^(backend|frontend)$"),
    lines: int = Query(100, ge=10, le=500),
):
    """Tail recent supervisor log lines, marking ERROR/CRITICAL/Traceback
    lines via regex."""
    await _require_admin(request)
    return _tail_log_file(service, lines)


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


# ─────────────────────────────────────────────────────────────────────
# Iter 210 — Critical Alerts (computed + broadcast via Socket.IO)
# ─────────────────────────────────────────────────────────────────────
async def compute_active_alerts() -> list[dict]:
    """Compute the current set of active critical alerts. Three triggers:
      (a) sync_degraded: no players updated in last 15 minutes
      (b) high_error_rate: >50 errors in last 100 backend log lines
      (c) dead_league_surge: ≥3 dead leagues (active status, no matchup
          activity in the last 30 days)
    """
    db = _db()
    now = datetime.now(timezone.utc)
    alerts: list[dict] = []

    # (a) Sync degraded
    cutoff_15min = (now - timedelta(minutes=15)).isoformat()
    fresh_players = await db.players.count_documents(
        {"last_synced_at": {"$gte": cutoff_15min}}
    )
    if fresh_players == 0:
        # Determine whether sync EVER happened — if never, mark "no_sync"
        # rather than "degraded" (avoids spamming during preview/sandbox).
        ever_synced = await db.players.count_documents({"last_synced_at": {"$exists": True}})
        if ever_synced > 0:
            last = await db.players.find_one(
                {"last_synced_at": {"$exists": True}},
                sort=[("last_synced_at", -1)],
            )
            alerts.append({
                "id": "sync_degraded",
                "severity": "critical",
                "title": "NHL data sync degraded",
                "detail": f"No player updates in 15min. Last sync: {(last or {}).get('last_synced_at')}",
                "since": now.isoformat(),
            })

    # (b) High error rate in backend logs
    log = _tail_log_file("backend", lines=100)
    if log.get("error_count", 0) > 50:
        alerts.append({
            "id": "high_error_rate",
            "severity": "critical",
            "title": "Backend error rate spike",
            "detail": f"{log['error_count']} errors in last {log['tail_size']} log lines",
            "since": now.isoformat(),
        })

    # (c) Dead league surge — leagues with status=active but no matchup
    # in 30 days. Threshold ≥ 3.
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    leagues = await db.leagues.find({"status": "active"}, {"_id": 1, "name": 1}).to_list(2000)
    dead_count = 0
    for lg in leagues:
        last_matchup = await db.matchups.find_one(
            {"league_id": str(lg["_id"])}, sort=[("created_at", -1)]
        )
        last_activity = (last_matchup or {}).get("created_at")
        if last_activity and (
            (isinstance(last_activity, str) and last_activity < cutoff_30d)
            or (hasattr(last_activity, "isoformat") and last_activity.isoformat() < cutoff_30d)
        ):
            dead_count += 1
    if dead_count >= 3:
        alerts.append({
            "id": "dead_league_surge",
            "severity": "warning",
            "title": "Dead-league surge",
            "detail": f"{dead_count} active leagues with no matchup activity in 30+ days",
            "since": now.isoformat(),
        })

    return alerts


@router.get("/alerts")
async def get_critical_alerts(request: Request):
    """Return currently-active critical alerts. Polled by the AdminDashboard
    on mount; Socket.IO push handles ongoing updates."""
    await _require_admin(request)
    alerts = await compute_active_alerts()
    return {"alerts": alerts, "computed_at": datetime.now(timezone.utc).isoformat()}


# Background sweeper — broadcasts when the active-alert set changes.
_last_alert_ids: set[str] = set()


async def alerts_sweeper_loop():
    """Run every 60s. If the set of active alert ids changes, broadcast
    the new list to the `platform_admins` Socket.IO room so every
    open admin dashboard updates in real-time."""
    import asyncio
    global _last_alert_ids
    broadcast = _deps.get("broadcast_to_room")
    if not broadcast:
        return
    while True:
        try:
            alerts = await compute_active_alerts()
            # Iter 211 — filter out admin-acknowledged alerts
            silenced = await _active_ack_ids()
            alerts = [a for a in alerts if a["id"] not in silenced]
            current_ids = {a["id"] for a in alerts}
            if current_ids != _last_alert_ids:
                _last_alert_ids = current_ids
                await broadcast(
                    "platform_admins",
                    "critical_alerts",
                    {"alerts": alerts,
                     "computed_at": datetime.now(timezone.utc).isoformat()},
                )
        except Exception:
            # Never let a sweeper failure crash the loop.
            pass
        await asyncio.sleep(60)



# ─────────────────────────────────────────────────────────────────────
# Iter 211 — Alert Acknowledgements + Platform Analytics
# ─────────────────────────────────────────────────────────────────────
@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request):
    """Silence a critical alert. Body: { "duration_minutes": 60 }
    Acks are time-bounded — when the window expires the alert can fire
    again. Filtered out of `compute_active_alerts()` while active."""
    admin = await _require_admin(request)
    payload = await request.json()
    duration_min = int(payload.get("duration_minutes") or 60)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=duration_min)).isoformat()
    await _db().alert_acknowledgements.update_one(
        {"alert_id": alert_id},
        {"$set": {
            "alert_id": alert_id,
            "expires_at": expires,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_by_email": admin.get("email"),
        }},
        upsert=True,
    )
    return {"ok": True, "alert_id": alert_id, "expires_at": expires}


async def _active_ack_ids() -> set[str]:
    """Return alert_ids currently silenced by a non-expired ack."""
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = await _db().alert_acknowledgements.find(
        {"expires_at": {"$gt": now_iso}}, {"alert_id": 1}
    ).to_list(100)
    return {r["alert_id"] for r in rows if r.get("alert_id")}


# Patch `compute_active_alerts` indirectly by wrapping. The original
# definition above is left intact for the sweeper's diff logic; this
# is an admin-facing filtered view.
@router.get("/alerts/active")
async def list_active_alerts(request: Request):
    """Like `/alerts` but filters out alerts the admin has silenced."""
    await _require_admin(request)
    alerts = await compute_active_alerts()
    silenced = await _active_ack_ids()
    visible = [a for a in alerts if a["id"] not in silenced]
    return {
        "alerts": visible,
        "silenced_ids": list(silenced),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Platform Analytics ─────────────────────────────────────────────
@router.get("/analytics/engagement")
async def analytics_engagement(request: Request, days: int = Query(30, ge=7, le=365)):
    """DAU / MAU / retention proxy. Buckets `user_login_audit` by day."""
    await _require_admin(request)
    db = _db()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()
    mau_cutoff = (now - timedelta(days=30)).isoformat()

    pipeline = [
        {"$match": {"ts": {"$gte": cutoff}}},
        {"$addFields": {"day": {"$substr": ["$ts", 0, 10]}}},
        {"$group": {"_id": "$day", "users": {"$addToSet": "$user_id"}}},
        {"$project": {"day": "$_id", "dau": {"$size": "$users"}}},
        {"$sort": {"day": 1}},
    ]
    daily = await db.user_login_audit.aggregate(pipeline).to_list(400)
    dau_series = [{"day": d["day"], "dau": d["dau"]} for d in daily]

    # MAU = distinct users in last 30 days
    mau_pipeline = [
        {"$match": {"ts": {"$gte": mau_cutoff}}},
        {"$group": {"_id": None, "users": {"$addToSet": "$user_id"}}},
        {"$project": {"mau": {"$size": "$users"}}},
    ]
    mau_rows = await db.user_login_audit.aggregate(mau_pipeline).to_list(1)
    mau = (mau_rows[0]["mau"] if mau_rows else 0)

    # Latest-day DAU
    latest_dau = dau_series[-1]["dau"] if dau_series else 0
    dau_mau_ratio = round(latest_dau / mau, 3) if mau else 0

    # Cohort retention proxy: how many users created in months M still
    # logged in within the trailing 30 days
    users = await db.users.find({}, {"created_at": 1}).to_list(50000)
    cohorts: dict[str, dict] = {}
    for u in users:
        created = u.get("created_at")
        if not created:
            continue
        try:
            if isinstance(created, str):
                cohort = created[:7]  # YYYY-MM
            else:
                cohort = created.strftime("%Y-%m")
        except Exception:
            continue
        cohorts.setdefault(cohort, {"cohort": cohort, "total": 0, "retained": 0})
        cohorts[cohort]["total"] += 1
    # Who logged in within last 30 days
    active_users = await db.user_login_audit.distinct("user_id", {"ts": {"$gte": mau_cutoff}})
    active_set = set(active_users)
    for u in users:
        created = u.get("created_at")
        if not created or str(u["_id"]) not in active_set:
            continue
        try:
            if isinstance(created, str):
                cohort = created[:7]
            else:
                cohort = created.strftime("%Y-%m")
        except Exception:
            continue
        if cohort in cohorts:
            cohorts[cohort]["retained"] += 1
    cohort_rows = sorted(cohorts.values(), key=lambda c: c["cohort"])
    for c in cohort_rows:
        c["retention_pct"] = round(c["retained"] / c["total"] * 100, 1) if c["total"] else 0

    return {
        "days": days,
        "dau_series": dau_series,
        "mau": mau,
        "latest_dau": latest_dau,
        "dau_mau_ratio": dau_mau_ratio,
        "cohort_retention": cohort_rows[-12:],  # last 12 monthly cohorts
    }


@router.get("/analytics/league-survival")
async def analytics_league_survival(request: Request):
    """For each year-of-creation, % of leagues still active today."""
    await _require_admin(request)
    db = _db()
    leagues = await db.leagues.find({}, {"created_at": 1, "status": 1}).to_list(10000)
    by_year: dict[str, dict] = {}
    for lg in leagues:
        created = lg.get("created_at")
        if not created:
            continue
        try:
            year = str(created)[:4] if isinstance(created, str) else created.strftime("%Y")
        except Exception:
            continue
        by_year.setdefault(year, {"year": year, "total": 0, "still_active": 0})
        by_year[year]["total"] += 1
        if lg.get("status") == "active":
            by_year[year]["still_active"] += 1
    rows = sorted(by_year.values(), key=lambda r: r["year"])
    for r in rows:
        r["survival_pct"] = round(r["still_active"] / r["total"] * 100, 1) if r["total"] else 0
    return {"by_year": rows}


@router.get("/analytics/feature-usage")
async def analytics_feature_usage(request: Request, days: int = Query(30, ge=1, le=365)):
    """Top-N most-active routes by hit count from supervisor's out log."""
    await _require_admin(request)
    log = _tail_log_file("backend", lines=500)
    counter: Counter[str] = Counter()
    # Parse access-log lines like:  "GET /api/players?league_id=... HTTP/1.1"
    pat = re.compile(r'"(?:GET|POST|PUT|DELETE|PATCH) (/api/[^?\s]+)')
    for row in log.get("lines", []):
        m = pat.search(row.get("line", ""))
        if m:
            counter[m.group(1)] += 1
    top = [{"endpoint": k, "hits": v} for k, v in counter.most_common(25)]
    return {"top_endpoints": top, "log_tail_size": log.get("tail_size", 0)}


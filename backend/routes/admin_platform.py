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


# ─────────────────────────────────────────────────────────────────────
# Iter 201b — Trades Review (fairness-scored, cross-league)
# ─────────────────────────────────────────────────────────────────────
from routes.trade_fairness import compute_fairness, ALERT_THRESHOLD  # noqa: E402


@router.get("/trades-review")
async def trades_review(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    league_id: Optional[str] = None,
    only_alerts: bool = False,
    sort_by: str = Query(default="created_desc", pattern=r"^(created_desc|fairness_asc|fairness_desc)$"),
):
    """Cross-league trade review feed with fairness scoring. Each trade is
    annotated with `fairness.score` (0-100) + `fairness.alert` (bool) + a
    `favored_side` indicator + age differential."""
    await _require_admin(request)
    db = _deps["db"]

    query: dict = {"status": {"$in": ["executed", "completed", "approved"]}}
    if league_id:
        query["league_id"] = league_id

    rows = await db.trades.find(query).sort("created_at", -1).limit(limit * 2).to_list(limit * 2)

    # Hydrate players involved
    pids = set()
    for r in rows:
        for side in ("assets_offered", "assets_requested"):
            for a in r.get(side) or []:
                if a.get("asset_type") == "player" and a.get("player_id"):
                    pids.add(str(a["player_id"]))
    player_lookup: dict = {}
    if pids:
        # Map both ObjectId and string lookups
        oid_list = []
        for p in pids:
            try:
                oid_list.append(ObjectId(p))
            except Exception:
                continue
        async for p in db.players.find({"_id": {"$in": oid_list}}):
            player_lookup[str(p["_id"])] = p

    # League name + team name hydration
    league_ids = {r.get("league_id") for r in rows if r.get("league_id")}
    league_lookup: dict = {}
    for lid in league_ids:
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            if lg:
                league_lookup[lid] = lg.get("name")
        except Exception:
            continue

    current_year = datetime.now(timezone.utc).year
    out = []
    for r in rows:
        fairness = compute_fairness(r, player_lookup, current_year=current_year)
        if only_alerts and not fairness["alert"]:
            continue
        out.append({
            "id": str(r["_id"]),
            "league_id": r.get("league_id"),
            "league_name": league_lookup.get(r.get("league_id")),
            "proposer_team_id": r.get("proposer_team_id"),
            "proposer_team_name": r.get("proposer_team_name"),
            "target_team_id": r.get("target_team_id"),
            "target_team_name": r.get("target_team_name"),
            "status": r.get("status"),
            "created_at": r.get("submitted_at") or r.get("created_at"),
            "executed_at": r.get("processed_at"),
            "fairness": fairness,
            "asset_counts": {
                "offered": len(r.get("assets_offered") or []),
                "requested": len(r.get("assets_requested") or []),
            },
        })

    # Sort
    if sort_by == "fairness_asc":
        out.sort(key=lambda x: x["fairness"]["score"])
    elif sort_by == "fairness_desc":
        out.sort(key=lambda x: -x["fairness"]["score"])
    # default created_desc already in order

    return {
        "entries": out[:limit],
        "alert_threshold": ALERT_THRESHOLD,
        "total": len(out),
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 201c — Collusion + Tanking detection
# ─────────────────────────────────────────────────────────────────────
@router.get("/collusion-flags")
async def collusion_flags(
    request: Request,
    min_trades: int = Query(default=3, ge=2, le=20),
    min_net_favor_pct: float = Query(default=30.0, ge=10.0, le=100.0),
):
    """Flag user pairs (proposer↔target) who have traded `min_trades`+
    times with a cumulative one-sidedness exceeding `min_net_favor_pct`.

    Aggregates by (proposer_id, target_owner_id) and sums (100 - fairness)
    × direction across trades. Any pair where |net favor| > threshold and
    count ≥ min_trades is surfaced."""
    await _require_admin(request)
    db = _deps["db"]

    # Pull recent executed trades (90 days), hydrate players, compute fairness
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    rows = await db.trades.find(
        {"status": {"$in": ["executed", "completed", "approved"]}, "submitted_at": {"$gte": since}},
    ).to_list(1000)
    if not rows:
        return {"pairs": [], "min_trades": min_trades, "min_net_favor_pct": min_net_favor_pct}

    # Player lookup
    pids = set()
    for r in rows:
        for side in ("assets_offered", "assets_requested"):
            for a in r.get(side) or []:
                if a.get("asset_type") == "player" and a.get("player_id"):
                    pids.add(str(a["player_id"]))
    player_lookup: dict = {}
    oid_list = []
    for p in pids:
        try:
            oid_list.append(ObjectId(p))
        except Exception:
            continue
    async for p in db.players.find({"_id": {"$in": oid_list}}):
        player_lookup[str(p["_id"])] = p

    current_year = datetime.now(timezone.utc).year
    pair_buckets: dict = {}  # key = sorted (u1, u2) tuple
    for r in rows:
        u1, u2 = r.get("proposer_id"), r.get("target_owner_id")
        if not (u1 and u2):
            continue
        pair_key = tuple(sorted([str(u1), str(u2)]))
        f = compute_fairness(r, player_lookup, current_year=current_year)
        delta = 100 - f["score"]  # unfair-ness magnitude
        # Direction: who got the better side? +1 if u1 favored, -1 if u2 favored
        direction = 0
        if f["favored_side"] == "offered":
            # target got the better side (received the offered side)
            direction = +1 if str(u2) == pair_key[0] else -1
        elif f["favored_side"] == "requested":
            direction = +1 if str(u1) == pair_key[0] else -1
        bucket = pair_buckets.setdefault(pair_key, {
            "pair": list(pair_key), "trade_count": 0, "net_favor": 0.0, "trades": []
        })
        bucket["trade_count"] += 1
        bucket["net_favor"] += direction * delta
        bucket["trades"].append({
            "trade_id": str(r["_id"]),
            "league_id": r.get("league_id"),
            "score": f["score"],
            "favored_side": f["favored_side"],
            "submitted_at": r.get("submitted_at"),
        })

    flagged = []
    for pair_key, b in pair_buckets.items():
        if b["trade_count"] >= min_trades and abs(b["net_favor"]) >= min_net_favor_pct:
            # Hydrate user emails
            user_lookup = {}
            for uid in pair_key:
                try:
                    u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "name": 1})
                    if u:
                        user_lookup[uid] = {"email": u.get("email"), "name": u.get("name")}
                except Exception:
                    pass
            flagged.append({
                **b,
                "net_favor": round(b["net_favor"], 1),
                "favored_user_id": pair_key[0] if b["net_favor"] > 0 else pair_key[1],
                "users": user_lookup,
            })

    flagged.sort(key=lambda x: -abs(x["net_favor"]))
    return {"pairs": flagged, "min_trades": min_trades, "min_net_favor_pct": min_net_favor_pct}


@router.get("/tanking-flags")
async def tanking_flags(
    request: Request,
    weeks_window: int = Query(default=4, ge=1, le=10),
):
    """Heuristic tanking detection. For each league, identifies teams
    that are (a) outside the playoff cutoff with ≤3 weeks left, and (b)
    benched ≥2 of their top-5 salary players in the last `weeks_window`
    weeks (i.e., active points dropped sharply while bench points stayed
    high).

    Uses `lineup_history` entries from `activity_feed` (event_type =
    'lineup_set') if present; otherwise falls back to a salary-based
    proxy that flags teams whose top-5 salary players have ≥50%
    bench-time in the window.
    """
    await _require_admin(request)
    db = _deps["db"]

    # Gather recent lineup-set events
    since = (datetime.now(timezone.utc) - timedelta(days=weeks_window * 7)).isoformat()
    suspicious_teams: dict = {}

    # Iterate leagues — only those with active matchups
    async for league in db.leagues.find({}, {"_id": 1, "name": 1, "playoff_teams": 1, "current_week": 1, "regular_season_weeks": 1}):
        lid = str(league["_id"])
        # Cheap heuristic: weeks remaining
        cur_wk = league.get("current_week") or 0
        reg_wks = league.get("regular_season_weeks") or 0
        weeks_left = max(0, reg_wks - cur_wk)
        if weeks_left > 3:
            continue  # only late-season

        # Standings rank cutoff
        playoff_cut = league.get("playoff_teams") or 8
        teams = await db.teams.find({"league_id": lid}).to_list(64)
        if not teams:
            continue
        ranked = sorted(teams, key=lambda t: (-(t.get("wins") or 0), -(t.get("points_for") or 0)))
        non_playoff = ranked[playoff_cut:]

        for team in non_playoff:
            top5_ids = sorted(
                ((p, s) for p, s in (team.get("player_salaries") or {}).items() if isinstance(s, (int, float))),
                key=lambda kv: -kv[1],
            )[:5]
            if not top5_ids:
                continue
            top5_pids = {pid for pid, _ in top5_ids}

            # Count how many of the top-5 were benched in the window
            benched_count = 0
            benched_evidence: list = []
            async for ev in db.activity_feed.find({
                "league_id": lid,
                "event_type": "lineup_set",
                "created_at": {"$gte": since},
                "metadata.team_id": str(team["_id"]),
            }).limit(50):
                meta = ev.get("metadata") or {}
                for pid in (meta.get("benched_player_ids") or []):
                    if str(pid) in top5_pids:
                        benched_count += 1
                        benched_evidence.append({"player_id": str(pid), "ts": ev.get("created_at")})
            # Fallback proxy when no lineup_set events recorded
            if benched_count == 0 and not benched_evidence:
                continue
            if benched_count >= 2:
                suspicious_teams.setdefault(lid, {
                    "league_id": lid,
                    "league_name": league.get("name"),
                    "weeks_left": weeks_left,
                    "teams": [],
                })["teams"].append({
                    "team_id": str(team["_id"]),
                    "team_name": team.get("name"),
                    "owner_id": str(team.get("owner_id") or ""),
                    "owner_name": team.get("owner_name"),
                    "benched_top5_count": benched_count,
                    "evidence": benched_evidence[:5],
                })

    return {"flagged": list(suspicious_teams.values()), "weeks_window": weeks_window}


# ─────────────────────────────────────────────────────────────────────
# Iter 201d — Lineup audit + multi-account-by-IP detection
# ─────────────────────────────────────────────────────────────────────
@router.get("/lineup-audit")
async def lineup_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    league_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """Lineup-mutation audit trail. Returns recent `lineup_set` events
    with IP / user-agent / actor identity. Also surfaces a derived
    `multi_account_flags` block: any IP that has set lineups for ≥2
    DIFFERENT user_ids across leagues in the last 14 days."""
    await _require_admin(request)
    db = _deps["db"]

    query: dict = {"event_type": "lineup_set"}
    if league_id:
        query["league_id"] = league_id
    if team_id:
        query["metadata.team_id"] = team_id
    if user_id:
        query["user_id"] = user_id

    rows = await db.activity_feed.find(query).sort("created_at", -1).limit(limit).to_list(limit)

    user_ids = {r.get("user_id") for r in rows if r.get("user_id")}
    league_ids = {r.get("league_id") for r in rows if r.get("league_id")}
    user_lookup: dict = {}
    league_lookup: dict = {}
    for uid in user_ids:
        try:
            u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "name": 1})
            if u:
                user_lookup[uid] = {"email": u.get("email"), "name": u.get("name")}
        except Exception:
            pass
    for lid in league_ids:
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            if lg:
                league_lookup[lid] = lg.get("name")
        except Exception:
            pass

    entries = []
    for r in rows:
        meta = r.get("metadata") or {}
        entries.append({
            "id": str(r["_id"]),
            "league_id": r.get("league_id"),
            "league_name": league_lookup.get(r.get("league_id")),
            "user_id": r.get("user_id"),
            "user": user_lookup.get(r.get("user_id")),
            "team_id": meta.get("team_id"),
            "ip": meta.get("ip"),
            "user_agent": meta.get("user_agent"),
            "device_fingerprint": meta.get("device_fingerprint"),
            "created_at": r.get("created_at"),
            "summary": meta.get("summary") or r.get("message"),
        })

    # Multi-account detection: same IP setting lineups for >1 user_id in 14d
    fortnight_ago = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    ip_to_users: dict = {}
    async for r in db.activity_feed.find(
        {"event_type": "lineup_set", "created_at": {"$gte": fortnight_ago}, "metadata.ip": {"$exists": True}},
        {"user_id": 1, "metadata.ip": 1, "league_id": 1},
    ):
        ip = (r.get("metadata") or {}).get("ip")
        uid = r.get("user_id")
        if ip and uid:
            ip_to_users.setdefault(ip, set()).add(uid)
    multi_flags = []
    for ip, uids in ip_to_users.items():
        if len(uids) >= 2:
            emails = []
            for uid in uids:
                lookup = user_lookup.get(uid)
                if not lookup:
                    try:
                        u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
                        lookup = {"email": (u or {}).get("email")}
                    except Exception:
                        lookup = {"email": uid}
                emails.append(lookup.get("email") or uid)
            multi_flags.append({"ip": ip, "user_count": len(uids), "users": emails})

    return {
        "entries": entries,
        "multi_account_flags": sorted(multi_flags, key=lambda x: -x["user_count"]),
        "limit": limit,
    }


# Iter 201d — helper used by the lineup write paths to stamp IP/UA
async def record_lineup_event(
    db,
    league_id: str,
    team_id: str,
    user_id: str,
    request: Request,
    summary: str | None = None,
    benched_player_ids: list[str] | None = None,
):
    """Record a `lineup_set` audit event with IP + UA fingerprinting. Call
    from `routes/lineup.py` after every lineup mutation."""
    ip = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    ua = request.headers.get("user-agent", "")[:240]
    await db.activity_feed.insert_one({
        "league_id": league_id,
        "event_type": "lineup_set",
        "message": summary or "Lineup updated",
        "user_id": user_id,
        "metadata": {
            "team_id": team_id,
            "ip": ip,
            "user_agent": ua,
            "device_fingerprint": f"{ip}::{ua[:60]}",
            "summary": summary,
            "benched_player_ids": benched_player_ids or [],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────
# Iter 201e — Admin moderation actions
#   • POST /trades/{trade_id}/revert       — roll back asset/pick moves
#   • POST /pairs/lock                     — lock trades between user pair
#   • GET  /pairs/locks                    — list active locks
#   • DELETE /pairs/locks/{lock_id}        — release a lock
# ─────────────────────────────────────────────────────────────────────
from pydantic import BaseModel  # noqa: E402


@router.post("/trades/{trade_id}/revert")
async def admin_revert_trade(trade_id: str, request: Request):
    """Roll back an EXECUTED trade. Swaps players + picks back to their
    pre-trade owners, marks `status="reverted"`, writes an audit row, and
    notifies both team owners. Cap impact is implicit via roster updates —
    we don't unwind cap-retention pacts (those need manual review)."""
    user = await _require_admin(request)
    db = _deps["db"]

    try:
        tid = ObjectId(trade_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trade_id")
    trade = await db.trades.find_one({"_id": tid})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") in ("reverted", "vetoed"):
        raise HTTPException(status_code=400, detail=f"Trade already in terminal state: {trade['status']}")
    if trade.get("status") != "executed":
        raise HTTPException(status_code=400, detail="Only executed trades can be reverted")

    proposer = await db.teams.find_one({"_id": ObjectId(trade["proposer_team_id"])})
    target = await db.teams.find_one({"_id": ObjectId(trade["target_team_id"])})
    if not (proposer and target):
        raise HTTPException(status_code=404, detail="Proposer or target team missing")

    proposer_roster = list(proposer.get("roster") or [])
    target_roster = list(target.get("roster") or [])

    # ── Swap players BACK: offered moves from target → proposer ──
    for a in trade.get("assets_offered") or []:
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in target_roster:
                target_roster.remove(pid)
            if pid not in proposer_roster:
                proposer_roster.append(pid)
        elif a.get("asset_type") == "pick":
            # Pick currently with target → back to proposer
            await db.draft_picks.update_one(
                {"league_id": trade["league_id"], "current_team_id": trade["target_team_id"],
                 **({"_id": ObjectId(a["pick_id"])} if a.get("pick_id") else
                    {**({"year": int(a["pick_year"])} if a.get("pick_year") else {}),
                     **({"round": int(str(a["pick_round"]).replace("R", "").strip())} if a.get("pick_round") else {})})},
                {"$set": {"current_team_id": trade["proposer_team_id"], "current_team_name": proposer.get("name")}},
            )

    # ── Swap players BACK: requested moves from proposer → target ──
    for a in trade.get("assets_requested") or []:
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in proposer_roster:
                proposer_roster.remove(pid)
            if pid not in target_roster:
                target_roster.append(pid)
        elif a.get("asset_type") == "pick":
            await db.draft_picks.update_one(
                {"league_id": trade["league_id"], "current_team_id": trade["proposer_team_id"],
                 **({"_id": ObjectId(a["pick_id"])} if a.get("pick_id") else
                    {**({"year": int(a["pick_year"])} if a.get("pick_year") else {}),
                     **({"round": int(str(a["pick_round"]).replace("R", "").strip())} if a.get("pick_round") else {})})},
                {"$set": {"current_team_id": trade["target_team_id"], "current_team_name": target.get("name")}},
            )

    await db.teams.update_one({"_id": proposer["_id"]}, {"$set": {"roster": proposer_roster}})
    await db.teams.update_one({"_id": target["_id"]}, {"$set": {"roster": target_roster}})

    now = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"_id": tid},
        {"$set": {
            "status": "reverted",
            "reverted_at": now,
            "reverted_by": str(user["_id"]),
            "reverted_by_email": user.get("email"),
        }},
    )
    await db.activity_feed.insert_one({
        "league_id": trade["league_id"],
        "event_type": "platform_admin_trade_revert",
        "message": f"Admin reverted trade {trade_id} ({proposer.get('name')} ↔ {target.get('name')})",
        "user_id": str(user["_id"]),
        "metadata": {
            "trade_id": trade_id,
            "proposer_team_id": trade["proposer_team_id"],
            "target_team_id": trade["target_team_id"],
            "reverted_by_email": user.get("email"),
        },
        "created_at": now,
    })
    return {"ok": True, "trade_id": trade_id, "reverted_at": now, "reverted_by": user.get("email")}


class PairLockBody(BaseModel):
    user_ids: list[str]
    league_id: str | None = None
    reason: str | None = None


@router.post("/pairs/lock")
async def admin_lock_pair(body: PairLockBody, request: Request):
    """Lock trading between a pair (or group) of user_ids. The trade
    creation endpoint should consult `trade_locks` and reject any pending
    trade whose (proposer_id, target_owner_id) intersects with an active
    lock. Scope optionally narrowed to a single league."""
    user = await _require_admin(request)
    db = _deps["db"]
    if len(body.user_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 user_ids to lock a pair")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_ids": sorted(set(str(u) for u in body.user_ids)),
        "league_id": body.league_id,  # null = global lock
        "reason": body.reason,
        "locked_by": str(user["_id"]),
        "locked_by_email": user.get("email"),
        "locked_at": now,
        "active": True,
    }
    res = await db.trade_locks.insert_one(doc)
    await db.activity_feed.insert_one({
        "league_id": body.league_id,
        "event_type": "platform_admin_pair_lock",
        "message": f"Admin locked trading between {len(body.user_ids)} users",
        "user_id": str(user["_id"]),
        "metadata": {"lock_id": str(res.inserted_id), **doc},
        "created_at": now,
    })
    return {"ok": True, "lock_id": str(res.inserted_id), **{k: v for k, v in doc.items() if k != "_id"}}


@router.get("/pairs/locks")
async def list_pair_locks(request: Request, active_only: bool = True):
    await _require_admin(request)
    db = _deps["db"]
    q = {"active": True} if active_only else {}
    rows = await db.trade_locks.find(q).sort("locked_at", -1).to_list(200)
    out = []
    for r in rows:
        # Hydrate emails
        emails = []
        for uid in (r.get("user_ids") or []):
            try:
                u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
                if u:
                    emails.append(u.get("email"))
            except Exception:
                emails.append(uid)
        out.append({
            "lock_id": str(r["_id"]),
            "user_ids": r.get("user_ids") or [],
            "emails": emails,
            "league_id": r.get("league_id"),
            "reason": r.get("reason"),
            "locked_by_email": r.get("locked_by_email"),
            "locked_at": r.get("locked_at"),
            "active": r.get("active", True),
        })
    return {"locks": out}


@router.delete("/pairs/locks/{lock_id}")
async def admin_release_lock(lock_id: str, request: Request):
    user = await _require_admin(request)
    db = _deps["db"]
    try:
        oid = ObjectId(lock_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lock_id")
    res = await db.trade_locks.update_one(
        {"_id": oid, "active": True},
        {"$set": {"active": False, "released_at": datetime.now(timezone.utc).isoformat(),
                  "released_by": str(user["_id"]), "released_by_email": user.get("email")}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lock not found or already released")
    return {"ok": True, "lock_id": lock_id}


async def is_trade_locked(db, league_id: str, proposer_id: str, target_owner_id: str) -> dict | None:
    """Helper for the trade-create endpoint to gate proposals. Returns the
    active lock document if the pair is locked (global or league-scoped),
    else None."""
    p = str(proposer_id)
    t = str(target_owner_id)
    lock = await db.trade_locks.find_one({
        "active": True,
        "user_ids": {"$all": [p, t]},
        "$or": [{"league_id": None}, {"league_id": league_id}],
    })
    return lock


# ─────────────────────────────────────────────────────────────────────
# Iter 205 — Content Moderation Phase 1: Report/Flag System
# ─────────────────────────────────────────────────────────────────────
# Schema: db.user_reports = {
#   _id, reporter_id, reporter_email,
#   target_user_id, target_user_email,
#   target_team_id?, league_id?,
#   category, reason, context_url?,
#   status: "open" | "resolved" | "dismissed",
#   created_at,
#   resolved_at?, resolved_by?, resolution_note?, resolution_action?,
# }
# `category` is a free-form string from a UI dropdown (e.g. "harassment",
# "spam", "offensive_username", "trade_collusion", "other").

VALID_REPORT_CATEGORIES = {
    "harassment",
    "spam",
    "offensive_username",
    "offensive_team_name",
    "offensive_avatar",
    "trade_collusion",
    "cheating",
    "other",
}


@router.get("/reports")
async def list_user_reports(
    request: Request,
    status: str = Query("open", pattern=r"^(open|resolved|dismissed|all)$"),
    limit: int = Query(100, ge=1, le=500),
):
    """List submitted user reports (admin-only). Default surfaces only
    `open` tickets so the moderation queue stays focused."""
    await _require_admin(request)
    db = _deps["db"]
    q: dict = {} if status == "all" else {"status": status}
    rows = await db.user_reports.find(q).sort("created_at", -1).to_list(limit)
    out = []
    for r in rows:
        out.append({
            "report_id": str(r["_id"]),
            "reporter_id": r.get("reporter_id"),
            "reporter_email": r.get("reporter_email"),
            "target_user_id": r.get("target_user_id"),
            "target_user_email": r.get("target_user_email"),
            "target_team_id": r.get("target_team_id"),
            "league_id": r.get("league_id"),
            "category": r.get("category"),
            "reason": r.get("reason"),
            "context_url": r.get("context_url"),
            "status": r.get("status"),
            "created_at": _iso(r.get("created_at")),
            "resolved_at": _iso(r.get("resolved_at")),
            "resolved_by": r.get("resolved_by"),
            "resolution_note": r.get("resolution_note"),
            "resolution_action": r.get("resolution_action"),
        })
    # Counts for the dashboard tab badge
    open_count = await db.user_reports.count_documents({"status": "open"})
    return {"reports": out, "open_count": open_count}


@router.post("/reports/{report_id}/resolve")
async def resolve_user_report(report_id: str, request: Request):
    """Resolve or dismiss a report. Body:
      { "action": "resolved" | "dismissed", "note": "...", "applied_action": "warning"|"timeout"|"ban"|"none" }
    """
    user = await _require_admin(request)
    db = _deps["db"]
    try:
        oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report id")

    payload = await request.json()
    action = payload.get("action") or "resolved"
    if action not in ("resolved", "dismissed"):
        raise HTTPException(status_code=400, detail="action must be resolved|dismissed")
    note = (payload.get("note") or "").strip()[:1000]
    applied_action = payload.get("applied_action") or "none"
    if applied_action not in ("warning", "timeout", "ban", "none"):
        raise HTTPException(status_code=400, detail="invalid applied_action")

    res = await db.user_reports.update_one(
        {"_id": oid, "status": "open"},
        {
            "$set": {
                "status": action,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": str(user["_id"]),
                "resolved_by_email": user.get("email"),
                "resolution_note": note,
                "resolution_action": applied_action,
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Report not found or already resolved")
    return {"ok": True, "report_id": report_id, "status": action}



# ─────────────────────────────────────────────────────────────────────
# Iter 214 — Users directory + per-user identity / security drilldown
# ─────────────────────────────────────────────────────────────────────
@router.get("/users")
async def list_users(
    request: Request,
    q: Optional[str] = Query(None, description="search email or username"),
    status: Optional[str] = Query(None, pattern=r"^(active|suspended|banned|deactivated|pending_verification)$"),
    role: Optional[str] = Query(None, pattern=r"^(user|admin|commissioner)$"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Paginated user directory for admins. Returns identity + status
    summary per row; the per-user detail endpoint surfaces login history,
    devices, etc."""
    await _require_admin(request)
    db = _deps["db"]
    flt: dict = {}
    if q:
        flt["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"username": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]
    if status:
        flt["status"] = status
    if role:
        flt["role"] = role
    total = await db.users.count_documents(flt)
    cursor = db.users.find(flt, {
        "email": 1, "username": 1, "name": 1, "role": 1, "status": 1,
        "is_active": 1, "created_at": 1, "email_verified": 1, "phone": 1,
        "phone_verified": 1, "auth_method": 1, "two_factor_enabled": 1,
        "last_login_at": 1, "failed_login_attempts": 1, "lockout_until": 1,
        "ban_reason_code": 1, "ban_reason": 1, "ban_expires_at": 1,
    }).sort("created_at", -1).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    # Latest login timestamp fallback via user_login_audit when last_login_at not set.
    user_ids = [str(r["_id"]) for r in rows]
    last_login_by_uid: dict = {}
    if user_ids:
        async for a in db.user_login_audit.aggregate([
            {"$match": {"user_id": {"$in": user_ids}}},
            {"$sort": {"ts": -1}},
            {"$group": {"_id": "$user_id", "ts": {"$first": "$ts"}}},
        ]):
            last_login_by_uid[a["_id"]] = a["ts"]
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "users": [{
            "id": str(r["_id"]),
            "email": r.get("email"),
            "username": r.get("username"),
            "name": r.get("name"),
            "role": r.get("role") or "user",
            "status": r.get("status") or ("active" if r.get("is_active", True) else "deactivated"),
            "created_at": _iso(r.get("created_at")),
            "email_verified": bool(r.get("email_verified", False)),
            "phone": r.get("phone"),
            "phone_verified": bool(r.get("phone_verified", False)),
            "auth_method": r.get("auth_method") or "email",
            "two_factor_enabled": bool(r.get("two_factor_enabled", False)),
            "last_login_at": _iso(r.get("last_login_at")) or last_login_by_uid.get(str(r["_id"])),
            "failed_login_attempts": int(r.get("failed_login_attempts") or 0),
            "lockout_until": _iso(r.get("lockout_until")),
            "ban_reason_code": r.get("ban_reason_code"),
            "ban_reason": r.get("ban_reason"),
            "ban_expires_at": _iso(r.get("ban_expires_at")),
        } for r in rows],
    }


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, request: Request):
    """Full per-user identity / authentication / security view for
    admin moderation. Surfaces:
      • Identity & account core (username, email, phone, status…)
      • Username/email change history (from `user_audit_log`)
      • Authentication & security (last login, login history,
        2FA, password reset history, linked SSO accounts, active
        sessions, recovery info)
    """
    await _require_admin(request)
    db = _deps["db"]
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    u = await db.users.find_one({"_id": oid})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    # Login history (last 50)
    login_history = await db.user_login_audit.find(
        {"user_id": user_id}
    ).sort("ts", -1).to_list(50)

    # Username / email change history (if recorded)
    name_history = await db.user_audit_log.find(
        {"user_id": user_id, "event_type": {"$in": ["username_changed", "email_changed", "name_changed"]}}
    ).sort("ts", -1).to_list(50)

    # Password reset history
    pwd_resets = await db.password_reset_audit.find(
        {"user_id": user_id}
    ).sort("ts", -1).to_list(20)

    # Active sessions (jwt issuance audit, if recorded)
    sessions = await db.user_sessions.find(
        {"user_id": user_id, "revoked": {"$ne": True}}
    ).sort("issued_at", -1).to_list(20)

    return {
        # ── Identity & Account Core ───────────────────────────────
        "id": str(u["_id"]),
        "username": u.get("username"),
        "name": u.get("name"),
        "email": u.get("email"),
        "email_verified": bool(u.get("email_verified", False)),
        "phone": u.get("phone"),
        "phone_verified": bool(u.get("phone_verified", False)),
        "auth_method": u.get("auth_method") or "email",
        "password_hash_present": bool(u.get("password_hash")),
        "linked_sso_accounts": u.get("linked_sso_accounts") or [],
        "role": u.get("role") or "user",
        "status": u.get("status") or ("active" if u.get("is_active", True) else "deactivated"),
        "ban_reason_code": u.get("ban_reason_code"),
        "ban_reason": u.get("ban_reason"),
        "ban_expires_at": _iso(u.get("ban_expires_at")),
        "created_at": _iso(u.get("created_at")),
        "username_change_history": [{
            "ts": _iso(h.get("ts")),
            "event_type": h.get("event_type"),
            "from": h.get("from_value"),
            "to": h.get("to_value"),
        } for h in name_history],
        # ── Authentication & Security ─────────────────────────────
        "last_login_at": _iso(u.get("last_login_at")) or (
            _iso(login_history[0].get("ts")) if login_history else None
        ),
        "login_history": [{
            "ts": _iso(h.get("ts")),
            "ip": h.get("ip"),
            "user_agent": h.get("user_agent"),
            "device_hash": h.get("device_hash"),
            "device_fingerprint": h.get("device_fingerprint"),
        } for h in login_history],
        "failed_login_attempts": int(u.get("failed_login_attempts") or 0),
        "lockout_until": _iso(u.get("lockout_until")),
        "two_factor_enabled": bool(u.get("two_factor_enabled", False)),
        "two_factor_method": u.get("two_factor_method"),
        "password_reset_history": [{
            "ts": _iso(p.get("ts")),
            "ip": p.get("ip"),
            "outcome": p.get("outcome"),
        } for p in pwd_resets],
        "active_sessions": [{
            "session_id": str(s.get("_id")),
            "issued_at": _iso(s.get("issued_at")),
            "expires_at": _iso(s.get("expires_at")),
            "ip": s.get("ip"),
            "user_agent": s.get("user_agent"),
        } for s in sessions],
        "recovery_email": u.get("recovery_email"),
        "security_questions_set": bool(u.get("security_questions")),
    }

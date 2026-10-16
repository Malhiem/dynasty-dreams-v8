"""
Iter 218 — UX Analytics (pageviews + feature adoption + onboarding funnel).

Tracks:
  • pageview events (anonymous + authenticated)
  • feature adoption (e.g., trade analyzer, league history)
  • onboarding funnel (account → email-verified → joined-league → first-lineup)
  • Dashboard return visit cadence

Collections:
  • analytics_pageviews — { user_id?, session_id, path, ref_path,
                            ts, viewport, device, ua }
  • analytics_events    — { user_id, event_name, props, ts }
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from collections import Counter

from fastapi import APIRouter, HTTPException, Request, Query

router = APIRouter(prefix="/analytics-ux", tags=["analytics-ux"])
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _require_admin(request: Request) -> dict:
    user = await _deps["get_current_user"](request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ─── Ingestion endpoints ────────────────────────────────────────────
@router.post("/pageview")
async def record_pageview(request: Request):
    """Fire-and-forget. Body: { path, ref_path, session_id, viewport, device }
    Auth optional — if a user is logged in we attach user_id."""
    body = await request.json()
    user_id = None
    try:
        u = await _deps["get_current_user"](request)
        user_id = str(u["_id"]) if u else None
    except Exception:
        pass
    await _db().analytics_pageviews.insert_one({
        "user_id": user_id,
        "session_id": (body.get("session_id") or "")[:64],
        "path": (body.get("path") or "")[:200],
        "ref_path": (body.get("ref_path") or "")[:200],
        "viewport": body.get("viewport"),
        "device": (body.get("device") or "")[:24],
        "ua": (request.headers.get("user-agent") or "")[:200],
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True}


@router.post("/event")
async def record_event(request: Request):
    """Body: { event_name, props? }. Auth required."""
    user = await _deps["get_current_user"](request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    body = await request.json()
    event_name = (body.get("event_name") or "").strip()
    if not event_name:
        raise HTTPException(status_code=400, detail="event_name required")
    await _db().analytics_events.insert_one({
        "user_id": str(user["_id"]),
        "event_name": event_name[:64],
        "props": body.get("props") or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True}


# ─── Personal "Your Activity" — Dashboard widget (Iter 218) ─────────
@router.get("/my-activity")
async def my_activity(request: Request, days: int = Query(7, ge=1, le=30)):
    """Returns the current user's pageview-derived activity for the
    dashboard widget. Auth-required, scoped to caller."""
    user = await _deps["get_current_user"](request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("_impersonation_mode"):
        # In view-as mode, show the TARGET user's activity (already
        # decoded by get_current_user); admin still gets their banner.
        pass
    user_id = str(user["_id"])
    db = _db()
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since = since_dt.isoformat()
    cursor = db.analytics_pageviews.find(
        {"user_id": user_id, "ts": {"$gte": since}}, {"path": 1, "ts": 1}
    )
    views = await cursor.to_list(10000)
    total = len(views)
    # Top paths
    counts: dict = {}
    for v in views:
        counts[v.get("path", "—")] = counts.get(v.get("path", "—"), 0) + 1
    top = sorted([{"path": p, "views": c} for p, c in counts.items()],
                  key=lambda x: -x["views"])[:5]
    # Sessions = distinct gaps > 30 min
    ts_list = []
    for v in views:
        try:
            ts_list.append(datetime.fromisoformat(v["ts"].replace("Z", "+00:00")))
        except Exception:
            continue
    ts_list.sort()
    sessions = 1 if ts_list else 0
    for i in range(1, len(ts_list)):
        if (ts_list[i] - ts_list[i - 1]).total_seconds() > 30 * 60:
            sessions += 1
    # Streak = consecutive days with ≥1 view going back from today
    days_with_view = {t.date() for t in ts_list}
    streak = 0
    today = datetime.now(timezone.utc).date()
    cur = today
    while cur in days_with_view:
        streak += 1
        cur -= timedelta(days=1)
    return {
        "window_days": days,
        "total_pageviews": total,
        "sessions_this_week": sessions,
        "top_paths": top,
        "streak_days": streak,
    }


# ─── Admin queries ───────────────────────────────────────────────────
@router.get("/pageviews-summary")
async def pageviews_summary(request: Request, days: int = Query(7, ge=1, le=90)):
    """Most/least visited paths + total views + DAU over the window."""
    await _require_admin(request)
    db = _db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"ts": {"$gte": since}}},
        {"$group": {"_id": "$path", "views": {"$sum": 1},
                     "uniques": {"$addToSet": "$user_id"}}},
        {"$project": {"path": "$_id", "views": 1,
                       "unique_users": {"$size": "$uniques"}, "_id": 0}},
        {"$sort": {"views": -1}},
    ]
    rows = await db.analytics_pageviews.aggregate(pipeline).to_list(200)
    total_views = sum(r["views"] for r in rows)
    # DAU over the window
    dau_pipeline = [
        {"$match": {"ts": {"$gte": since}, "user_id": {"$ne": None}}},
        {"$project": {"user_id": 1, "day": {"$substr": ["$ts", 0, 10]}}},
        {"$group": {"_id": {"day": "$day", "user_id": "$user_id"}}},
        {"$group": {"_id": "$_id.day", "dau": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    daily = []
    async for d in db.analytics_pageviews.aggregate(dau_pipeline):
        daily.append({"day": d["_id"], "dau": d["dau"]})
    return {
        "window_days": days,
        "total_views": total_views,
        "top_paths": rows[:25],
        "least_paths": rows[-15:] if len(rows) > 25 else [],
        "dau_series": daily,
    }


@router.get("/feature-adoption")
async def feature_adoption(request: Request, days: int = Query(30, ge=1, le=180)):
    """For each tracked feature path, return:
      • discovered: users who visited the page at least once
      • used:       users who fired the feature's `_use` event
      • returned:   users who used the feature >1 time
    The platform's historical-storytelling differentiator is included
    via the league-history page path."""
    await _require_admin(request)
    db = _db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    features = [
        {"key": "trade_analyzer", "path_regex": "^/trade-analyzer", "event": "trade_analyzer_run"},
        {"key": "league_history", "path_regex": "^/leagues/.*/history|^/league-history", "event": "league_history_view"},
        {"key": "live_scoring", "path_regex": "^/live-scoring", "event": "live_scoring_view"},
        {"key": "trade_block", "path_regex": "^/trade-block", "event": "trade_block_post"},
        {"key": "forum", "path_regex": "^/forum", "event": "forum_post"},
        {"key": "draft_room", "path_regex": "^/drafts/", "event": "draft_pick_made"},
    ]
    out = []
    eligible = [str(u["_id"]) async for u in db.users.find({"role": {"$ne": "admin"}}, {"_id": 1})]
    total_users = len(eligible)
    for f in features:
        # Discovered: unique users hitting the path
        discovered_ids = set()
        async for v in db.analytics_pageviews.find(
            {"ts": {"$gte": since}, "path": {"$regex": f["path_regex"]}, "user_id": {"$in": eligible}},
            {"user_id": 1},
        ):
            discovered_ids.add(v["user_id"])
        # Used (fired the event)
        used_ids = set()
        async for e in db.analytics_events.find(
            {"ts": {"$gte": since}, "event_name": f["event"], "user_id": {"$in": eligible}}, {"user_id": 1},
        ):
            used_ids.add(e["user_id"])
        # Returned (>=2 uses)
        ret_counts: Counter = Counter()
        async for e in db.analytics_events.find(
            {"ts": {"$gte": since}, "event_name": f["event"], "user_id": {"$in": eligible}}, {"user_id": 1},
        ):
            ret_counts[e["user_id"]] += 1
        returned_ids = {uid for uid, cnt in ret_counts.items() if cnt >= 2}
        out.append({
            "feature": f["key"],
            "discovered": len(discovered_ids),
            "used": len(used_ids),
            "returned": len(returned_ids),
            "discovered_pct": round(100.0 * len(discovered_ids) / total_users, 1) if total_users else 0,
            "used_pct": round(100.0 * len(used_ids) / total_users, 1) if total_users else 0,
        })
    return {"window_days": days, "total_users": total_users, "features": out}


@router.get("/onboarding-funnel")
async def onboarding_funnel(request: Request, days: int = Query(60, ge=1, le=365)):
    """Onboarding stage drop-offs computed entirely from user-doc fields
    + collections we already have. Stages:
       1. Account created
       2. Email verified
       3. Profile setup (avatar OR favourite_team set)
       4. Joined or created a league
       5. First lineup set (team.lineup has at least one slot filled)
    """
    await _require_admin(request)
    db = _db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    # Registration stores BSON datetimes; legacy ISO strings are normalized for this cohort.
    cohort = {"role": {"$ne": "admin"}, "$expr": {"$gte": [
        {"$convert": {"input": "$created_at", "to": "date", "onError": None, "onNull": None}}, since]}}
    total = await db.users.count_documents(cohort)

    email_verified = await db.users.count_documents({
        **cohort, "email_verified": True,
    })
    profile_set = await db.users.count_documents({
        **cohort,
        "$or": [{"avatar_url": {"$exists": True, "$ne": None}},
                {"favourite_team": {"$exists": True, "$ne": None}}],
    })
    # Joined / created a league = has a team
    user_ids_with_team = set()
    async for t in db.teams.find({}, {"owner_id": 1}):
        if t.get("owner_id"):
            user_ids_with_team.add(t["owner_id"])
    new_user_ids = set()
    async for u in db.users.find(
        cohort, {"_id": 1},
    ):
        new_user_ids.add(str(u["_id"]))
    joined_league = len(new_user_ids & user_ids_with_team)
    # First lineup set
    first_lineup_user_ids = set()
    async for t in db.teams.find(
        {"owner_id": {"$in": list(new_user_ids & user_ids_with_team)}, "lineup": {"$exists": True, "$ne": {}}},
        {"owner_id": 1, "lineup": 1},
    ):
        if (t.get("lineup") or {}):
            first_lineup_user_ids.add(t["owner_id"])
    first_lineup = len(first_lineup_user_ids)

    def pct(n):
        return round(100.0 * n / total, 1) if total else 0.0

    return {
        "window_days": days,
        "total_new_users": total,
        "stages": [
            {"stage": "account_created", "users": total, "pct_of_total": 100.0},
            {"stage": "email_verified", "users": email_verified, "pct_of_total": pct(email_verified)},
            {"stage": "profile_setup", "users": profile_set, "pct_of_total": pct(profile_set)},
            {"stage": "joined_league", "users": joined_league, "pct_of_total": pct(joined_league)},
            {"stage": "first_lineup_set", "users": first_lineup, "pct_of_total": pct(first_lineup)},
        ],
    }


@router.get("/engagement-cadence")
async def engagement_cadence(request: Request, days: int = Query(30, ge=1, le=180)):
    """Returns DAU/MAU + median sessions/user/week + median session length
    estimated from gaps between consecutive pageviews per user (<30 min
    apart = same session)."""
    await _require_admin(request)
    db = _db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    # Pull all pageviews in the window grouped by user
    user_views: dict = {}
    async for v in db.analytics_pageviews.find(
        {"ts": {"$gte": since}, "user_id": {"$ne": None}},
        {"user_id": 1, "ts": 1},
    ):
        user_views.setdefault(v["user_id"], []).append(v["ts"])
    sessions_per_user_per_week = []
    session_lengths_seconds = []
    for uid, tss in user_views.items():
        sorted_ts = sorted(tss)
        sessions = 1
        last = None
        sess_start = None
        for ts_str in sorted_ts:
            try:
                t = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                continue
            if last is None:
                last = t
                sess_start = t
                continue
            gap = (t - last).total_seconds()
            if gap > 30 * 60:
                # New session — record previous session length
                session_lengths_seconds.append((last - sess_start).total_seconds())
                sessions += 1
                sess_start = t
            last = t
        if last and sess_start:
            session_lengths_seconds.append((last - sess_start).total_seconds())
        weeks = max(1, days // 7)
        sessions_per_user_per_week.append(sessions / weeks)

    def _median(xs):
        if not xs:
            return 0
        xs = sorted(xs)
        m = len(xs) // 2
        return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2

    return {
        "window_days": days,
        "active_user_count": len(user_views),
        "median_sessions_per_user_per_week": round(_median(sessions_per_user_per_week), 2),
        "median_session_length_seconds": round(_median(session_lengths_seconds), 1),
    }

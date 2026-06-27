"""Draft inspection router — read-only endpoints.

Extracted from `routes/drafts.py` (iter 231c) to continue reducing the
drafts.py footprint after iter 231 already extracted draft-config. This
module owns every pure-read endpoint a client uses to render the Draft
Room without mutating any state:

  • GET /api/drafts                           — list drafts (optionally filtered)
  • GET /api/drafts/{id}                      — fetch a single draft
  • GET /api/drafts/{id}/board                — compute the snake/linear board
  • GET /api/drafts/{id}/stats                — pick velocity + floor-trade aggregates
  • GET /api/drafts/{id}/edit-preview         — diff preview for the Edit Draft dialog
  • GET /api/leagues/{id}/upcoming-drafts     — rolling-window picker

All endpoints use the same `setup(deps)` injection pattern as the rest
of the modular routers. See `server.py` wiring.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from draft_engine import build_draft_board, get_team_for_pick


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]


@router.get("/drafts")
async def get_drafts(
    league_id: Optional[str] = None,
    include_archived: bool = False,
    request: Request = None,
):
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    # Iter 228d — hide soft-deleted drafts by default
    if not include_archived:
        query["status"] = {"$ne": "archived"}
    drafts = await _db().drafts.find(query, {"team_map": 0}).sort("created_at", -1).to_list(100)
    for d in drafts:
        d["_id"] = str(d["_id"])
    return drafts



@router.get("/drafts/{draft_id}/edit-preview")
async def edit_draft_preview(
    draft_id: str, total_rounds: int = 0, request: Request = None
):
    """Iter 228q — Returns a "what-if I save these new rounds?" diff so
    the Edit Draft dialog can render an inline preview banner BEFORE
    the commissioner commits. Computes:
      - team_count
      - original_rounds + new_rounds
      - picks_added (per team and total)
      - picks_removed (per team and total)
      - traded_picks_preserved (rows with non-empty trade_history that
        survive a shrink)
    """
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league_id = draft.get("league_id")
    team_count = await _db().teams.count_documents({"league_id": league_id})
    original_rounds = int(draft.get("total_rounds") or 0)
    new_rounds = max(0, int(total_rounds or 0))
    picks_added_per_team = max(0, new_rounds - original_rounds)
    picks_removed_per_team = max(0, original_rounds - new_rounds)
    picks_added = picks_added_per_team * team_count
    picks_removed = picks_removed_per_team * team_count
    traded_preserved = 0
    if new_rounds < original_rounds:
        traded_preserved = await _db().draft_picks.count_documents({
            "draft_id": draft_id,
            "round": {"$gt": new_rounds},
            "trade_history": {"$exists": True, "$ne": []},
        })
    return {
        "draft_id": draft_id,
        "team_count": team_count,
        "original_rounds": original_rounds,
        "new_rounds": new_rounds,
        "picks_added_per_team": picks_added_per_team,
        "picks_removed_per_team": picks_removed_per_team,
        "picks_added": picks_added,
        "picks_removed": picks_removed,
        "traded_picks_preserved": traded_preserved,
    }


@router.get("/leagues/{league_id}/upcoming-drafts")
async def get_upcoming_drafts(
    league_id: str,
    days: int = 30,
    request: Request = None,
):
    """Iter 228n — Upcoming drafts within a rolling N-day window.

    Used by the Draft Room to populate a dropdown when multiple drafts
    are scheduled close together. Returns drafts sorted by
    `scheduled_time` ASC (soonest first). Past drafts and archived
    drafts are excluded.

    Iter 230w — Also surface `active` drafts (already started) so the
    picker doesn't hide a live draft a manager is mid-way through.
    Drafts are returned with ACTIVE first (most relevant to "where am
    I right now?"), then scheduled drafts in chronological order.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=max(1, min(days, 365)))

    query = {
        "league_id": league_id,
        # Iter 230w — Include "active" drafts alongside "scheduled" so
        # an in-progress draft remains visible in the picker (was
        # silently dropped before, which made the Draft Room
        # auto-select a future scheduled draft instead of the live
        # one).
        "status": {"$in": ["scheduled", "active"]},
    }
    cursor = _db().drafts.find(query, {"team_map": 0}).sort("scheduled_time", 1)
    raw = await cursor.to_list(50)

    upcoming = []
    for d in raw:
        # Iter 230w — Active drafts always surface (a live draft can
        # have a scheduled_time in the past). Scheduled drafts honour
        # the rolling N-day horizon.
        if d.get("status") == "active":
            d["_id"] = str(d["_id"])
            upcoming.append(d)
            continue
        sched = d.get("scheduled_time")
        if not sched:
            # Drafts without a scheduled_time still surface — they're
            # commissioner-initiated, not auto-launched. Place last.
            d["_id"] = str(d["_id"])
            upcoming.append(d)
            continue
        try:
            sched_dt = datetime.fromisoformat(str(sched).replace("Z", "+00:00"))
        except Exception:
            d["_id"] = str(d["_id"])
            upcoming.append(d)
            continue
        if sched_dt <= horizon and sched_dt >= now - timedelta(hours=2):
            # Allow a 2-hour lookback so drafts that started moments
            # ago still appear in the picker.
            d["_id"] = str(d["_id"])
            upcoming.append(d)

    # Iter 230w — Active drafts first (most relevant for "where am I
    # right now?"), then scheduled in chronological order. Within each
    # bucket, preserve the original soonest-first ordering.
    upcoming.sort(key=lambda d: (0 if d.get("status") == "active" else 1, d.get("scheduled_time") or ""))

    return {
        "league_id": league_id,
        "window_days": days,
        "count": len(upcoming),
        "drafts": upcoming,
    }


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft["_id"] = str(draft["_id"])
    return draft

@router.get("/drafts/{draft_id}/board")
async def get_draft_board(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    board = build_draft_board(
        draft["team_abbrs"],
        draft["total_rounds"],
        draft["snake_draft"],
        draft["picks"]
    )
    return {
        "board": board,
        "current_pick": draft["current_pick"],
        "status": draft["status"],
        "team_abbrs": draft["team_abbrs"],
        "total_rounds": draft["total_rounds"],
        "snake_draft": draft["snake_draft"],
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"]) if draft["team_abbrs"] else None
    }


@router.get("/drafts/{draft_id}/stats")
async def get_draft_stats(draft_id: str):
    """Iter 230aa — Compact stats summary for the Draft Live tile.

    Returns a single JSON blob the frontend can drop into a small
    sidebar strip without N round-trips. All metrics use the picks'
    `timestamp` field (set when the pick is committed) — the delta
    between consecutive timestamps is the proxy for "time taken to
    pick", and per-team aggregates surface the fastest/slowest manager.

    Shape:
    {
      "current_pick": 5,
      "total_picks": 240,
      "picks_made": 4,
      "avg_seconds_per_pick": 42.0,
      "fastest": {"team": "TOR", "avg_seconds": 18.5, "picks": 3},
      "slowest": {"team": "HC",  "avg_seconds": 201.0, "picks": 2},
      "floor_trades": 4
    }

    Fields that can't be computed (e.g. no picks yet → no deltas) are
    returned as `None` rather than omitted so the frontend has stable
    keys.
    """
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    team_abbrs = draft.get("team_abbrs") or []
    total_rounds = int(draft.get("total_rounds") or 0)
    total_picks = total_rounds * len(team_abbrs)
    picks: list[dict] = draft.get("picks") or []
    picks_made = len(picks)

    # Parse pick timestamps once.
    def _parse(ts) -> Optional[datetime]:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return None

    # Anchor for the FIRST pick's elapsed time: the draft's started_at
    # if present, otherwise scheduled_time, otherwise skip (delta is
    # undefined). Pick #N's elapsed = pick[N].timestamp - prev_anchor.
    started_at = _parse(draft.get("started_at")) or _parse(draft.get("scheduled_time"))

    # Sort picks by overall just in case storage order ever drifts.
    sorted_picks = sorted(picks, key=lambda p: int(p.get("overall") or 0))

    deltas: list[float] = []
    per_team_deltas: dict[str, list[float]] = {}
    prev_ts = started_at
    for p in sorted_picks:
        ts = _parse(p.get("timestamp"))
        if ts and prev_ts:
            d = (ts - prev_ts).total_seconds()
            if 0 < d < 24 * 3600:  # ignore absurd gaps (>24h pauses)
                deltas.append(d)
                team = p.get("team")
                if team:
                    per_team_deltas.setdefault(team, []).append(d)
        if ts:
            prev_ts = ts

    avg = (sum(deltas) / len(deltas)) if deltas else None

    fastest = slowest = None
    if per_team_deltas:
        per_team_avg = [
            (team, sum(arr) / len(arr), len(arr))
            for team, arr in per_team_deltas.items()
            if arr
        ]
        if per_team_avg:
            f = min(per_team_avg, key=lambda x: x[1])
            s = max(per_team_avg, key=lambda x: x[1])
            fastest = {"team": f[0], "avg_seconds": round(f[1], 1), "picks": f[2]}
            slowest = {"team": s[0], "avg_seconds": round(s[1], 1), "picks": s[2]}

    # Floor trades — completed trades whose `assets` include any draft-
    # pick reference for this league/draft. We count distinct trade docs
    # with status approved/completed that mention this draft.
    league_id = draft.get("league_id")
    floor_trades = 0
    latest_floor_trade = None
    if league_id:
        try:
            trade_query = {
                "league_id": str(league_id),
                "status": {"$in": ["approved", "completed", "auto_approved"]},
                "$or": [
                    {"draft_id": draft_id},
                    {"draft_id": str(draft_id)},
                    # Legacy: trades carrying any pick asset on this league
                    # during the draft window — best-effort fallback.
                    {"assets": {"$elemMatch": {"type": "draft_pick", "league_id": str(league_id)}}},
                ],
            }
            floor_trades = await _db().trades.count_documents(trade_query)
            # Iter 230ag — Pull the single most recent floor trade so
            # the Draft Live tile can render a "Latest: …" tooltip
            # without a second API call. Sort by approved/completed
            # timestamp (falls back to created_at).
            if floor_trades > 0:
                latest = await _db().trades.find_one(
                    trade_query,
                    sort=[("updated_at", -1), ("created_at", -1)],
                )
                if latest:
                    # Render the abbr-by-abbr summary client-side so we
                    # don't have to fan out N team lookups here. Just
                    # pass through the raw shape the stats consumer needs.
                    assets = latest.get("assets") or []
                    team_a_id = latest.get("team_a_id") or latest.get("proposer_team_id")
                    team_b_id = latest.get("team_b_id") or latest.get("target_team_id")
                    # Resolve abbrs via the draft's `team_map` (already
                    # in memory) — falls back to the team's full name.
                    team_map = draft.get("team_map") or {}
                    abbr_by_team_id: dict[str, str] = {}
                    for a, meta in team_map.items():
                        tid = (meta or {}).get("id")
                        if tid:
                            abbr_by_team_id[str(tid)] = a
                    a_abbr = abbr_by_team_id.get(str(team_a_id) if team_a_id else "", "")
                    b_abbr = abbr_by_team_id.get(str(team_b_id) if team_b_id else "", "")
                    # Compact "TEAM-A picks ↔ TEAM-B picks" summary.
                    a_picks = [
                        f"#{x.get('pick_number') or x.get('overall') or '?'}"
                        for x in assets
                        if x.get("type") == "draft_pick" and (str(x.get("from_team_id") or "") == str(team_a_id))
                    ]
                    b_picks = [
                        f"#{x.get('pick_number') or x.get('overall') or '?'}"
                        for x in assets
                        if x.get("type") == "draft_pick" and (str(x.get("from_team_id") or "") == str(team_b_id))
                    ]
                    ts = latest.get("updated_at") or latest.get("created_at")
                    seconds_ago = None
                    if ts:
                        try:
                            ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                            seconds_ago = max(0, int((datetime.now(timezone.utc) - ts_dt).total_seconds()))
                        except Exception:
                            pass
                    latest_floor_trade = {
                        "team_a_abbr": a_abbr or None,
                        "team_b_abbr": b_abbr or None,
                        "team_a_picks": a_picks,
                        "team_b_picks": b_picks,
                        "seconds_ago": seconds_ago,
                    }
        except Exception:
            floor_trades = 0
            latest_floor_trade = None

    return {
        "current_pick": int(draft.get("current_pick") or 1),
        "total_picks": total_picks,
        "picks_made": picks_made,
        "avg_seconds_per_pick": round(avg, 1) if avg is not None else None,
        "fastest": fastest,
        "slowest": slowest,
        "floor_trades": int(floor_trades),
        "latest_floor_trade": latest_floor_trade,
    }

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
    include_orphans: bool = False,
    request: Request = None,
):
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    # Iter 228d — hide soft-deleted drafts by default
    if not include_archived:
        query["status"] = {"$ne": "archived"}
    drafts = await _db().drafts.find(query, {"team_map": 0}).sort("created_at", -1).to_list(100)
    # Iter 232N.70 — Filter out orphan / stub draft docs (no scheduling
    # or pick-order signal) so free-agent widgets and dashboards don't
    # falsely display "draft is running" for a league whose
    # commissioner never actually set a draft up.
    if not include_orphans:
        from utils.draft_lock import _looks_like_real_draft
        drafts = [d for d in drafts if _looks_like_real_draft(d)]
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
    # Iter 232N.71 — Filter out orphan / stub drafts so the picker
    # doesn't offer a phantom draft the commissioner never scheduled.
    from utils.draft_lock import _looks_like_real_draft
    raw = [d for d in raw if _looks_like_real_draft(d)]

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

    # Older records can predate the materialized board fields.
    team_abbrs = draft.get("team_abbrs")
    if team_abbrs is None:
        teams = await _db().teams.find({"league_id": draft.get("league_id")}).sort("draft_position", 1).to_list(100)
        team_abbrs = [team.get("logo_abbr") or team.get("abbreviation") or team.get("name", "Team") for team in teams]
    total_rounds = draft.get("total_rounds") or draft.get("rounds") or 1
    snake_draft = draft.get("snake_draft", draft.get("draft_type", "snake") == "snake")
    picks = draft.get("picks") or []
    current_pick = draft.get("current_pick") or 1
    board = build_draft_board(
        team_abbrs,
        total_rounds,
        snake_draft,
        picks
    )
    return {
        "board": board,
        "current_pick": current_pick,
        "status": draft.get("status", "scheduled"),
        "team_abbrs": team_abbrs,
        "total_rounds": total_rounds,
        "snake_draft": snake_draft,
        "on_the_clock": get_team_for_pick(team_abbrs, current_pick, snake_draft) if team_abbrs else None
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



# ─── Iter 231t — GET /drafts/{draft_id}/eligible-players ──────────────


@router.get("/drafts/{draft_id}/eligible-players")
async def get_draft_eligible_players(
    draft_id: str,
    request: Request,
    search: Optional[str] = None,
    position: Optional[str] = None,
    undrafted_only: bool = False,
    page: int = 1,
    limit: int = 50,
):
    """Iter 231t — Relocated here from `routes/drafts.py`.

    Returns the paginated list of players eligible for the next pick:
      • Excludes anyone already drafted in this draft (always)
      • Excludes anyone ever drafted in this league when
        `exclude_previously_drafted == True`
      • Filters to prospects only when `minors_eligibility_required`
      • Honours the draft's `player_criteria` ("entry" → prospects,
        "open" or anything else → non-prospect skaters/goalies)
      • Sorts by `points DESC` and stamps a 1-based `ranking` so the
        Draft Board can show the same ordering across pages.
    """
    user = await _deps["get_current_user"](request)
    try:
        draft_oid = ObjectId(draft_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft ID")
    draft = await _db().drafts.find_one({"_id": draft_oid})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    from routes.league_guards import require_league_member
    authorized_league = await require_league_member(_db(), user, draft.get("league_id") or "")

    # Get already-drafted player IDs (in THIS draft only)
    drafted_ids = [p["player_id"] for p in draft.get("picks", []) if p.get("player_id")]

    # Iter 228n — Optional eligibility filters surfaced as draft-config
    # checkboxes. `exclude_previously_drafted` removes any player ever
    # drafted by ANY team in this league (full historical audit, per the
    # user's preference). `minors_eligibility_required` keeps only
    # players flagged `minor_eligible: true`.
    league_id_str = draft.get("league_id")
    if draft.get("exclude_previously_drafted") and league_id_str:
        historical = await _db().drafts.find(
            {
                "league_id": league_id_str,
                "_id": {"$ne": draft["_id"]},
                "status": {"$in": ["scheduled", "active", "completed"]},
            },
            {"picks": 1},
        ).to_list(500)
        for past in historical:
            for p in past.get("picks") or []:
                pid = p.get("player_id")
                if pid:
                    drafted_ids.append(pid)

    query = {}
    if drafted_ids:
        unique_oids = list({pid for pid in drafted_ids})
        query["_id"] = {"$nin": [ObjectId(pid) for pid in unique_oids]}

    if draft.get("minors_eligibility_required"):
        query["minor_eligible"] = True

    # Iter 170o / 231aj — Criteria-aware filter. Normalises the
    # draft-config string to one of: `entry` / `prospects` (synonyms,
    # both filter to player_type=prospect), `all` (include BOTH NHL
    # and prospects — no player_type filter), or `open` / anything
    # else (only non-prospects). The frontend uses `prospects` and
    # `all`; legacy drafts may still use `entry` / `open`.
    raw_crit = draft.get("player_criteria")
    if isinstance(raw_crit, list):
        criteria = (raw_crit[0] if raw_crit else "open")
    else:
        criteria = raw_crit or "open"
    criteria = str(criteria).lower()
    if criteria in ("entry", "prospects"):
        query["player_type"] = "prospect"
    elif criteria == "all":
        # No player_type filter — include both NHL skaters/goalies
        # AND prospects in the eligibility list.
        pass
    else:
        query["player_type"] = {"$ne": "prospect"}

    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}}
        ]
    if position and position != "all":
        query["position"] = position

    # ─── Iter 232N — Previously-drafted set (for `undrafted` flag) ───
    from routes.player_status import (
        compute_player_status_flags,
        get_previously_drafted_pids,
    )
    previously_drafted_pids: set = await get_previously_drafted_pids(
        _db(), league_id_str, exclude_draft_id=draft["_id"],
    )

    # Iter 232N.2 — `undrafted_only` query param filters the eligible
    # list to players who have never been picked in any prior draft
    # in this league. Injected into the Mongo query BEFORE it fires so
    # pagination + total counts reflect the filter.
    if undrafted_only and league_id_str:
        existing_id = query.get("_id")
        already_nin: list = []
        if isinstance(existing_id, dict) and "$nin" in existing_id:
            already_nin = list(existing_id["$nin"])
        combined = {oid for oid in already_nin}
        for pid in previously_drafted_pids:
            try:
                combined.add(ObjectId(pid))
            except Exception:
                continue
        if combined:
            query["_id"] = {"$nin": list(combined)}

    skip = (page - 1) * limit
    from services.player_pool import pool_query
    league_pool = authorized_league
    query = {"$and": [query, pool_query(league_pool or {})]}
    players = await _db().players.find(query).sort([("points", -1), ("_id", 1)]).skip(skip).limit(limit).to_list(limit)
    total = await _db().players.count_documents(query)

    result = []
    for i, p in enumerate(players):
        # Iter 170g — surface a best-effort NHL headshot URL based on
        # nhl_id + team. Frontend falls back to an initials circle if
        # the image 404s.
        # Iter 173 — Prospects don't have NHL headshots; skip the URL so
        # the frontend renders the initials avatar instead of a broken img.
        player_type = p.get("player_type") or "skater"
        is_prospect = player_type == "prospect"
        headshot = (
            f"https://assets.nhle.com/mugs/nhl/20252026/{p.get('team', 'NHL')}/{p.get('nhl_id', '')}.png"
            if p.get("nhl_id") and not is_prospect else None
        )
        # For prospects, the "league" they play in is their amateur league
        # (OHL/WHL/SHL/…), not "NHL". For NHL players, fall back to "NHL".
        league_label = p.get("amateur_league") if is_prospect else "NHL"
        if not league_label:
            league_label = "NHL"
        # display_name strips the "(Prospect)" suffix added at seed time so
        # the UI shows the real human name.
        display_name = p.get("display_name") or p["name"]
        pid_str = str(p["_id"])
        # ─── Iter 232N — Player status flags for the badge layer ──
        # Uses the shared `compute_player_status_flags` helper so every
        # consumer emits the same shape. `undrafted` is stamped only
        # when we have a league_id (otherwise left False).
        status_flags = compute_player_status_flags(
            p, previously_drafted_pids if league_id_str else None,
        )
        result.append({
            "id": pid_str,
            "name": display_name,
            "position": p["position"],
            "nhlTeam": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "age": p.get("age", 0),
            "league": league_label,
            "gp": p.get("games_played", 0),
            "g": p.get("goals", 0),
            "a": p.get("assists", 0),
            "pts": p.get("points", 0),
            "plus_minus": p.get("plus_minus", 0),
            "ranking": skip + i + 1,
            "drafted": False,
            "headshot": headshot,
            "nhl_id": p.get("nhl_id"),
            # Iter 173 — expose prospect status so the Draft Room + Player
            # Cards can render a "Minor-eligible" affordance when the
            # league has minors_enabled. `minor_eligible` is a derived
            # convenience flag that mirrors `player_type == "prospect"`.
            "player_type": player_type,
            "minor_eligible": is_prospect,
            # Iter 232N — Symbol-layer flags.
            "status_flags": status_flags,
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}



# ─── Iter 231v — Endpoints relocated from drafts.py ────────────────────


@router.get("/drafts/{league_id}/picks")
async def get_draft_picks(
    league_id: str,
    year: Optional[int] = None,
    draft_id: Optional[str] = None,
):
    """Iter 231v — Relocated from `routes/drafts.py`.

    Lists the league's draft_picks rows (slot grid for the trade
    center + Draft Board) and decorates each with pending pick-upgrade
    clauses (executed trades whose upgrade hasn't resolved yet) so the
    Board can render a "Protected: top-N / Conditional upgrade" badge.

    Iter 232N.39 — `draft_id` filter added so the Draft Board can
    show pick ownership for a SPECIFIC scheduled draft (Summer Entry
    vs Winter Entry vs Inaugural) rather than aggregating every draft
    in a year into a single misleading grid.
    """
    db = _db()
    query = {"league_id": league_id}
    if year:
        query["year"] = int(year)
    if draft_id:
        query["draft_id"] = draft_id
    # Iter 232N.39 — Bumped list limit from 1000 to 10000. A single
    # 24-team × 55-round draft is 1,320 rows; a league with 3 drafts
    # in one year easily exceeds the old cap and silently dropped
    # picks off the tail.
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(10000)

    # Build a lookup of pending pick-upgrade clauses (status=executed,
    # applied_at/failed_at not yet set) so the DraftBoard can render a
    # "Protected: top-N" / "Conditional upgrade" badge before the lottery
    # resolves.
    trades = await db.trades.find({
        "league_id": league_id,
        "status": "executed",
        "pick_upgrades": {"$exists": True, "$ne": []},
    }, {"_id": 1, "pick_upgrades": 1}).to_list(500)
    pending: dict = {}
    for t in trades:
        for u in (t.get("pick_upgrades") or []):
            if u.get("applied_at") or u.get("failed_at"):
                continue
            pid = u.get("pick_id")
            if not pid:
                continue
            cond = u.get("condition") or {}
            pending.setdefault(pid, []).append({
                "trade_id": str(t["_id"]),
                "new_round": u.get("new_round"),
                "new_year": u.get("new_year"),
                "subject_type": cond.get("subject_type"),
                "metric": cond.get("metric"),
                "operator": cond.get("operator"),
                "threshold": cond.get("threshold"),
                "description": cond.get("description") or u.get("description"),
            })

    for p in picks:
        p["_id"] = str(p["_id"])
        p["pending_protections"] = pending.get(p["_id"], [])
    return {"league_id": league_id, "year": year, "draft_id": draft_id, "picks": picks}


# ─── Iter 204 — Related trades for a completed draft ────────────────────────
# Surfaces, for a single draft, every executed trade that affected
# either (a) a drafted player or (b) any pick used in or scheduled for
# this draft. Powers the "Related Trades" section on the Draft History
# page so managers can audit how a draft was shaped by trades.
@router.get("/drafts/{draft_id}/related-trades")
async def get_draft_related_trades(draft_id: str):
    db = _db()
    if not ObjectId.is_valid(draft_id):
        raise HTTPException(status_code=400, detail="Invalid draft id")
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league_id = draft.get("league_id")
    picks = draft.get("picks") or []
    drafted_player_ids = {str(p.get("player_id")) for p in picks if p.get("player_id")}

    # Player-trade match: any executed trade where a player asset
    # references a player_id that appears in this draft.
    # Pick-trade match: any `is_in_draft_pick_trade=true` trade for the
    # league (these were proposed/executed in the context of this draft
    # cycle). Status filter is lenient — surface vetoed/expired ones
    # too so users see "what was attempted".
    all_trades = await db.trades.find({"league_id": league_id}).sort("created_at", -1).to_list(500)

    out = []
    for t in all_trades:
        proposer_assets = t.get("proposer_assets") or []
        receiver_assets = t.get("receiver_assets") or []
        is_pick_trade = bool(t.get("is_in_draft_pick_trade"))
        affected_player_ids: list[str] = []
        affected_picks: list[dict] = []

        for asset in proposer_assets + receiver_assets:
            atype = asset.get("type") or asset.get("asset_type")
            if atype == "player":
                pid = str(asset.get("player_id") or "")
                if pid and pid in drafted_player_ids:
                    affected_player_ids.append(pid)
            elif atype == "pick":
                affected_picks.append({
                    "pick_id": asset.get("pick_id"),
                    "round": asset.get("round"),
                    "year": asset.get("year"),
                    "original_team_id": asset.get("original_team_id"),
                })

        relevance = None
        if affected_player_ids and t.get("status") == "executed":
            relevance = "player"
        elif is_pick_trade:
            relevance = "pick"

        if not relevance:
            continue

        # Hydrate proposer / receiver team display names
        async def _team_name(tid):
            if not tid or not ObjectId.is_valid(str(tid)):
                return None
            doc = await db.teams.find_one({"_id": ObjectId(str(tid))}, {"name": 1, "logo_abbr": 1})
            return doc and (doc.get("name") or doc.get("logo_abbr"))

        # Hydrate affected drafted-player names (snapshot lookup from
        # the draft's picks list to avoid an extra players collection
        # round-trip).
        affected_players_meta = []
        for pid in set(affected_player_ids):
            match = next((pk for pk in picks if str(pk.get("player_id")) == pid), None)
            if match:
                affected_players_meta.append({
                    "player_id": pid,
                    "name": (match.get("player") or {}).get("name") or "Unknown",
                    "drafted_overall": match.get("overall"),
                    "drafted_by_team": match.get("team"),
                })

        out.append({
            "trade_id": str(t["_id"]),
            "relevance": relevance,
            "status": t.get("status"),
            "is_in_draft_pick_trade": is_pick_trade,
            "created_at": t.get("created_at"),
            "executed_at": t.get("executed_at"),
            "proposer_team_id": str(t.get("proposer_team_id") or ""),
            "receiver_team_id": str(t.get("receiver_team_id") or ""),
            "proposer_team_name": await _team_name(t.get("proposer_team_id")),
            "receiver_team_name": await _team_name(t.get("receiver_team_id")),
            "affected_players": affected_players_meta,
            "affected_picks": affected_picks,
            "votes": t.get("votes") or {},
            "post_review_action": t.get("post_review_action"),
        })

    return {"draft_id": draft_id, "league_id": league_id, "related_trades": out}


# ─── Iter 205 — Draft player stats (career totals + medal ranking) ─────────
# Aggregates career career totals + FP/FP/G for every player picked in
# a draft so the Draft History page can:
#   1. Expand a pick row to show stats-to-date
#   2. Render compact key-stat strips inline in the Pick Log
#   3. Award gold/silver/bronze medals to the top-3 producers PER
#      position group (C, W combining LW/RW, D, G), ranked by total
#      career fantasy points against the league's scoring config.
@router.get("/drafts/{draft_id}/player-stats")
async def get_draft_player_stats(draft_id: str):
    db = _db()
    if not ObjectId.is_valid(draft_id):
        raise HTTPException(status_code=400, detail="Invalid draft id")
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league_id = draft.get("league_id")
    league = await db.leagues.find_one({"_id": ObjectId(league_id)}) if ObjectId.is_valid(str(league_id)) else None
    scoring_format = (league or {}).get("scoring_format", "head_to_head")
    is_h2h = "head_to_head" in scoring_format or "h2h" in scoring_format

    # Build the player_id → (overall, position, name) map from the
    # draft's picks list. We use the position recorded at draft time
    # (rather than re-resolving from /players) so backwards-compat is
    # preserved for legacy drafts.
    picks = draft.get("picks") or []
    rows: list[dict] = []
    for p in picks:
        pid = p.get("player_id")
        if not pid:
            continue
        rows.append({
            "overall": p.get("overall"),
            "player_id": pid,
            "drafted_pos": (p.get("player") or {}).get("position") or "—",
            "name": (p.get("player") or {}).get("name") or "Unknown",
        })

    # Pull each player's stats directly off the players collection.
    # On-doc fields (games_played, goals, assists, points, etc.) hold
    # season-to-date totals populated by the NHL sync. These are the
    # same fields powering the player browse / live scoring screens,
    # so a draft's medals stay in lockstep with the rest of the app.
    player_object_ids = [ObjectId(r["player_id"]) for r in rows if ObjectId.is_valid(str(r["player_id"]))]
    player_docs = {}
    if player_object_ids:
        async for doc in db.players.find({"_id": {"$in": player_object_ids}}):
            player_docs[str(doc["_id"])] = doc

    # Lazy import to share the same fpts calculator the other player
    # endpoints use against league scoring config.
    from routes.players import _scoring_cfg_for, _calc_fpts
    scoring_cfg = await _scoring_cfg_for(league_id)

    out_rows: list[dict] = []
    for r in rows:
        pdoc = player_docs.get(str(r["player_id"])) or {}
        is_goalie = (r["drafted_pos"] or pdoc.get("position") or "") == "G"

        if is_goalie:
            stats = {
                "wins": pdoc.get("wins", 0),
                "losses": pdoc.get("losses", 0),
                "saves": pdoc.get("saves", 0),
                "shutouts": pdoc.get("shutouts", 0),
                "goals_against": pdoc.get("goals_against", 0),
            }
            display = {
                "games_played": pdoc.get("games_played", 0),
                "wins": pdoc.get("wins", 0),
                "losses": pdoc.get("losses", 0),
                "shutouts": pdoc.get("shutouts", 0),
                "save_pct": pdoc.get("save_pct", 0),
                "goals_against_avg": pdoc.get("goals_against_avg", 0),
            }
        else:
            stats = {
                "goals": pdoc.get("goals", 0),
                "assists": pdoc.get("assists", 0),
                "points": pdoc.get("points", 0),
                "plus_minus": pdoc.get("plus_minus", 0),
                "shots": pdoc.get("shots", 0),
                "ppg": pdoc.get("power_play_goals", 0),
                "ppp": pdoc.get("power_play_points", 0),
                "shg": pdoc.get("short_handed_goals", 0),
                "pim": pdoc.get("penalty_minutes", 0),
            }
            display = {
                "games_played": pdoc.get("games_played", 0),
                "goals": pdoc.get("goals", 0),
                "assists": pdoc.get("assists", 0),
                "points": pdoc.get("points", 0),
                "plus_minus": pdoc.get("plus_minus", 0),
                "shots": pdoc.get("shots", 0),
                "shooting_pct": pdoc.get("shooting_pct", 0),
            }
        gp = pdoc.get("games_played") or 0
        fpts = _calc_fpts(stats, is_goalie, scoring_cfg) if pdoc else 0.0
        fpts = round(float(fpts or 0), 2)
        fpg = round(fpts / gp, 2) if gp else 0.0

        out_rows.append({
            "overall": r["overall"],
            "player_id": r["player_id"],
            "name": r["name"],
            "position": r["drafted_pos"],
            "is_goalie": is_goalie,
            "career_stats": display,
            "fantasy_points": fpts,
            "fantasy_points_per_game": fpg,
            "medal": None,
            "position_group": None,
        })

    # Group by position_group (C, W [combines LW/RW], D, G).
    def _pos_group(pos: str) -> str:
        p = (pos or "").upper()
        if p == "C":
            return "C"
        if p in ("LW", "RW", "W"):
            return "W"
        if p == "D":
            return "D"
        if p == "G":
            return "G"
        return "OTHER"

    groups: dict[str, list[dict]] = {}
    for row in out_rows:
        g = _pos_group(row["position"])
        row["position_group"] = g
        groups.setdefault(g, []).append(row)

    # Award medals — top 3 by total fantasy_points in each group.
    for g, items in groups.items():
        items.sort(
            key=lambda x: (
                -float(x["fantasy_points"] or 0),
                -float(x["fantasy_points_per_game"] or 0),
                x["overall"] or 9999,
            )
        )
        for idx, item in enumerate(items[:3]):
            if (item["fantasy_points"] or 0) <= 0:
                continue
            item["medal"] = ["gold", "silver", "bronze"][idx]

    return {
        "draft_id": draft_id,
        "league_id": league_id,
        "scoring_format": scoring_format,
        "is_h2h": is_h2h,
        "picks": sorted(out_rows, key=lambda x: x.get("overall") or 0),
    }


# Iter 166 — Per-team draft picks (currently owned). Powers the
# Roster page's Draft Picks section + the team's pick provenance chips.
@router.get("/teams/{team_id}/draft-picks")
async def get_team_draft_picks(team_id: str, request: Request, year: Optional[int] = None):
    """Return every pick currently owned by this team.

    A pick is considered "currently owned" when its `current_team_id`
    matches the requested team_id — regardless of who held the slot
    originally. Each pick carries its full `trade_history` so the
    front-end can render the provenance chain.

    Iter 228o — Each pick is decorated with `draft_id` + `draft_name`
    so the Roster page can group picks by parent draft (e.g. "TFHL
    Inaugural Draft" vs "TFHL 2026 Entry Draft") instead of just by
    calendar year. Mapping prefers an explicit `pick.draft_id` field
    (set on newly-seeded picks), then falls back to matching the pick's
    `(league_id, year)` against the league's drafts collection.
    """
    db = _db()
    # SEC-002 — auth + league-membership guard
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)}, {"league_id": 1})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    from routes.league_guards import require_league_member
    await require_league_member(db, user, team.get("league_id") or "")
    query = {"current_team_id": team_id}
    if year:
        query["year"] = int(year)
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(1000)

    # ─── Build a year → (draft_id, draft_name) lookup for fallback ────
    league_ids = list({p.get("league_id") for p in picks if p.get("league_id")})
    drafts_by_year: dict = {}     # (league_id, year) → (draft_id, name)
    drafts_by_id: dict = {}       # draft_id → name
    drafts_meta_by_id: dict = {}  # draft_id → {name, scheduled_time}
    if league_ids:
        all_drafts = await db.drafts.find(
            {"league_id": {"$in": league_ids},
             "status": {"$ne": "archived"}},
            {"_id": 1, "league_id": 1, "name": 1, "scheduled_time": 1,
             "season": 1, "draft_type": 1},
        ).to_list(500)
        for d in all_drafts:
            did = str(d["_id"])
            name = d.get("name") or "Untitled Draft"
            drafts_by_id[did] = name
            # Iter 228s — also stash scheduled_time for chronological sort.
            drafts_meta_by_id[did] = {
                "name": name,
                "scheduled_time": d.get("scheduled_time"),
            }
            # Derive year for the draft
            yr = None
            sched = d.get("scheduled_time")
            if sched:
                try:
                    yr = int(str(sched)[:4])
                except Exception:
                    pass
            if yr is None and d.get("season"):
                try:
                    yr = int(str(d["season"]).split("-")[0])
                except Exception:
                    pass
            if yr is not None:
                key = (d["league_id"], yr)
                if key not in drafts_by_year:
                    drafts_by_year[key] = (did, name)

    for p in picks:
        p["_id"] = str(p["_id"])
        explicit_did = p.get("draft_id")
        if explicit_did and explicit_did in drafts_by_id:
            p["draft_name"] = drafts_by_id[explicit_did]
            p["draft_scheduled_time"] = (drafts_meta_by_id.get(explicit_did) or {}).get("scheduled_time")
        else:
            key = (p.get("league_id"), int(p.get("year") or 0))
            mapped = drafts_by_year.get(key)
            if mapped:
                p["draft_id"] = mapped[0]
                p["draft_name"] = mapped[1]
                p["draft_scheduled_time"] = (drafts_meta_by_id.get(mapped[0]) or {}).get("scheduled_time")
            else:
                p["draft_name"] = f"{p.get('year') or 'Unknown'} Draft"
                p["draft_scheduled_time"] = None

    return {"team_id": team_id, "year": year, "picks": picks}

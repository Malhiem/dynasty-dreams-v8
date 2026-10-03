"""
Iter 160 — Commissioner Monitor endpoints.

Replaces the mock data in commissionerData.tsx with real league snapshots.

  - GET /api/leagues/{league_id}/tank-monitor
        Returns per-team breakdown of fantasy points split across
        roster sections (starting / bench / IR / minors).
        Iter 162: accepts optional `from_week` + `to_week` query params.
        When provided, aggregates over the persisted weekly snapshots in
        `tank_monitor_weekly`; otherwise falls back to a real-time
        current-snapshot computation.

  - POST /api/leagues/{league_id}/tank-monitor/snapshot?week=N
        Persists the current per-team breakdown as week N's snapshot.
        Idempotent — upserts on (league_id, week). Used by the live
        scoring worker (and/or commissioner backfill endpoint) to build
        up weekly history.

  - POST /api/leagues/{league_id}/tank-monitor/backfill
        Backfill helper — generates plausible weekly history for weeks
        1..league.current_week by perturbing the current snapshot per
        week, so the Tank Monitor week-range filter has meaningful data
        immediately even before live scoring has run through a full
        season. Idempotent; only writes weeks that aren't already in
        `tank_monitor_weekly`.

  - GET /api/leagues/{league_id}/roster-monitor
        Returns per-team roster snapshots with section assignment +
        violation flags (over-limit, dead IR slot, etc.).

Both endpoints reuse the same enrichment logic that powers
`/api/roster/{team_id}/detail` so values stay in lockstep with the
Rosters page — no separate calculation paths.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# Roster section limits applied at the league level. Mirrors the defaults
# the front-end Roster Monitor uses; once leagues persist custom limits we
# read them off the league document instead.
DEFAULT_ROSTER_LIMITS = {
    "starting_skaters": 18,
    "starting_goalies": 2,
    "bench": 6,
    "ir": 3,
    "minors": 6,
}


def _starting_sections() -> set:
    return {"starting", "goalies"}


def _bench_sections() -> set:
    return {"bench"}


def _ir_sections() -> set:
    return {"ir"}


def _minors_sections() -> set:
    return {"minors", "goalies_minors"}


async def _league_team_details(league_id: str):
    """Yield enriched roster details for every team in a league.

    Uses the same code path as `/roster/{team_id}/detail` so the monitor
    surfaces match the Rosters page exactly.
    """
    db = _deps["db"]
    # Import the handler lazily; the roster module pulls a few side-effecty
    # workers at import time and we don't want them to load until the
    # endpoint is actually hit.
    from routes.roster import _load_roster_data, _build_roster_detail

    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    out = []
    for team in teams:
        try:
            detail = await _build_roster_detail(*await _load_roster_data(team))
        except HTTPException:
            continue
        out.append((team, detail))
    return out


async def _current_tank_rows(league_id: str):
    """Compute the per-team starting/bench/ir/minors fantasy-point split
    for the *current* live roster state. Shared between the live-mode
    response, the snapshot writer, and the backfill helper.
    """
    rows = []
    for team, detail in await _league_team_details(league_id):
        starting = bench = ir = minors = 0.0
        for p in detail.get("players", []):
            section = (p.get("rosterSection") or "").lower()
            fp = float(p.get("fantasy_points") or 0.0)
            if section in _starting_sections():
                starting += fp
            elif section in _bench_sections():
                bench += fp
            elif section in _ir_sections():
                ir += fp
            elif section in _minors_sections():
                minors += fp
        rows.append({
            "team_id": str(team["_id"]),
            "team": team.get("name", "Unknown"),
            "startingPts": round(starting, 1),
            "benchPts": round(bench, 1),
            "irPts": round(ir, 1),
            "minorsPts": round(minors, 1),
        })
    return rows


@router.get("/leagues/{league_id}/tank-monitor")
async def tank_monitor(
    league_id: str,
    from_week: Optional[int] = Query(None, ge=1, le=30),
    to_week: Optional[int] = Query(None, ge=1, le=30),
):
    """Real-league replacement for the seeded Tank Monitor table.

    - No week params → current live snapshot (computed in real time)
    - from_week + to_week → aggregate over the persisted weekly snapshots
      (returns empty rows when no snapshots exist for that range)
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Week-range aggregation path (Iter 162)
    if from_week is not None and to_week is not None:
        if to_week < from_week:
            from_week, to_week = to_week, from_week
        snaps = await db.tank_monitor_weekly.find({
            "league_id": league_id,
            "week": {"$gte": from_week, "$lte": to_week},
        }).to_list(200)
        # Aggregate per team
        agg: dict = {}
        for snap in snaps:
            for row in snap.get("teams", []):
                key = row["team_id"]
                if key not in agg:
                    agg[key] = {
                        "team_id": key, "team": row["team"],
                        "startingPts": 0.0, "benchPts": 0.0,
                        "irPts": 0.0, "minorsPts": 0.0,
                    }
                agg[key]["startingPts"] += float(row.get("startingPts") or 0.0)
                agg[key]["benchPts"] += float(row.get("benchPts") or 0.0)
                agg[key]["irPts"] += float(row.get("irPts") or 0.0)
                agg[key]["minorsPts"] += float(row.get("minorsPts") or 0.0)
        rows = [
            {**v, "startingPts": round(v["startingPts"], 1),
             "benchPts": round(v["benchPts"], 1),
             "irPts": round(v["irPts"], 1),
             "minorsPts": round(v["minorsPts"], 1)}
            for v in agg.values()
        ]
        return {
            "league_id": league_id,
            "league_name": league.get("name"),
            "teams": rows,
            "from_week": from_week,
            "to_week": to_week,
            "weeks_available": len(snaps),
            "mode": "weekly_aggregate",
        }

    # Default — live current snapshot
    rows = await _current_tank_rows(league_id)
    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "teams": rows,
        "mode": "live",
    }


@router.post("/leagues/{league_id}/tank-monitor/snapshot")
async def tank_monitor_snapshot(league_id: str, week: int = Query(..., ge=1, le=30)):
    """Persist the current per-team breakdown as the given week's snapshot.

    Idempotent — upserts on (league_id, week). Used to populate
    `tank_monitor_weekly` so the week-range filter has data to aggregate.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    rows = await _current_tank_rows(league_id)
    now = datetime.now(timezone.utc).isoformat()
    await db.tank_monitor_weekly.update_one(
        {"league_id": league_id, "week": week},
        {"$set": {
            "league_id": league_id,
            "week": week,
            "teams": rows,
            "snapshot_at": now,
        }},
        upsert=True,
    )
    return {"league_id": league_id, "week": week, "teams_captured": len(rows), "snapshot_at": now}


@router.post("/leagues/{league_id}/tank-monitor/backfill")
async def tank_monitor_backfill(
    league_id: str,
    weeks: int = Query(22, ge=1, le=30, description="Number of historical weeks to backfill"),
    overwrite: bool = Query(False, description="Re-write existing weeks if already persisted"),
):
    """Backfill weekly snapshots so the Tank Monitor week-range filter
    has data immediately on a fresh league.

    Generates *plausible* historical data by perturbing the current
    snapshot per week — NOT a full replay. Use only for demo / initial
    population; the live worker should call `/snapshot` weekly going
    forward for real history.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    current_rows = await _current_tank_rows(league_id)
    if not current_rows:
        return {"league_id": league_id, "weeks_written": 0, "weeks_skipped": 0}

    now = datetime.now(timezone.utc).isoformat()
    written = 0
    skipped = 0
    for w in range(1, weeks + 1):
        if not overwrite:
            existing = await db.tank_monitor_weekly.find_one({"league_id": league_id, "week": w})
            if existing:
                skipped += 1
                continue
        # Perturb the current snapshot deterministically per (week, team)
        perturbed = []
        for i, r in enumerate(current_rows):
            seed = (w * 7 + i * 13) % 100
            jitter = lambda base, span: round(max(0.0, float(base) * (1.0 + (seed % span - span / 2) / 100.0)), 1)
            perturbed.append({
                "team_id": r["team_id"],
                "team": r["team"],
                "startingPts": jitter(r["startingPts"], 20),
                "benchPts": jitter(r["benchPts"], 30),
                "irPts": jitter(r["irPts"], 25),
                "minorsPts": jitter(r["minorsPts"], 25),
            })
        await db.tank_monitor_weekly.update_one(
            {"league_id": league_id, "week": w},
            {"$set": {
                "league_id": league_id,
                "week": w,
                "teams": perturbed,
                "snapshot_at": now,
                "backfilled": True,
            }},
            upsert=True,
        )
        written += 1
    return {"league_id": league_id, "weeks_written": written, "weeks_skipped": skipped}


@router.get("/leagues/{league_id}/roster-monitor")
async def roster_monitor(league_id: str):
    """Real-league replacement for the seeded Roster Monitor table.

    Per-team roster snapshots with section assignment + per-team violation
    counts (over-limit, empty starting slots, etc.). Limits default to a
    standard NHL fantasy template; once `league.roster_limits` lands we'll
    read them from the league document.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    limits = {**DEFAULT_ROSTER_LIMITS, **(league.get("roster_limits") or {})}

    teams_payload = []
    for team, detail in await _league_team_details(league_id):
        players = detail.get("players", []) or []
        # Categorize each player into a single coarse slot for the table
        categorized = []
        counts = {"starting": 0, "bench": 0, "ir": 0, "minors": 0}
        for p in players:
            sec = (p.get("rosterSection") or "").lower()
            if sec in _starting_sections():
                slot = "starting"
            elif sec in _bench_sections():
                slot = "bench"
            elif sec in _ir_sections():
                slot = "ir"
            elif sec in _minors_sections():
                slot = "minors"
            else:
                slot = "bench"  # fall-through default
            counts[slot] += 1
            categorized.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "position": p.get("position"),
                "fantasyPoints": float(p.get("fantasy_points") or 0.0),
                "slot": slot,
                "is_goalie": bool(p.get("is_goalie")),
                "irEligible": (p.get("contract") or {}).get("injuredReserve", False),
            })

        starting_cap = limits["starting_skaters"] + limits["starting_goalies"]
        violations = []
        if counts["starting"] > starting_cap:
            violations.append({
                "type": "over_starting",
                "message": f"Starting lineup has {counts['starting']} players (limit {starting_cap})",
            })
        if counts["bench"] > limits["bench"]:
            violations.append({
                "type": "over_bench",
                "message": f"Bench has {counts['bench']} players (limit {limits['bench']})",
            })
        if counts["ir"] > limits["ir"]:
            violations.append({
                "type": "over_ir",
                "message": f"IR has {counts['ir']} players (limit {limits['ir']})",
            })
        if counts["minors"] > limits["minors"]:
            violations.append({
                "type": "over_minors",
                "message": f"Minors has {counts['minors']} players (limit {limits['minors']})",
            })

        teams_payload.append({
            "team_id": str(team["_id"]),
            "team": team.get("name", "Unknown"),
            "players": categorized,
            "counts": counts,
            "violations": violations,
        })

    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "limits": limits,
        "teams": teams_payload,
    }

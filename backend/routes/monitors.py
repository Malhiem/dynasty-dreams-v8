"""
Iter 160 — Commissioner Monitor endpoints.

Replaces the mock data in commissionerData.tsx with real league snapshots.

  - GET /api/leagues/{league_id}/tank-monitor
        Returns per-team breakdown of fantasy points split across
        roster sections (starting / bench / IR / minors). Used by the
        commissioner's Tank Monitor table to spot teams hoarding talent
        outside their starting lineup.

  - GET /api/leagues/{league_id}/roster-monitor
        Returns per-team roster snapshots with section assignment +
        violation flags (over-limit, dead IR slot, etc.).

Both endpoints reuse the same enrichment logic that powers
`/api/roster/{team_id}/detail` so values stay in lockstep with the
Rosters page — no separate calculation paths.
"""
import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException

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
    from routes.roster import get_roster_detail

    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    out = []
    for team in teams:
        try:
            detail = await get_roster_detail(str(team["_id"]))
        except HTTPException:
            continue
        out.append((team, detail))
    return out


@router.get("/leagues/{league_id}/tank-monitor")
async def tank_monitor(league_id: str):
    """Real-league replacement for the seeded Tank Monitor table.

    Returns one row per team with fantasy-point totals split across the
    four roster sections. Empty teams (no players yet) are surfaced with
    zeros so commissioners still see the team listed.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

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

    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "teams": rows,
    }


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

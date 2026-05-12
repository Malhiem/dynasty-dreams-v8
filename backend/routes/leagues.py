"""Leagues router: enhanced standings (divisions/conferences/GB/movement) +
playoff bracket + division management (commissioner-only).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pydantic ─────────────────────────────────────────────────
class DivisionAssignment(BaseModel):
    team_id: str
    division: Optional[str] = None       # e.g. "Atlantic"
    conference: Optional[str] = None     # e.g. "Eastern"


class DivisionsUpdate(BaseModel):
    assignments: List[DivisionAssignment]


class ScheduleConfig(BaseModel):
    """Commissioner-tunable schedule mix.
    `intra_division_games` = times you play every team in your OWN division.
    `intra_conference_games` = times you play every non-division team in your OWN conference.
    `inter_conference_games` = times you play every team in the OPPOSITE conference.
    All three must be positive integers; set any to 0 to skip that tier.
    When not set (or <2 divisions configured), the generator falls back to
    vanilla round-robin (no intra-division bias).
    """
    intra_division_games: int = 2
    intra_conference_games: int = 1
    inter_conference_games: int = 1


# ─── Helpers ─────────────────────────────────────────────────
def _score(team: dict) -> float:
    """Tiebreaker score used for ranking within a group."""
    return float(team.get("points_for", 0) or 0) + float(team.get("live_points", 0) or 0)


def _rank_teams(teams: List[dict]) -> List[dict]:
    """Sort teams by W desc, PF desc. Returns new sorted list."""
    return sorted(
        teams,
        key=lambda t: (
            t.get("wins", 0) or 0,
            _score(t),
        ),
        reverse=True,
    )


def _games_back(leader: dict, team: dict) -> float:
    """NHL-style Games Back. 0.0 for leader."""
    if leader is None or team is None:
        return 0.0
    lw = leader.get("wins", 0) or 0
    ll = leader.get("losses", 0) or 0
    tw = team.get("wins", 0) or 0
    tl = team.get("losses", 0) or 0
    gb = ((lw - tw) + (tl - ll)) / 2.0
    return max(0.0, round(gb, 1))


# ─── Endpoints ───────────────────────────────────────────────
@router.get("/leagues/{league_id}/standings")
async def get_standings(league_id: str):
    """Standings with live cap remaining, last-5 W/L/T, division/conference
    grouping, Games Back (GB), and week-over-week rank movement arrows.
    """
    db = _deps["db"]
    _recompute_team_salary_used = _deps["_recompute_team_salary_used"]

    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    cap_enabled = bool((league or {}).get("salary_cap_enabled"))
    league_cap = float((league or {}).get("salary_cap") or 0.0)

    # ─── Overall ranking ─────────────────────────────────
    overall_ranked = _rank_teams(teams)
    overall_leader = overall_ranked[0] if overall_ranked else None
    overall_rank_by_id = {str(t["_id"]): i + 1 for i, t in enumerate(overall_ranked)}

    # ─── Division / Conference grouping ─────────────────
    divisions_map: dict = {}  # division name -> list
    conferences_map: dict = {}  # conference name -> list
    has_divisions = False
    has_conferences = False
    for t in teams:
        div = t.get("division")
        conf = t.get("conference")
        if div:
            has_divisions = True
            divisions_map.setdefault(div, []).append(t)
        if conf:
            has_conferences = True
            conferences_map.setdefault(conf, []).append(t)

    div_rank_by_id: dict = {}
    for div_name, div_teams in divisions_map.items():
        for i, t in enumerate(_rank_teams(div_teams)):
            div_rank_by_id[str(t["_id"])] = i + 1

    conf_rank_by_id: dict = {}
    for conf_name, conf_teams in conferences_map.items():
        for i, t in enumerate(_rank_teams(conf_teams)):
            conf_rank_by_id[str(t["_id"])] = i + 1

    # ─── Build rows ──────────────────────────────────────
    standings = []
    for team in overall_ranked:
        tid = str(team["_id"])

        cap_used = 0.0
        cap_remaining: Optional[float] = None
        if cap_enabled and league_cap > 0:
            try:
                cap_used = await _recompute_team_salary_used(tid)
                cap_remaining = league_cap - cap_used
            except Exception:
                cap_used = float(team.get("salary_used") or 0.0)
                cap_remaining = league_cap - cap_used

        # Last-5 sequence
        history_cursor = db.matchups.find({
            "league_id": league_id,
            "$or": [{"home_team_id": tid}, {"away_team_id": tid}],
            "status": {"$in": ["completed", "final"]},
        }).sort("week", -1).limit(5)
        last_5: list[str] = []
        async for m in history_cursor:
            home_score = float(m.get("home_score") or 0)
            away_score = float(m.get("away_score") or 0)
            is_home = m.get("home_team_id") == tid
            my_score = home_score if is_home else away_score
            opp_score = away_score if is_home else home_score
            if abs(my_score - opp_score) < 0.01:
                last_5.append("T")
            elif my_score > opp_score:
                last_5.append("W")
            else:
                last_5.append("L")
        last_5.reverse()

        overall_rank = overall_rank_by_id[tid]
        prev_rank = team.get("previous_rank") or overall_rank
        rank_delta = prev_rank - overall_rank  # positive = moved up
        if rank_delta > 0:
            movement = "up"
        elif rank_delta < 0:
            movement = "down"
        else:
            movement = "same"

        gb = _games_back(overall_leader, team)
        gb_division = 0.0
        division_leader = None
        if team.get("division"):
            div_teams_sorted = _rank_teams(divisions_map.get(team["division"], []))
            if div_teams_sorted:
                division_leader = div_teams_sorted[0]
                gb_division = _games_back(division_leader, team)

        standings.append({
            "rank": overall_rank,
            "division_rank": div_rank_by_id.get(tid),
            "conference_rank": conf_rank_by_id.get(tid),
            "previous_rank": prev_rank,
            "rank_delta": rank_delta,
            "movement": movement,
            "team_id": tid,
            "team_name": team["name"],
            "team_abbr": team.get("logo_abbr"),
            "team_logo_url": team.get("logo_url"),
            "owner_name": team["owner_name"],
            "division": team.get("division"),
            "conference": team.get("conference"),
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
            "ties": team.get("ties", 0),
            "points_for": team.get("points_for", 0),
            "points_against": team.get("points_against", 0),
            "games_back": gb,
            "games_back_division": gb_division,
            "salary_cap_enabled": cap_enabled,
            "salary_cap": league_cap if cap_enabled else None,
            "salary_used": round(cap_used, 2) if cap_enabled else None,
            "salary_cap_remaining": round(cap_remaining, 2) if (cap_enabled and cap_remaining is not None) else None,
            "last_5": last_5,
        })

    return {
        "standings": standings,
        "has_divisions": has_divisions,
        "has_conferences": has_conferences,
        "divisions": sorted(divisions_map.keys()),
        "conferences": sorted(conferences_map.keys()),
    }


@router.get("/leagues/{league_id}/divisions")
async def get_divisions(league_id: str):
    """Return division/conference setup for a league."""
    db = _deps["db"]
    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "division": 1, "conference": 1, "logo_abbr": 1},
    ).to_list(200)

    divisions: dict = {}
    for t in teams:
        div = t.get("division")
        if not div:
            continue
        entry = divisions.setdefault(div, {
            "division": div,
            "conference": t.get("conference"),
            "team_ids": [],
            "teams": [],
        })
        entry["team_ids"].append(str(t["_id"]))
        entry["teams"].append({
            "id": str(t["_id"]),
            "name": t.get("name"),
            "abbr": t.get("logo_abbr"),
        })
    return {
        "divisions": list(divisions.values()),
        "unassigned": [
            {"id": str(t["_id"]), "name": t.get("name")}
            for t in teams if not t.get("division")
        ],
    }


@router.put("/leagues/{league_id}/divisions")
async def update_divisions(league_id: str, input: DivisionsUpdate, request: Request):
    """Commissioner assigns teams to divisions/conferences."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner only")

    updated = 0
    # ─── Enforce: every team in the league must have BOTH a division and a conference ──
    # When a commissioner saves League Structure, we refuse the save if any
    # team in the league would be left unassigned. We compute the post-save
    # state by overlaying the incoming assignments on the current teams
    # collection.
    proposed = {a.team_id: a for a in input.assignments}
    all_teams = await db.teams.find({"league_id": league_id}, {"_id": 1, "name": 1, "division": 1, "conference": 1}).to_list(200)
    missing: list = []
    for t in all_teams:
        tid = str(t["_id"])
        if tid in proposed:
            div = proposed[tid].division or None
            conf = proposed[tid].conference or None
        else:
            div = t.get("division") or None
            conf = t.get("conference") or None
        if not div or not conf:
            missing.append({"team_id": tid, "team_name": t.get("name"), "division": div, "conference": conf})
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "incomplete_league_structure",
                "message": "Every team needs both a division and a conference before you can save.",
                "missing": missing,
            },
        )

    for a in input.assignments:
        try:
            oid = ObjectId(a.team_id)
        except Exception:
            continue
        res = await db.teams.update_one(
            {"_id": oid, "league_id": league_id},
            {"$set": {
                "division": a.division or None,
                "conference": a.conference or None,
            }},
        )
        updated += res.modified_count

    # Audit log
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$push": {"audit_log": {
            "action": "divisions_updated",
            "by": user.get("email"),
            "count": updated,
            "assignments": [a.model_dump() for a in input.assignments],
        }}},
    )
    return {"updated": updated}


@router.get("/leagues/{league_id}/schedule-config")
async def get_schedule_config(league_id: str):
    """Return the league's schedule mix config (or defaults if unset)."""
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)}, {"schedule_config": 1})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    cfg = league.get("schedule_config") or {}
    return {
        "intra_division_games": cfg.get("intra_division_games", 2),
        "intra_conference_games": cfg.get("intra_conference_games", 1),
        "inter_conference_games": cfg.get("inter_conference_games", 1),
        "configured": bool(league.get("schedule_config")),
    }


@router.put("/leagues/{league_id}/schedule-config")
async def update_schedule_config(league_id: str, input: ScheduleConfig, request: Request):
    """Commissioner tunes intra-division / intra-conference / inter-conference game counts."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner only")

    for field_name, val in (
        ("intra_division_games", input.intra_division_games),
        ("intra_conference_games", input.intra_conference_games),
        ("inter_conference_games", input.inter_conference_games),
    ):
        if val < 0 or val > 10:
            raise HTTPException(status_code=400, detail=f"{field_name} must be 0-10")

    cfg = {
        "intra_division_games": input.intra_division_games,
        "intra_conference_games": input.intra_conference_games,
        "inter_conference_games": input.inter_conference_games,
    }
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {
            "$set": {"schedule_config": cfg},
            "$push": {"audit_log": {
                "action": "schedule_config_updated",
                "by": user.get("email"),
                "config": cfg,
            }},
        },
    )
    return {"saved": cfg}


@router.post("/leagues/{league_id}/setup-complete")
async def mark_setup_complete(league_id: str, request: Request):
    """Flip league.setup_wizard_complete = true (commissioner only)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner only")

    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {
            "$set": {
                "setup_wizard_complete": True,
                "setup_wizard_completed_at": datetime.now(timezone.utc),
                "setup_wizard_completed_by": user.get("email"),
            },
            "$push": {"audit_log": {
                "action": "setup_wizard_completed",
                "by": user.get("email"),
            }},
        },
    )
    return {"setup_wizard_complete": True}


@router.post("/leagues/{league_id}/validate-setup")
async def validate_setup_prerequisites(league_id: str, request: Request):
    """Pre-flight check before marking a league setup-complete. Returns
    `{ok: bool, issues: [str]}` so the wizard can surface a specific reason
    instead of a generic 'Failed to mark setup complete' toast.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    issues: list[str] = []
    # Roster shape sanity
    if not league.get("roster_spots"):
        issues.append("Roster size isn't set — pick a non-zero number on the Basics step.")
    # Teams present
    teams_count = await db.teams.count_documents({"league_id": league_id})
    if teams_count < 2:
        issues.append(f"Only {teams_count} team{'s' if teams_count != 1 else ''} in the league — you need at least 2 before generating a schedule.")
    return {"ok": len(issues) == 0, "issues": issues, "teams_count": teams_count}


@router.post("/leagues/{league_id}/setup-reset")
async def reset_setup_wizard(league_id: str, request: Request):
    """Re-open the setup wizard (commissioner only)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner only")

    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"setup_wizard_complete": False}},
    )
    return {"setup_wizard_complete": False}


@router.get("/leagues/{league_id}/playoff-bracket")
async def get_playoff_bracket(league_id: str):
    """Projected playoff bracket using current standings.

    Format:
      - 6 teams  → top 2 seeds bye, 3v6 + 4v5, then winners vs seeds → final
      - 4 teams  → 1v4, 2v3 → final
      - 8 teams  → 1v8, 2v7, 3v6, 4v5 → QF/SF/F
      - 2 teams  → single championship game
    Matches `league.playoff_teams` if set, otherwise defaults by team count:
      12 teams → 6, 10 → 6, 8 → 6, 6 → 4, 4 → 2.
    Pairings follow standard single-elimination seeding.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    total = len(teams)
    if total < 2:
        return {"rounds": [], "playoff_teams": [], "bye_teams": [], "status": "insufficient_teams"}

    # Determine playoff size
    playoff_size = league.get("playoff_teams")
    if not playoff_size or not isinstance(playoff_size, int) or playoff_size < 2:
        if total >= 10:
            playoff_size = 6
        elif total >= 8:
            playoff_size = 6
        elif total >= 6:
            playoff_size = 4
        elif total >= 4:
            playoff_size = 4
        else:
            playoff_size = 2
    playoff_size = min(playoff_size, total)

    # Seed by overall rank
    seeded = _rank_teams(teams)[:playoff_size]
    overall_leader = seeded[0] if seeded else None

    def _team_to_slot(t: dict, seed: int) -> dict:
        return {
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "team_abbr": t.get("logo_abbr"),
            "team_logo_url": t.get("logo_url"),
            "owner_name": t.get("owner_name"),
            "seed": seed,
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": round(float(t.get("points_for", 0) or 0), 2),
            "games_back": _games_back(overall_leader, t),
        }

    playoff_teams_out = [_team_to_slot(t, i + 1) for i, t in enumerate(seeded)]

    # Build bracket rounds
    rounds: list = []
    bye_teams_out: list = []

    def _make_matchup(high_seed: dict, low_seed: dict) -> dict:
        return {
            "high_seed": high_seed,
            "low_seed": low_seed,
            "projected_winner": high_seed["team_id"] if high_seed else None,
            "status": "projected",
        }

    if playoff_size == 2:
        rounds.append({
            "name": "Championship",
            "matchups": [_make_matchup(playoff_teams_out[0], playoff_teams_out[1])],
        })
    elif playoff_size == 4:
        r1 = [
            _make_matchup(playoff_teams_out[0], playoff_teams_out[3]),  # 1v4
            _make_matchup(playoff_teams_out[1], playoff_teams_out[2]),  # 2v3
        ]
        rounds.append({"name": "Semifinals", "matchups": r1})
        rounds.append({
            "name": "Championship",
            "matchups": [_make_matchup(playoff_teams_out[0], playoff_teams_out[1])],
        })
    elif playoff_size == 6:
        # Top-2 seeds bye; 3v6, 4v5 in R1
        bye_teams_out = [playoff_teams_out[0], playoff_teams_out[1]]
        r1 = [
            _make_matchup(playoff_teams_out[2], playoff_teams_out[5]),  # 3v6
            _make_matchup(playoff_teams_out[3], playoff_teams_out[4]),  # 4v5
        ]
        rounds.append({"name": "Quarterfinals", "matchups": r1, "byes": bye_teams_out})
        # Semis: 1 vs lowest surviving, 2 vs next
        rounds.append({
            "name": "Semifinals",
            "matchups": [
                _make_matchup(playoff_teams_out[0], playoff_teams_out[5]),
                _make_matchup(playoff_teams_out[1], playoff_teams_out[3]),
            ],
        })
        rounds.append({
            "name": "Championship",
            "matchups": [_make_matchup(playoff_teams_out[0], playoff_teams_out[1])],
        })
    elif playoff_size == 8:
        r1 = [
            _make_matchup(playoff_teams_out[0], playoff_teams_out[7]),
            _make_matchup(playoff_teams_out[3], playoff_teams_out[4]),
            _make_matchup(playoff_teams_out[1], playoff_teams_out[6]),
            _make_matchup(playoff_teams_out[2], playoff_teams_out[5]),
        ]
        rounds.append({"name": "Quarterfinals", "matchups": r1})
        rounds.append({
            "name": "Semifinals",
            "matchups": [
                _make_matchup(playoff_teams_out[0], playoff_teams_out[3]),
                _make_matchup(playoff_teams_out[1], playoff_teams_out[2]),
            ],
        })
        rounds.append({
            "name": "Championship",
            "matchups": [_make_matchup(playoff_teams_out[0], playoff_teams_out[1])],
        })

    # Overlay actual playoff matchups if they exist for this league
    actual_matchups = await db.matchups.find({
        "league_id": league_id,
        "is_playoff": True,
    }).to_list(50)
    actual_by_pair: dict = {}
    for m in actual_matchups:
        key = tuple(sorted([m.get("home_team_id"), m.get("away_team_id")]))
        actual_by_pair[key] = m

    for rd in rounds:
        for mu in rd["matchups"]:
            hs = mu.get("high_seed")
            ls = mu.get("low_seed")
            if not hs or not ls:
                continue
            key = tuple(sorted([hs["team_id"], ls["team_id"]]))
            a = actual_by_pair.get(key)
            if a:
                mu["status"] = a.get("status", "scheduled")
                mu["home_score"] = a.get("home_score")
                mu["away_score"] = a.get("away_score")
                mu["week"] = a.get("week")
                # Winner (if finalized)
                if a.get("status") in ("completed", "final"):
                    home = a.get("home_team_id")
                    hs_s = float(a.get("home_score") or 0)
                    as_s = float(a.get("away_score") or 0)
                    if hs_s > as_s:
                        mu["projected_winner"] = home
                    elif as_s > hs_s:
                        mu["projected_winner"] = a.get("away_team_id")

    return {
        "league_id": league_id,
        "playoff_size": playoff_size,
        "playoff_teams": playoff_teams_out,
        "bye_teams": bye_teams_out,
        "rounds": rounds,
        "status": "actual" if actual_matchups else "projected",
    }


# ─── Premium feature settings (salary cap, minors) + 14-day trial clock ───
class CapSettingsUpdate(BaseModel):
    salary_cap_enabled: Optional[bool] = None
    salary_cap: Optional[int] = None
    salary_retention_slots: Optional[int] = Field(None, ge=0, le=10)
    minors_enabled: Optional[bool] = None  # if your league offers a minor-league/prospects pool


def _premium_status(league: dict) -> dict:
    """Compute trial state for a league with premium features enabled.

    Returns a dict with `paid`, `trial_started_at`, `trial_expires_at`,
    `trial_seconds_left`, `trial_expired`, and `enabled_features`.
    The 14-day clock starts when the first premium feature is toggled on
    AND the league hasn't paid. Last 24 hours: countdown is hourly on the
    client (server returns full seconds_left).
    """
    paid = bool(league.get("premium"))
    enabled = []
    if league.get("salary_cap_enabled"):
        enabled.append("salary_cap")
    if league.get("minors_enabled"):
        enabled.append("minors")
    started = league.get("premium_trial_started_at")
    if not enabled or paid:
        return {
            "paid": paid, "trial_started_at": None, "trial_expires_at": None,
            "trial_seconds_left": None, "trial_expired": False,
            "enabled_features": enabled,
        }
    if not started:
        return {
            "paid": False, "trial_started_at": None, "trial_expires_at": None,
            "trial_seconds_left": None, "trial_expired": False,
            "enabled_features": enabled,
        }
    if isinstance(started, str):
        try:
            started = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except Exception:
            started = None
    if not started:
        return {
            "paid": False, "trial_started_at": None, "trial_expires_at": None,
            "trial_seconds_left": None, "trial_expired": False,
            "enabled_features": enabled,
        }
    # Coerce naive datetimes (MongoDB) to UTC-aware so arithmetic works.
    if isinstance(started, datetime) and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    expires = started + timedelta(days=14)
    now = datetime.now(timezone.utc)
    seconds_left = int((expires - now).total_seconds())
    return {
        "paid": False,
        "trial_started_at": started.isoformat(),
        "trial_expires_at": expires.isoformat(),
        "trial_seconds_left": max(0, seconds_left),
        "trial_expired": seconds_left <= 0,
        "enabled_features": enabled,
    }


@router.put("/leagues/{league_id}/admin/cap-settings")
async def update_cap_settings(league_id: str, payload: CapSettingsUpdate, request: Request):
    """Commissioner toggles salary cap / minors premium features.

    Starts the 14-day premium trial clock the first time a premium feature
    is enabled (and the league hasn't already paid). The clock only resets
    if both premium features get disabled and re-enabled later.
    """
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    ):
        raise HTTPException(status_code=403, detail="Commissioner only")

    updates: dict = {}
    if payload.salary_cap_enabled is not None:
        updates["salary_cap_enabled"] = bool(payload.salary_cap_enabled)
        if not payload.salary_cap_enabled:
            updates["salary_cap"] = None
        elif payload.salary_cap is not None:
            updates["salary_cap"] = int(payload.salary_cap)
    elif payload.salary_cap is not None:
        updates["salary_cap"] = int(payload.salary_cap)
    if payload.salary_retention_slots is not None:
        updates["salary_retention_slots"] = int(payload.salary_retention_slots)
    if payload.minors_enabled is not None:
        updates["minors_enabled"] = bool(payload.minors_enabled)

    # Start the trial clock if any premium feature is now enabled and the
    # league hasn't paid yet. Idempotent — won't reset an existing clock.
    new_cap = updates.get("salary_cap_enabled", league.get("salary_cap_enabled"))
    new_min = updates.get("minors_enabled", league.get("minors_enabled"))
    any_premium = bool(new_cap or new_min)
    if any_premium and not league.get("premium") and not league.get("premium_trial_started_at"):
        updates["premium_trial_started_at"] = datetime.now(timezone.utc)
    # When all premium features are off, clear the trial timer so re-enabling
    # later gives a fresh 14-day window.
    if not any_premium and league.get("premium_trial_started_at"):
        updates["premium_trial_started_at"] = None

    if updates:
        await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": updates})
    fresh = await db.leagues.find_one({"_id": ObjectId(league_id)})
    return {
        "salary_cap_enabled": bool(fresh.get("salary_cap_enabled")),
        "salary_cap": fresh.get("salary_cap"),
        "salary_retention_slots": fresh.get("salary_retention_slots"),
        "minors_enabled": bool(fresh.get("minors_enabled")),
        "premium_status": _premium_status(fresh),
    }


@router.get("/leagues/{league_id}/premium-status")
async def get_premium_status(league_id: str, request: Request):
    """Public-ish endpoint (any logged-in user) so the banner can render.

    Returns the live trial countdown for the league.
    """
    db = _deps["db"]
    await _deps["get_current_user"](request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return _premium_status(league)


# ─── PUT /leagues/{league_id} ──────────────────────────────────
# Moved out of `server.py` (iter 80) for parity with the rest of the leagues
# router. Single source of truth for every mutable league setting that the
# Setup Wizard or Commissioner Settings UI can change. Sparse payload — only
# provided keys are written. Audit log captures the diff with actor + role.
class LeagueUpdate(BaseModel):
    is_private: Optional[bool] = None
    name: Optional[str] = Field(default=None, max_length=120)
    # Roster shape
    roster_spots: Optional[int] = Field(default=None, ge=10, le=40)
    bench_spots: Optional[int] = Field(default=None, ge=0, le=20)
    minors_spots: Optional[int] = Field(default=None, ge=0, le=20)
    # Format + scoring
    scoring_format: Optional[str] = None
    max_teams: Optional[int] = Field(default=None, ge=4, le=32)
    keepers_allowed: Optional[int] = Field(default=None, ge=0, le=30)
    entry_fee: Optional[float] = Field(default=None, ge=0)
    # Trade settings
    trade_review_period_hours: Optional[int] = Field(default=None, ge=0, le=168)
    trade_veto_threshold_pct: Optional[int] = Field(default=None, ge=0, le=100)
    trade_deadline_week: Optional[int] = Field(default=None, ge=1, le=30)
    # Waiver settings
    waiver_faab_budget: Optional[int] = Field(default=None, ge=0, le=10000)
    waiver_period_days: Optional[int] = Field(default=None, ge=0, le=7)
    # Playoff settings
    playoff_teams: Optional[int] = Field(default=None, ge=2, le=16)
    playoff_start_week: Optional[int] = Field(default=None, ge=1, le=30)
    playoff_rounds: Optional[int] = Field(default=None, ge=1, le=5)
    playoff_end_week: Optional[int] = Field(default=None, ge=1, le=40)
    regular_season_weeks: Optional[int] = Field(default=None, ge=4, le=30)
    # Salary retention controls
    salary_retention_enabled: Optional[bool] = None
    salary_retention_max_pct: Optional[int] = Field(default=None, ge=0, le=100)
    salary_retention_slots: Optional[int] = Field(default=None, ge=0, le=10)
    # Schedule shape (calendar-based)
    season_start_date: Optional[str] = Field(default=None, max_length=20)
    season_end_date: Optional[str] = Field(default=None, max_length=20)
    matchup_length_days: Optional[int] = Field(default=None, ge=1, le=30)
    opponents_per_matchup_period: Optional[int] = Field(default=None, ge=1, le=10)
    # Consolation bracket
    consolation_enabled: Optional[bool] = None
    consolation_start_week: Optional[int] = Field(default=None, ge=1, le=40)
    consolation_end_week: Optional[int] = Field(default=None, ge=1, le=40)
    consolation_uses_playoff_schedule: Optional[bool] = None


_LEAGUE_UPDATE_ALLOWED = {
    "is_private", "name", "roster_spots", "bench_spots", "minors_spots",
    "scoring_format", "max_teams", "keepers_allowed", "entry_fee",
    "trade_review_period_hours", "trade_veto_threshold_pct", "trade_deadline_week",
    "waiver_faab_budget", "waiver_period_days",
    "playoff_teams", "playoff_start_week", "playoff_rounds", "playoff_end_week",
    "regular_season_weeks",
    "salary_retention_enabled", "salary_retention_max_pct", "salary_retention_slots",
    "season_start_date", "season_end_date",
    "matchup_length_days", "opponents_per_matchup_period",
    "consolation_enabled", "consolation_start_week", "consolation_end_week",
    "consolation_uses_playoff_schedule",
}


@router.put("/leagues/{league_id}")
async def update_league(league_id: str, payload: LeagueUpdate, request: Request):
    """Commissioner / co-commissioner only: update mutable league settings.

    Sparse payload — only provided keys are written; the response echoes the
    full canonical config so the UI cache can stay in sync without a follow-up
    GET.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(
            status_code=403,
            detail="Only commissioners can update league settings",
        )

    update: dict = {}
    diff: dict = {}
    body = payload.model_dump(exclude_unset=True)
    for field in _LEAGUE_UPDATE_ALLOWED:
        if field not in body:
            continue
        new_val = body[field]
        if field == "name" and isinstance(new_val, str):
            new_val = new_val.strip() or None
            if not new_val:
                continue
        old_val = league.get(field)
        if new_val != old_val:
            update[field] = new_val
            diff[field] = {"from": old_val, "to": new_val}

    if update:
        await db.leagues.update_one({"_id": league["_id"]}, {"$set": update})
        await db.audit_log.insert_one({
            "league_id": league_id,
            "actor_id": user["_id"],
            "actor_name": user.get("name", user.get("email", "Unknown")),
            "action": "league_settings_updated",
            "role": "commissioner" if is_comm else "co_commissioner",
            "diff": diff,
            "created_at": datetime.now(timezone.utc),
        })

    fresh = await db.leagues.find_one({"_id": league["_id"]})
    out = {
        "league_id": league_id,
        "changes": diff,
        "name": fresh.get("name"),
        "is_private": bool(fresh.get("is_private")),
    }
    for key in _LEAGUE_UPDATE_ALLOWED:
        if key in ("name", "is_private"):
            continue
        out[key] = fresh.get(key)
    return out

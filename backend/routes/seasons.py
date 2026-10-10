"""Season lifecycle + League Health Score.

Tracks per-season snapshots (records, awards, rosters, points) when a
commissioner marks a season complete and renews. Also computes a 0-100
"health score" reflecting how well the league is configured for the year.

Data:
  - league_seasons: { league_id, season_year, status, snapshot_at, completed_by,
                      teams: [...], awards: [...], divisions, schedule_config,
                      salary_cap_config, playoff_config, regular_season_weeks,
                      playoff_weeks }
  - leagues.current_season_year (int, e.g. 2026)
  - leagues.current_season_status: "in_progress" | "complete" | "renewed"
"""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from services.financial_lock import serialize_finances
from services.profile_attribution import contributions, next_season_attribution, owners
from services.season_history import capture_players, capture_standings, champions, historical_rank, tied_leaders
from services.fantasy_scoring import DEFAULT_SKATER_SCORING, DEFAULT_GOALIE_SCORING, calculate_fantasy_points
from routes.league_guards import require_league_member
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pydantic ────────────────────────────────────────────────
class CompleteSeasonInput(BaseModel):
    season_year: Optional[int] = None  # default = league.current_season_year


class RenewSeasonInput(BaseModel):
    new_season_year: int
    carry_over_settings: bool = True   # copy cap, divisions, schedule_config, playoff_config
    reset_records: bool = True         # zero W/L/T, points_for/points_against


# ─── Helpers ─────────────────────────────────────────────────
async def _league_or_404(league_id: str):
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league


async def _ensure_commish(request: Request, league: dict):
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner only")
    return user


async def _snapshot_scoring_config(db, league_id):
    config = await db.scoring_configs.find_one({"league_id": league_id}) or {}
    return {
        "skater_scoring": config.get("skater_scoring", DEFAULT_SKATER_SCORING),
        "goalie_scoring": config.get("goalie_scoring", DEFAULT_GOALIE_SCORING),
    }


# ─── Health Score ────────────────────────────────────────────
def _section_complete(league: dict, key: str, data_inferred: bool) -> bool:
    """Iter 199 — derive section completion from `league.setup_progress[key]`
    when present. Falls back to `data_inferred` ONLY for legacy leagues
    that finished setup before `setup_progress` was introduced (so
    existing 100% leagues don't suddenly drop). New leagues default to
    incomplete until the commissioner walks the wizard.
    """
    sp = league.get("setup_progress")
    if isinstance(sp, dict) and key in sp:
        return bool(sp[key])
    # Legacy fallback: only trust data inference once the wizard's been
    # acknowledged as complete (otherwise default-on fields like
    # `playoff_teams=6` or `salary_cap_enabled=false` falsely show 100%).
    if league.get("setup_wizard_complete"):
        return data_inferred
    return False


def _compute_health_score(league: dict, teams: list, matchups_by_status: dict) -> dict:
    """Compute a 0-100 score across 6 weighted sections."""
    sections = []

    # 1. Basics — name + format + max_teams configured
    basics_ok_data = bool(league.get("name")) and bool(league.get("format")) and (league.get("max_teams") or 0) >= 2
    basics_ok = _section_complete(league, "basics", basics_ok_data)
    sections.append({
        "key": "basics",
        "label": "Basics",
        "complete": basics_ok,
        "weight": 16,
        "detail": "League name, format, and team count" if basics_ok else "Set name, format, and max teams",
    })

    # 2. Salary Cap — explicitly disabled is OK
    cap_explicit = ("salary_cap_enabled" in league)
    cap_ok_data = cap_explicit and (
        not league.get("salary_cap_enabled")
        or (league.get("salary_cap") and league.get("salary_cap") > 0)
    )
    cap_ok = _section_complete(league, "cap", cap_ok_data)
    sections.append({
        "key": "cap",
        "label": "Salary Cap",
        "complete": cap_ok,
        "weight": 16,
        "detail": (
            "Cap disabled" if cap_explicit and not league.get("salary_cap_enabled")
            else f"Cap ${(league.get('salary_cap') or 0):,.0f}" if cap_ok
            else "Configure cap (or explicitly disable it)"
        ),
    })

    # 3. Divisions — at least 2
    divisions = list({t.get("division") for t in teams if t.get("division")})
    div_ok_data = len(divisions) >= 2
    div_ok = _section_complete(league, "divisions", div_ok_data)
    sections.append({
        "key": "divisions",
        "label": "Divisions",
        "complete": div_ok,
        "weight": 16,
        "detail": f"{len(divisions)} divisions configured" if div_ok else "Assign teams to ≥ 2 divisions",
    })

    # 4. Schedule generated — at least one matchup exists
    sched_ok_data = matchups_by_status.get("total", 0) > 0
    sched_ok = _section_complete(league, "schedule", sched_ok_data)
    sections.append({
        "key": "schedule",
        "label": "Schedule",
        "complete": sched_ok,
        "weight": 17,
        "detail": (
            f"{matchups_by_status.get('total', 0)} matchups generated"
            if sched_ok else "Generate the regular-season schedule"
        ),
    })

    # 5. Playoff configured — playoff_teams set
    playoff_ok_data = (league.get("playoff_teams") or 0) >= 2
    playoff_ok = _section_complete(league, "playoffs", playoff_ok_data)
    sections.append({
        "key": "playoffs",
        "label": "Playoffs",
        "complete": playoff_ok,
        "weight": 17,
        "detail": (
            f"{league.get('playoff_teams')}-team bracket"
            if playoff_ok else "Set playoff team count"
        ),
    })

    # 6. Draft scheduled — at least one draft exists
    draft_ok_data = matchups_by_status.get("draft_count", 0) > 0
    draft_ok = _section_complete(league, "draft", draft_ok_data)
    sections.append({
        "key": "draft",
        "label": "Draft",
        "complete": draft_ok,
        "weight": 18,
        "detail": (
            f"{matchups_by_status.get('draft_count', 0)} draft(s) scheduled"
            if draft_ok else "Schedule a draft"
        ),
    })

    score = sum(s["weight"] for s in sections if s["complete"])
    return {
        "score": score,
        "sections": sections,
        "missing": [s["key"] for s in sections if not s["complete"]],
    }


# ─── Endpoints ───────────────────────────────────────────────
@router.get("/leagues/{league_id}/health-score")
async def get_health_score(league_id: str):
    """Return league setup completeness for the current season."""
    db = _deps["db"]
    league = await _league_or_404(league_id)
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    total_matchups = await db.matchups.count_documents({"league_id": league_id})
    drafts = await db.drafts.count_documents({"league_id": league_id})
    health = _compute_health_score(
        league, teams,
        {"total": total_matchups, "draft_count": drafts},
    )
    return {
        "league_id": league_id,
        "current_season_year": league.get("current_season_year") or datetime.now(timezone.utc).year,
        "current_season_status": league.get("current_season_status") or "in_progress",
        **health,
    }


@router.post("/leagues/{league_id}/setup-progress")
async def mark_setup_progress(league_id: str, request: Request):
    """Iter 199 — stamp one (or more) `setup_progress.<key>` flags as true
    on the league doc. Used by the Setup Wizard after each step's save.
    Body: `{"sections": ["basics", "cap"]}` OR `{"section": "basics"}`.
    Commissioner-only. Idempotent."""
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    league = await _league_or_404(league_id)
    # Reuse the same commish gate the rest of the file uses.
    uid = str(user.get("_id") or user.get("id") or "")
    commish_ids = {str(league.get("commissioner_id") or ""), str(league.get("created_by") or "")}
    commish_ids.update(str(x) for x in (league.get("co_commissioners") or []))
    commish_ids.update(str(x) for x in (league.get("commissioner_ids") or []))
    if uid not in commish_ids:
        raise HTTPException(status_code=403, detail="Commissioner access required")

    body = await request.json()
    sections = body.get("sections") or ([body["section"]] if body.get("section") else [])
    allowed = {"basics", "cap", "divisions", "schedule", "playoffs", "draft", "trades"}
    sections = [s for s in sections if s in allowed]
    if not sections:
        raise HTTPException(status_code=400, detail="No valid sections provided")

    progress = league.get("setup_progress") or {}
    for s in sections:
        progress[s] = True
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"setup_progress": progress}},
    )
    return {"league_id": league_id, "setup_progress": progress}


@router.get("/leagues/{league_id}/seasons")
async def list_seasons(league_id: str, request: Request, include_team_stats: bool = False):
    """List all completed seasons for a league (for History/Trophy Room).

    When `include_team_stats=true`, each returned season also includes a
    `team_stats` array — one entry per franchise that played that season —
    with the snapshot-time {wins, losses, ties, points_for, points_against,
    division, conference}. This lets the League History page sum lifetime
    records correctly across every completed season instead of relying on
    just the LIVE current-season totals.
    """
    user = await _deps["get_current_user"](request)
    db = _deps["db"]
    await require_league_member(db, user, league_id)
    projection = {
        "_id": 1, "season_year": 1, "status": 1, "snapshot_at": 1,
        "champion_team_name": 1, "completed_by": 1,
    }
    if include_team_stats:
        projection["teams"] = 1
    cursor = db.league_seasons.find({"league_id": league_id}, projection).sort("season_year", -1)
    seasons = []
    async for s in cursor:
        s["id"] = str(s.pop("_id"))
        if include_team_stats:
            teams = s.pop("teams", []) or []
            s["team_stats"] = [
                {
                    "team_id": t.get("team_id"),
                    "team_name": t.get("team_name"),
                    "wins": int(t.get("wins") or 0),
                    "losses": int(t.get("losses") or 0),
                    "ties": int(t.get("ties") or 0),
                    "points_for": float(t.get("points_for") or 0.0),
                    "points_against": float(t.get("points_against") or 0.0),
                    "division": t.get("division"),
                    "conference": t.get("conference"),
                }
                for t in teams
            ]
        seasons.append(s)
    return {"seasons": seasons}


@router.get("/leagues/{league_id}/seasons/{season_year}")
async def get_season(league_id: str, season_year: int, request: Request):
    """Full snapshot of a specific past season."""
    user = await _deps["get_current_user"](request)
    db = _deps["db"]
    await require_league_member(db, user, league_id)
    season = await db.league_seasons.find_one({
        "league_id": league_id, "season_year": season_year,
    })
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    season["id"] = str(season.pop("_id"))
    return season


@router.post("/leagues/{league_id}/complete-season")
@serialize_finances(lambda: _deps["db"])
async def complete_season(league_id: str, payload: CompleteSeasonInput, request: Request):
    """Snapshot the current season's records, awards, rosters → league_seasons.

    The snapshot becomes the source-of-truth for past performance shown in
    Analytics, League History, Trophy Room, and per-player career stats.

    Idempotent within a season_year: re-running overwrites the existing snapshot
    (useful if commissioner needs to correct it before renewing).
    """
    db = _deps["db"]
    league = await _league_or_404(league_id)
    user = await _ensure_commish(request, league)

    season_year = payload.season_year or league.get("current_season_year") or datetime.now(timezone.utc).year
    now = datetime.now(timezone.utc)

    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    player_snapshot = await capture_players(db, teams)

    from services.salary_policy import payroll, obligations
    prior = await db.league_seasons.find_one({"league_id": league_id, "season_year": season_year})
    previous_finances = {t["team_id"]: t for t in (prior or {}).get("teams", [])}
    for team in teams:
        state = await payroll(db, team, league)
        team["salary_used"] = state["used"]
        team["retention_history"] = [{k: v for k, v in row.items() if k != "_id"}
                                     for row in await obligations(db, league, team, include_history=True)]
        if league.get("current_season_status") == "complete" and str(team["_id"]) in previous_finances:
            saved = previous_finances[str(team["_id"])]
            team["salary_used"] = saved.get("salary_used", team["salary_used"])
            team["retention_history"] = saved.get("retention_history", team["retention_history"])


    # Snapshot teams' end-of-season records + roster + awards
    teams_snapshot = []
    champion = None
    for t in teams:
        owner = await db.users.find_one(
            {"_id": t.get("owner_id")},
            {"username": 1, "name": 1},
        ) if t.get("owner_id") else None
        ts = {
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "logo_abbr": t.get("logo_abbr"),
            "logo_url": t.get("logo_url"),
            "owner_id": t.get("owner_id"),
            "co_owner_ids": t.get("co_owner_ids") or [],
            "profile_contributions": contributions(t),
            "profile_management_excluded_user_ids": t.get("profile_management_excluded_user_ids") or [],
            "xp_award_details": t.get("xp_award_details") or {},
            "owner_username": (owner or {}).get("username"),
            "owner_name": (owner or {}).get("name"),
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": float(t.get("points_for", 0.0) or 0.0),
            "points_against": float(t.get("points_against", 0.0) or 0.0),
            "live_points": float(t.get("live_points", 0.0) or 0.0),
            "division": t.get("division"),
            "conference": t.get("conference"),
            "salary_used": float(t.get("salary_used", 0.0) or 0.0),
            "retention_history": t.get("retention_history", []),
            "roster": list(t.get("roster") or []),
            "awards": {
                "championship_won_at": t.get("championship_won_at"),
                "consolation_won_at": t.get("consolation_won_at"),
                "division_winner_at": t.get("division_winner_at"),
                "conference_winner_at": t.get("conference_winner_at"),
                "playoffs_reached_at": t.get("playoffs_reached_at"),
                "playoff_runner_up_at": t.get("playoff_runner_up_at"),
            },
        }
        if t.get("championship_won_at"):
            champion = ts["team_name"]
        teams_snapshot.append(ts)

    champion_ids = await capture_standings(db, league, teams_snapshot)
    champion = next((t['team_name'] for t in teams_snapshot if t['team_id'] in champion_ids), None)
    for ts in teams_snapshot:
        if ts['team_id'] in champion_ids:
            if not ts['awards'].get('championship_won_at'):
                ts['awards']['championship_won_at'] = now.isoformat()
                from services.profile_competition import award_fields
                fields = await award_fields(db, ts['team_id'], {'championship_won_at': now.isoformat()})
                await db.teams.update_one({'_id': ObjectId(ts['team_id'])}, {'$set': fields})
                refreshed = await db.teams.find_one({'_id': ObjectId(ts['team_id'])})
                ts['profile_contributions'] = contributions(refreshed)
                ts['xp_award_details'] = refreshed.get('xp_award_details') or {}
                for uid in owners(ts):
                    ts['profile_contributions'].setdefault(uid, {})['championship_won_at'] = ts['awards']['championship_won_at']

    # Awards / activity_feed entries from this season
    activity_cursor = db.activity_feed.find({
        "league_id": league_id,
        "event_type": {"$in": [
            "championship_awarded", "division_awarded",
            "conference_awarded", "consolation_awarded",
        ]},
    }).sort("created_at", -1)
    awards = []
    async for a in activity_cursor:
        awards.append({
            "event_type": a.get("event_type"),
            "description": a.get("description"),
            "created_at": a.get("created_at"),
        })

    # Capture league config for "use last year's settings" pre-fill
    scoring_config = await _snapshot_scoring_config(db, league_id)
    snapshot_doc = {
        "scoring_config": scoring_config,
        "league_id": league_id,
        "season_year": season_year,
        "status": "complete",
        "snapshot_at": now,
        "completed_by": user.get("email"),
        "completed_by_name": user.get("name"),
        "champion_team_name": champion,
        "champion_team_id": champion_ids[0] if len(champion_ids) == 1 else None,
        "champion_team_ids": champion_ids,
        "salary_cap_config": {
            "enabled": bool(league.get("salary_cap_enabled")),
            "amount": league.get("salary_cap"),
            "retention_slots": league.get("salary_retention_slots", 3),
        },
        "schedule_config": league.get("schedule_config"),
        "playoff_config": {
            "playoff_teams": league.get("playoff_teams"),
            "playoff_weeks": league.get("playoff_weeks"),
            "playoff_start_week": league.get("playoff_start_week"),
            "playoff_rounds": league.get("playoff_rounds"),
        },
        "regular_season_weeks": league.get("regular_season_weeks"),
        "scoring_format": league.get("scoring_format"),
        "format": league.get("format"),
        "teams": teams_snapshot,
        "awards": awards,
        "players": player_snapshot,
    }

    # Upsert — replay-safe
    await db.league_seasons.update_one(
        {"league_id": league_id, "season_year": season_year},
        {"$set": snapshot_doc},
        upsert=True,
    )

    if champion_ids:
        await db.teams.update_many({'_id': {'$in': [ObjectId(tid) for tid in champion_ids]}, '$or': [{'championship_won_at': None}, {'championship_won_at': ''}]}, {'$set': {'championship_won_at': now.isoformat()}})

    # Mark league
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "current_season_year": season_year,
            "current_season_status": "complete",
            "season_completed_at": now,
        }, "$push": {"audit_log": {
            "action": "season_completed",
            "by": user.get("email"),
            "season_year": season_year,
            "champion": champion,
        }}},
    )

    return {
        "season_year": season_year,
        "champion": champion,
        "teams_snapshotted": len(teams_snapshot),
        "awards_snapshotted": len(awards),
        "players_snapshotted": len(player_snapshot),
    }


@router.post("/leagues/{league_id}/renew-season")
@serialize_finances(lambda: _deps["db"])
async def renew_season(league_id: str, payload: RenewSeasonInput, request: Request):
    """Start a new season after the previous one has been marked complete.

    - Optionally carries over cap/divisions/schedule/playoff configs.
    - Optionally resets team W/L/T + points (keeps rosters intact).
    - Bumps `current_season_year` and resets status to "in_progress".
    - Does NOT delete past-season snapshots (those live forever in `league_seasons`).
    """
    db = _deps["db"]
    league = await _league_or_404(league_id)
    user = await _ensure_commish(request, league)

    now = datetime.now(timezone.utc)
    prev_year = league.get("current_season_year") or (datetime.now(timezone.utc).year - 1)
    new_year = payload.new_season_year
    if new_year <= prev_year:
        raise HTTPException(
            status_code=400,
            detail=f"new_season_year ({new_year}) must be greater than current ({prev_year})",
        )

    # Carry ownership attribution into the new season with a fresh baseline.
    attribution_teams = await db.teams.find({'league_id': league_id}).to_list(None)
    for team in attribution_teams:
        await db.teams.update_one({'_id': team['_id']}, {'$set': {
            'profile_attribution': next_season_attribution(team, payload.reset_records),
            'career_user_ids': sorted(set(team.get('career_user_ids') or []) | set(owners(team))),
        }})
    # Reset team records (keeps rosters)
    if payload.reset_records:
        await db.teams.update_many(
            {"league_id": league_id},
            {"$set": {
                "wins": 0, "losses": 0, "ties": 0,
                "xp_win_adjustment": 0, "xp_award_adjustments": {}, "xp_award_details": {},
                "points_for": 0.0, "points_against": 0.0,
                "live_points": 0.0,
            }, "$unset": {
                "championship_won_at": "",
                "division_winner_at": "",
                "conference_winner_at": "",
                "consolation_won_at": "",
                "playoffs_reached_at": "",
                "previous_rank": "",
                "xp_last_competition": "",
                "playoff_runner_up_at": "",
            }},
        )

    # Wipe matchups for the new season — fresh slate
    await db.matchups.delete_many({"league_id": league_id})

    # Bump league
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "current_season_year": new_year,
            "current_season_status": "in_progress",
            "setup_wizard_complete": False,  # encourage re-running wizard with prefilled values
            "season_renewed_at": now,
        }, "$push": {"audit_log": {
            "action": "season_renewed",
            "by": user.get("email"),
            "from_year": prev_year,
            "to_year": new_year,
            "carry_over_settings": payload.carry_over_settings,
            "reset_records": payload.reset_records,
        }}},
    )

    # Build prefill suggestion
    prev_snapshot = await db.league_seasons.find_one(
        {"league_id": league_id, "season_year": prev_year},
        {"_id": 0},
    )
    suggestions = None
    if prev_snapshot and payload.carry_over_settings:
        suggestions = {
            "salary_cap_config": prev_snapshot.get("salary_cap_config"),
            "schedule_config": prev_snapshot.get("schedule_config"),
            "playoff_config": prev_snapshot.get("playoff_config"),
            "scoring_format": prev_snapshot.get("scoring_format"),
        }

    return {
        "from_year": prev_year,
        "to_year": new_year,
        "reset_records": payload.reset_records,
        "carry_over_settings": payload.carry_over_settings,
        "previous_season_suggestions": suggestions,
    }


@router.get("/leagues/{league_id}/setup-suggestions")
async def get_setup_suggestions(league_id: str):
    """Suggest setup-wizard values based on the most recent completed season.
    Setup wizard pre-fills its inputs from this endpoint (returns null fields
    when no prior season exists).
    """
    db = _deps["db"]
    league = await _league_or_404(league_id)
    cur_year = league.get("current_season_year") or datetime.now(timezone.utc).year
    snap = await db.league_seasons.find_one(
        {"league_id": league_id, "season_year": {"$lt": cur_year}},
        sort=[("season_year", -1)],
    )
    if not snap:
        return {"has_previous_season": False}
    return {
        "has_previous_season": True,
        "previous_season_year": snap.get("season_year"),
        "salary_cap_config": snap.get("salary_cap_config"),
        "schedule_config": snap.get("schedule_config"),
        "playoff_config": snap.get("playoff_config"),
        "scoring_format": snap.get("scoring_format"),
        "champion": snap.get("champion_team_name"),
    }


# ─── Trophy Room ────────────────────────────────────────────
def _player_points(p: dict, scoring_config=None) -> float:
    """Use frozen season weights; preserve estimates for legacy snapshots."""
    if scoring_config is not None:
        return calculate_fantasy_points({**(p.get("season_stats") or {}), "position": (p.get("position") or "").upper()}, scoring_config)
    ss = p.get("season_stats") or {}
    pos = (p.get("position") or "").upper()
    if pos == "G":
        # Goalie: 4×W + 0.6×Sv − 1×GA (approximation)
        return float(
            4 * (ss.get("wins") or 0)
            + 0.6 * (ss.get("saves") or 0)
            - 1 * (ss.get("goals_against") or 0)
            + 5 * (ss.get("shutouts") or 0)
        )
    return float(ss.get("points") or 0) + 0.1 * float(ss.get("plus_minus") or 0)


def _build_season_trophies(snapshot: dict) -> dict:
    """Compute per-season trophy assignments from a league_seasons snapshot."""
    teams = snapshot.get("teams") or []
    players = snapshot.get("players") or []

    # Team-level trophies
    season_champions = champions(snapshot)
    champion = season_champions[0] if season_champions else None
    president_winners = tied_leaders(teams, lambda t:float(t.get('points_for') or 0), 'team_id')
    presidents = president_winners[0] if president_winners else None

    division_winners = [t for t in teams if (t.get("awards") or {}).get("division_winner_at")]
    conference_winners = [t for t in teams if (t.get("awards") or {}).get("conference_winner_at")]
    consolation = next((t for t in teams if (t.get("awards") or {}).get("consolation_won_at")), None)

    # Player-level trophies
    scoring_config = snapshot.get("scoring_config")
    score = lambda p: _player_points(p, scoring_config)
    skaters = [p for p in players if (p.get('position') or '').upper() != 'G']
    goalies = [p for p in players if (p.get('position') or '').upper() == 'G']
    defenders = [p for p in skaters if (p.get('position') or '').upper() == 'D']
    mvps = tied_leaders(skaters, score, 'player_id')
    goalie_winners = tied_leaders(goalies, score, 'player_id')
    defense_winners = tied_leaders(defenders, score, 'player_id')
    season_mvp = mvps[0] if mvps else None
    best_goalie = goalie_winners[0] if goalie_winners else None
    best_defender = defense_winners[0] if defense_winners else None

    # Owner lookup so each player trophy can attribute to their team
    player_to_team = {}
    for t in teams:
        for pid in (t.get("roster") or []):
            player_to_team[str(pid)] = {
                "team_id": t.get("team_id"),
                "team_name": t.get("team_name"),
            }

    def _player_card(p, label):
        if not p:
            return None
        owner = player_to_team.get(p.get("player_id"), {})
        return {
            "label": label,
            "player_id": p.get("player_id"),
            "player_name": p.get("name"),
            "position": p.get("position"),
            "team": p.get("team"),
            "season_stats": p.get("season_stats") or {},
            "points": round(score(p), 2),
            "scoring_basis": "season_weights" if scoring_config is not None else "legacy_estimate",
            "owner_team_id": owner.get("team_id"),
            "owner_team_name": owner.get("team_name"),
        }

    return {
        "champions": [{"team_id":t['team_id'],"team_name":t['team_name'],"logo_url":t.get('logo_url')} for t in season_champions],
        "champion_status": "resolved" if season_champions else "ambiguous" if snapshot.get('champion_team_name') else "none",
        "presidents_trophies": [{"team_id":t['team_id'],"team_name":t['team_name'],"logo_url":t.get('logo_url'),"points_for":t.get('points_for')} for t in president_winners],
        "player_awards": [_player_card(p,label) for rows,label in [(mvps,'Season MVP'),(goalie_winners,'Best Goalie'),(defense_winners,'Best Defenseman')] for p in rows],
        "season_year": snapshot.get("season_year"),
        "champion": (
            {"team_id": champion["team_id"], "team_name": champion["team_name"], "logo_url": champion.get("logo_url")}
            if champion else None
        ),
        "presidents_trophy": (
            {"team_id": presidents["team_id"], "team_name": presidents["team_name"], "logo_url": presidents.get("logo_url"), "points_for": presidents.get("points_for")}
            if presidents else None
        ),
        "division_winners": [
            {"team_id": t["team_id"], "team_name": t["team_name"], "logo_url": t.get("logo_url"), "division": t.get("division")}
            for t in division_winners
        ],
        "conference_winners": [
            {"team_id": t["team_id"], "team_name": t["team_name"], "logo_url": t.get("logo_url"), "conference": t.get("conference")}
            for t in conference_winners
        ],
        "consolation_winner": (
            {"team_id": consolation["team_id"], "team_name": consolation["team_name"], "logo_url": consolation.get("logo_url")}
            if consolation else None
        ),
        "season_mvp": _player_card(season_mvp, "Season MVP"),
        "best_goalie": _player_card(best_goalie, "Best Goalie"),
        "best_defenseman": _player_card(best_defender, "Best Defenseman"),
    }


@router.get("/leagues/{league_id}/trophy-room")
async def get_league_trophy_room(league_id: str, request: Request):
    """Return all-time trophies + hall of fame for the league."""
    user = await _deps["get_current_user"](request)
    db = _deps["db"]
    await require_league_member(db, user, league_id)

    cursor = db.league_seasons.find({"league_id": league_id}).sort("season_year", -1)
    season_trophies: list = []
    async for snap in cursor:
        season_trophies.append(_build_season_trophies(snap))

    # Aggregate banners per team
    team_banners: dict = {}
    def _add_banner(team, btype, year, extra=None):
        if not team or not team.get("team_id"):
            return
        tb = team_banners.setdefault(team["team_id"], {
            "team_id": team["team_id"],
            "team_name": team.get("team_name"),
            "logo_url": team.get("logo_url"),
            "banners": [],
        })
        tb["banners"].append({
            "type": btype, "year": year, **(extra or {}),
        })

    # Hall of fame: aggregate player trophies across seasons
    hof_counter: dict = {}
    for s in season_trophies:
        yr = s["season_year"]
        for winner in s["champions"]: _add_banner(winner, "championship", yr)
        for winner in s["presidents_trophies"]: _add_banner(winner, "presidents_trophy", yr)
        for d in s["division_winners"]: _add_banner(d, "division", yr, {"division": d.get("division")})
        for c in s["conference_winners"]: _add_banner(c, "conference", yr, {"conference": c.get("conference")})
        if s["consolation_winner"]: _add_banner(s["consolation_winner"], "consolation", yr)

        for ptrophy in s["player_awards"]:
            if not ptrophy or not ptrophy.get("player_id"):
                continue
            pid = ptrophy["player_id"]
            entry = hof_counter.setdefault(pid, {
                "player_id": pid,
                "player_name": ptrophy["player_name"],
                "position": ptrophy["position"],
                "team": ptrophy["team"],
                "trophies": [],
            })
            entry["trophies"].append({
                "label": ptrophy["label"],
                "year": yr,
                "owner_team_id": ptrophy.get("owner_team_id"),
                "owner_team_name": ptrophy.get("owner_team_name"),
            })

    # Top-3 hall of fame (by trophy count desc, then most recent first)
    hall_of_fame = sorted(
        hof_counter.values(),
        key=lambda x: (-len(x["trophies"]), -max((t["year"] or 0) for t in x["trophies"]) if x["trophies"] else 0),
    )[:8]

    return {
        "league_id": league_id,
        "seasons": season_trophies,
        "team_banners": list(team_banners.values()),
        "hall_of_fame": hall_of_fame,
    }


@router.get("/players/{player_id}/dynasty-career")
async def get_player_dynasty_career(player_id: str, request: Request):
    """Return a player's dynasty-league career: every league_seasons snapshot
    where this player was rostered, with the team that owned them + any
    individual awards (Season MVP / Best Goalie / Best Defenseman) won that year.
    """
    user = await _deps["get_current_user"](request)
    db = _deps["db"]
    cursor = db.league_seasons.find(
        {"players.player_id": player_id},
    ).sort("season_year", -1)

    history: list = []
    league_ids: set = set()
    access = {}
    async for snap in cursor:
        lid = snap["league_id"]
        if lid not in access:
            try:
                await require_league_member(db, user, lid)
                access[lid] = True
            except HTTPException as exc:
                if exc.status_code not in (400, 403, 404):
                    raise
                access[lid] = False
        if not access[lid]:
            continue
        league_ids.add(lid)
        # Locate this player's snapshot row
        prow = next((p for p in (snap.get("players") or []) if p.get("player_id") == player_id), None)
        if not prow:
            continue
        # Locate the team that owned them
        owner_team = None
        for t in (snap.get("teams") or []):
            if player_id in [str(rid) for rid in (t.get("roster") or [])]:
                owner_team = t
                break
        # Award detection: did this player win a per-season trophy?
        awards = []
        season_card = _build_season_trophies(snap)
        for ptrophy in season_card["player_awards"]:
            if ptrophy and ptrophy.get("player_id") == player_id:
                awards.append({"label": ptrophy["label"], "year": snap.get("season_year")})

        history.append({
            "league_id": snap["league_id"],
            "season_year": snap.get("season_year"),
            "season_stats": prow.get("season_stats") or {},
            "fantasy_points": round(_player_points(prow, snap.get("scoring_config")), 2),
            "scoring_basis": "season_weights" if snap.get("scoring_config") is not None else "legacy_estimate",
            "owner_team_id": (owner_team or {}).get("team_id"),
            "owner_team_name": (owner_team or {}).get("team_name"),
            "awards": awards,
            "champion": any(t["team_id"] == (owner_team or {}).get("team_id") for t in champions(snap)),
        })

    # Resolve league names
    leagues_by_id: dict = {}
    if league_ids:
        async for lg in db.leagues.find(
            {"_id": {"$in": [ObjectId(lid) for lid in league_ids if ObjectId.is_valid(lid)]}},
            {"name": 1},
        ):
            leagues_by_id[str(lg["_id"])] = lg.get("name")
    for h in history:
        h["league_name"] = leagues_by_id.get(h["league_id"])

    # Career totals
    total_awards = sum(len(h["awards"]) for h in history)
    total_championships = sum(1 for h in history if h["champion"])
    total_seasons = len(history)
    return {
        "player_id": player_id,
        "history": history,
        "totals": {
            "seasons": total_seasons,
            "leagues": len(league_ids),
            "awards": total_awards,
            "championships": total_championships,
        },
    }


# ─── Auto-snapshot trigger (called from matchups.simulate_week) ─────────
@serialize_finances(lambda: _deps["db"])
async def _maybe_auto_snapshot_season(league_id: str):
    """Internal helper: when a league's last playoff matchup transitions
    to completed/final, automatically run complete-season.
    Called from matchups.simulate_week.
    Idempotent — checks current_season_status before snapshotting.
    """
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        return None
    # Already complete? Skip.
    if league.get("current_season_status") == "complete":
        return None

    # Are there ANY playoff matchups for this league?
    has_playoffs = await db.matchups.find_one({"league_id": league_id, "is_playoff": True})
    if not has_playoffs:
        return None
    # Final playoff week = max week among is_playoff matchups
    agg = await db.matchups.aggregate([
        {"$match": {"league_id": league_id, "is_playoff": True}},
        {"$group": {"_id": None, "max_week": {"$max": "$week"}}},
    ]).to_list(1)
    if not agg:
        return None
    final_week = agg[0]["max_week"]
    # Are ALL playoff matchups in the final week completed?
    pending = await db.matchups.count_documents({
        "league_id": league_id,
        "is_playoff": True,
        "week": final_week,
        "status": {"$nin": ["completed", "final"]},
    })
    if pending > 0:
        return None

    # Trigger the snapshot using the same logic as POST /complete-season
    season_year = league.get("current_season_year") or datetime.now(timezone.utc).year
    now = datetime.now(timezone.utc)
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    player_snapshot = await capture_players(db, teams)

    from services.salary_policy import payroll, obligations
    for team in teams:
        team["salary_used"] = (await payroll(db, team, league))["used"]
        team["retention_history"] = [{k: v for k, v in row.items() if k != "_id"}
                                     for row in await obligations(db, league, team, include_history=True)]

    teams_snapshot = []
    champion = None
    for t in teams:
        owner = await db.users.find_one(
            {"_id": t.get("owner_id")},
            {"username": 1, "name": 1},
        ) if t.get("owner_id") else None
        ts = {
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "logo_abbr": t.get("logo_abbr"),
            "logo_url": t.get("logo_url"),
            "owner_id": t.get("owner_id"),
            "co_owner_ids": t.get("co_owner_ids") or [],
            "profile_contributions": contributions(t),
            "profile_management_excluded_user_ids": t.get("profile_management_excluded_user_ids") or [],
            "xp_award_details": t.get("xp_award_details") or {},
            "owner_username": (owner or {}).get("username"),
            "owner_name": (owner or {}).get("name"),
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": float(t.get("points_for", 0.0) or 0.0),
            "points_against": float(t.get("points_against", 0.0) or 0.0),
            "live_points": float(t.get("live_points", 0.0) or 0.0),
            "division": t.get("division"),
            "conference": t.get("conference"),
            "salary_used": float(t.get("salary_used", 0.0) or 0.0),
            "retention_history": t.get("retention_history", []),
            "roster": list(t.get("roster") or []),
            "awards": {
                "championship_won_at": t.get("championship_won_at"),
                "consolation_won_at": t.get("consolation_won_at"),
                "division_winner_at": t.get("division_winner_at"),
                "conference_winner_at": t.get("conference_winner_at"),
                "playoffs_reached_at": t.get("playoffs_reached_at"),
                "playoff_runner_up_at": t.get("playoff_runner_up_at"),
            },
        }
        if t.get("championship_won_at"):
            champion = ts["team_name"]
        teams_snapshot.append(ts)

    champion_ids = await capture_standings(db, league, teams_snapshot)
    champion = next((t['team_name'] for t in teams_snapshot if t['team_id'] in champion_ids), None)
    for ts in teams_snapshot:
        if ts['team_id'] in champion_ids:
            if not ts['awards'].get('championship_won_at'):
                ts['awards']['championship_won_at'] = now.isoformat()
                from services.profile_competition import award_fields
                fields = await award_fields(db, ts['team_id'], {'championship_won_at': now.isoformat()})
                await db.teams.update_one({'_id': ObjectId(ts['team_id'])}, {'$set': fields})
                refreshed = await db.teams.find_one({'_id': ObjectId(ts['team_id'])})
                ts['profile_contributions'] = contributions(refreshed)
                ts['xp_award_details'] = refreshed.get('xp_award_details') or {}
                for uid in owners(ts):
                    ts['profile_contributions'].setdefault(uid, {})['championship_won_at'] = ts['awards']['championship_won_at']

    # Awards
    activity_cursor = db.activity_feed.find({
        "league_id": league_id,
        "event_type": {"$in": [
            "championship_awarded", "division_awarded",
            "conference_awarded", "consolation_awarded",
        ]},
    }).sort("created_at", -1)
    awards = []
    async for a in activity_cursor:
        awards.append({
            "event_type": a.get("event_type"),
            "description": a.get("description"),
            "created_at": a.get("created_at"),
        })

    scoring_config = await _snapshot_scoring_config(db, league_id)
    snapshot_doc = {
        "scoring_config": scoring_config,
        "league_id": league_id,
        "season_year": season_year,
        "status": "complete",
        "snapshot_at": now,
        "completed_by": "system",
        "completed_by_name": "System (auto-snapshot)",
        "champion_team_name": champion,
        "champion_team_id": champion_ids[0] if len(champion_ids) == 1 else None,
        "champion_team_ids": champion_ids,
        "salary_cap_config": {
            "enabled": bool(league.get("salary_cap_enabled")),
            "amount": league.get("salary_cap"),
            "retention_slots": league.get("salary_retention_slots", 3),
        },
        "schedule_config": league.get("schedule_config"),
        "playoff_config": {
            "playoff_teams": league.get("playoff_teams"),
            "playoff_weeks": league.get("playoff_weeks"),
            "playoff_start_week": league.get("playoff_start_week"),
            "playoff_rounds": league.get("playoff_rounds"),
        },
        "regular_season_weeks": league.get("regular_season_weeks"),
        "scoring_format": league.get("scoring_format"),
        "format": league.get("format"),
        "teams": teams_snapshot,
        "awards": awards,
        "players": player_snapshot,
        "auto_triggered": True,
    }
    await db.league_seasons.update_one(
        {"league_id": league_id, "season_year": season_year},
        {"$set": snapshot_doc},
        upsert=True,
    )
    if champion_ids:
        await db.teams.update_many({'_id': {'$in': [ObjectId(tid) for tid in champion_ids]}, '$or': [{'championship_won_at': None}, {'championship_won_at': ''}]}, {'$set': {'championship_won_at': now.isoformat()}})
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "current_season_year": season_year,
            "current_season_status": "complete",
            "season_completed_at": now,
            "auto_snapshot_at": now,
        }, "$push": {"audit_log": {
            "action": "season_auto_snapshotted",
            "by": "system",
            "season_year": season_year,
            "champion": champion,
            "trigger": "final_playoff_week_completed",
        }}},
    )
    # Best-effort socket emit so UI refreshes Health Card
    try:
        sio = _deps.get("sio")
        if sio:
            await sio.emit("season_auto_snapshotted", {
                "league_id": league_id,
                "season_year": season_year,
                "champion": champion,
            })
    except Exception:
        pass
    return {
        "league_id": league_id,
        "season_year": season_year,
        "champion": champion,
        "auto": True,
    }


@router.get("/teams/{team_id}/trophy-room")
async def get_team_trophy_room(team_id: str, request: Request):
    """Return all-time trophies for a single team."""
    user = await _deps["get_current_user"](request)
    db = _deps["db"]
    try:
        toid = ObjectId(team_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid team id")

    team = await db.teams.find_one({"_id": toid})
    historical = False
    if not team:
        snap = await db.league_seasons.find_one({'teams.team_id':team_id}, sort=[('season_year',-1)])
        if not snap:
            raise HTTPException(status_code=404, detail="Team not found")
        saved = next(t for t in snap['teams'] if t['team_id'] == team_id)
        team = {'name':saved.get('team_name'),'league_id':snap['league_id'],'logo_url':saved.get('logo_url'),'logo_abbr':saved.get('logo_abbr')}
        historical = True

    league_id = team["league_id"]
    await require_league_member(db, user, league_id)
    cursor = db.league_seasons.find({"league_id": league_id}).sort("season_year", -1)
    banners: list = []
    individual_awards: list = []
    seasons_played: list = []

    async for snap in cursor:
        yr = snap.get("season_year")
        my_team = next((t for t in (snap.get("teams") or []) if t.get("team_id") == team_id), None)
        if not my_team:
            continue
        rank, rank_basis = historical_rank(snap, my_team)
        seasons_played.append({
            "year": yr,
            "wins": my_team.get("wins"),
            "losses": my_team.get("losses"),
            "ties": my_team.get("ties"),
            "points_for": my_team.get("points_for"),
            "rank": rank,
            "rank_basis": rank_basis,
        })
        awards = my_team.get("awards") or {}
        season_card = _build_season_trophies(snap)
        if any(t['team_id'] == team_id for t in season_card['champions']):
            banners.append({"type": "championship", "year": yr})
        if any(t['team_id'] == team_id for t in season_card['presidents_trophies']):
            banners.append({"type": "presidents_trophy", "year": yr})
        if awards.get("division_winner_at"):
            banners.append({"type": "division", "year": yr, "division": my_team.get("division")})
        if awards.get("conference_winner_at"):
            banners.append({"type": "conference", "year": yr, "conference": my_team.get("conference")})
        if awards.get("consolation_won_at"):
            banners.append({"type": "consolation", "year": yr})

        # Individual: which of MY rostered players won league-wide trophies that year?
        my_pids = set(map(str, my_team.get("roster") or []))
        season_card = _build_season_trophies(snap)
        for ptrophy in season_card["player_awards"]:
            if ptrophy and ptrophy.get("player_id") in my_pids:
                individual_awards.append({
                    "label": ptrophy["label"],
                    "scoring_basis": ptrophy.get("scoring_basis"),
                    "year": yr,
                    "player_id": ptrophy["player_id"],
                    "player_name": ptrophy["player_name"],
                    "position": ptrophy.get("position"),
                    "team": ptrophy.get("team"),
                })

    return {
        "team_id": team_id,
        "team_name": team.get("name"),
        "historical_franchise": historical,
        "logo_url": team.get("logo_url"),
        "logo_abbr": team.get("logo_abbr"),
        "league_id": league_id,
        "seasons_played": seasons_played,
        "banners": banners,
        "individual_awards": individual_awards,
    }

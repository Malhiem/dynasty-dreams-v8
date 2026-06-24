"""Leagues router: enhanced standings (divisions/conferences/GB/movement) +
playoff bracket + division management (commissioner-only) + Iter 109: League CRUD
(create / list / get) extracted from server.py.
"""
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from utils.roster_rules import check_position_breakdown_within_caps

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Enums (extracted from server.py iter 109) ───────────────
class LeagueFormat(str, Enum):
    REDRAFT = "redraft"
    KEEPER = "keeper"
    DYNASTY = "dynasty"
    BEST_BALL = "best_ball"


class ScoringFormat(str, Enum):
    HEAD_TO_HEAD = "head_to_head"
    TOTAL_POINTS = "total_points"
    ROTISSERIE = "rotisserie"
    GUILLOTINE = "guillotine"
    ALL_PLAY = "all_play"


class DraftType(str, Enum):
    SNAKE = "snake"
    LINEAR = "linear"
    AUCTION = "auction"
    CUSTOM = "custom"


class UserRole(str, Enum):
    USER = "user"
    COMMISSIONER = "commissioner"
    ADMIN = "admin"


# ─── LeagueCreate / LeagueResponse Pydantic models (extracted iter 109) ───
class LeagueCreate(BaseModel):
    name: str
    sport: str = "nhl"
    format: LeagueFormat
    scoring_format: ScoringFormat
    max_teams: int = Field(default=12, ge=4, le=32)
    salary_cap_enabled: bool = False
    salary_cap: Optional[float] = None
    draft_type: DraftType = DraftType.SNAKE
    roster_spots: int = Field(default=20, ge=10, le=100)
    keepers_allowed: int = Field(default=0, ge=0, le=10)
    entry_fee: Optional[float] = None
    is_private: bool = False
    # Iter 219 — Head-to-Head only: number of matchups each team plays
    # per scoring week. Range 1 .. (max_teams - 1) enforced at the
    # endpoint. Defaults to 1 (classic single-matchup H2H).
    matchups_per_week: int = Field(default=1, ge=1, le=31)


class LeagueResponse(BaseModel):
    id: str
    name: str
    sport: str = "nhl"
    format: str
    scoring_format: str
    max_teams: int
    current_teams: int
    commissioner_id: str
    commissioner_name: str
    co_commissioners: List[str] = []
    salary_cap_enabled: bool
    salary_cap: Optional[float]
    draft_type: str
    roster_spots: Optional[int] = None
    keepers_allowed: int
    entry_fee: Optional[float]
    is_private: bool
    status: str
    invite_code: Optional[str] = None
    created_at: datetime
    setup_wizard_complete: bool = False
    # Extended wizard / commissioner-settable fields (single source of truth)
    bench_spots: Optional[int] = None
    minors_spots: Optional[int] = None
    trade_review_period_hours: Optional[int] = None
    trade_veto_threshold_pct: Optional[int] = None
    trade_deadline_week: Optional[int] = None
    trade_deadline_at: Optional[str] = None
    waiver_faab_budget: Optional[int] = None
    waiver_period_days: Optional[int] = None
    playoff_teams: Optional[int] = None
    playoff_start_week: Optional[int] = None
    playoff_rounds: Optional[int] = None
    playoff_end_week: Optional[int] = None
    regular_season_weeks: Optional[int] = None
    matchups_per_week: Optional[int] = None  # Iter 219
    salary_retention_enabled: Optional[bool] = None
    salary_retention_max_pct: Optional[int] = None
    salary_retention_slots: Optional[int] = None
    season_start_date: Optional[str] = None
    season_end_date: Optional[str] = None
    matchup_length_days: Optional[int] = None
    opponents_per_matchup_period: Optional[int] = None
    consolation_enabled: Optional[bool] = None
    consolation_start_week: Optional[int] = None
    consolation_end_week: Optional[int] = None
    consolation_uses_playoff_schedule: Optional[bool] = None
    ir_slots: Optional[int] = None
    ir_plus_slots: Optional[int] = None
    taxi_squad_size: Optional[int] = None
    position_limits: Optional[dict] = None
    position_breakdown: Optional[dict] = None
    enforce_position_maxes: Optional[bool] = None
    min_active_players: Optional[int] = None
    min_games_played: Optional[int] = None
    prorate_min_max_by_period: Optional[bool] = None
    allow_illegal_rosters: Optional[bool] = None
    ir_eligibility_modes: Optional[List[str]] = None
    roster_lock_type: Optional[str] = None
    roster_lock_day: Optional[str] = None
    roster_lock_second_day: Optional[str] = None
    lineup_lock_minutes_before: Optional[int] = None
    # Iter 194b — In-draft pick trade review settings (iter 191)
    draft_trade_review_minutes: Optional[int] = None
    draft_trade_post_delay_action: Optional[str] = None
    # Iter 195 (Task B) — Per-week playoff matchup length overrides.
    # Format: { "1": {"length_weeks": 1}, "2": {"length_weeks": 2}, ... }
    # Keys are playoff round numbers (1=wildcard / quarterfinals,
    # max=finals). When omitted the bracket falls back to the
    # league-wide `matchup_length_days`.
    playoff_week_lengths: Optional[dict] = None
    playoff_roster_lock_override: Optional[bool] = None
    playoff_roster_lock_type: Optional[str] = None
    playoff_roster_lock_day: Optional[str] = None
    playoff_roster_lock_second_day: Optional[str] = None
    playoff_lineup_lock_minutes_before: Optional[int] = None
    stats_count_start_date: Optional[str] = None
    stats_count_end_date: Optional[str] = None
    playoff_format: Optional[str] = None
    playoff_seeding_method: Optional[str] = None
    playoff_custom_matchups: Optional[List[dict]] = None
    consolation_teams: Optional[int] = None
    consolation_seeding_method: Optional[str] = None
    consolation_custom_matchups: Optional[List[dict]] = None
    emergency_changes_enabled: Optional[bool] = None
    emergency_changes_regular: Optional[int] = None
    emergency_changes_playoffs: Optional[int] = None
    emergency_eligibility: Optional[List[str]] = None
    emergency_changes_scope: Optional[str] = None
    differentiate_goalie_scoring: Optional[bool] = None
    goalie_scoring_method: Optional[str] = None
    goalie_best_x_count: Optional[int] = None
    goalie_avg_multiplier_count: Optional[int] = None
    goalie_gp_limit_enabled: Optional[bool] = None
    goalie_gp_limit: Optional[int] = None
    goalie_gp_count_method: Optional[str] = None
    # Iter 111 — Future-year salary caps + Contract Buyouts toggle
    salary_cap_year_plus_1: Optional[int] = None
    salary_cap_year_plus_2: Optional[int] = None
    salary_cap_year_plus_1_tentative: Optional[bool] = None
    salary_cap_year_plus_2_tentative: Optional[bool] = None
    contract_buyouts_enabled: Optional[bool] = None
    # Iter 226 — per-week matchup-length overrides
    week_overrides: Optional[list[dict]] = None


# ─── League CRUD endpoints (extracted iter 109) ──────────────
@router.post("/leagues", response_model=LeagueResponse)
async def create_league(input: LeagueCreate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    # Iter 219 — validate matchups_per_week for H2H formats
    scoring_value = input.scoring_format.value
    matchups_per_week = int(input.matchups_per_week or 1)
    is_h2h = scoring_value.startswith("h2h") or scoring_value.startswith("head_to_head") or "h2h" in scoring_value
    if is_h2h:
        if matchups_per_week < 1 or matchups_per_week > input.max_teams - 1:
            raise HTTPException(
                status_code=400,
                detail=f"matchups_per_week must be between 1 and {input.max_teams - 1} for H2H leagues",
            )
    else:
        # Non-H2H formats don't use this — force back to 1 for cleanliness
        matchups_per_week = 1

    league_doc = {
        "name": input.name,
        "sport": input.sport,
        "format": input.format.value,
        "scoring_format": scoring_value,
        "max_teams": input.max_teams,
        "current_teams": 1,  # commissioner is auto-joined
        "commissioner_id": user["_id"],
        "commissioner_name": user["name"],
        "salary_cap_enabled": input.salary_cap_enabled,
        "salary_cap": input.salary_cap if input.salary_cap_enabled else None,
        "draft_type": input.draft_type.value,
        "roster_spots": input.roster_spots,
        "keepers_allowed": input.keepers_allowed,
        "entry_fee": input.entry_fee,
        "is_private": input.is_private,
        "invite_code": secrets.token_urlsafe(8),
        "matchups_per_week": matchups_per_week,
        "status": "setup",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.leagues.insert_one(league_doc)
    league_id = str(result.inserted_id)

    # Iter 219 — Auto-create a team for the league commissioner so
    # they're immediately a member of the league they just created.
    # Without this, `useActiveLeague` returns null on /commissioner/settings
    # and the page renders a 404-style "no league selected" state.
    await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": user["_id"],
        "name": f"{user['name']}'s Team",
        "roster": [],
        "lineup": {},
        "is_commissioner_team": True,
        "created_at": datetime.now(timezone.utc),
    })

    # Promote requester to commissioner role if currently a plain user
    if user["role"] == UserRole.USER.value:
        await db.users.update_one(
            {"_id": ObjectId(user["_id"])},
            {"$set": {"role": UserRole.COMMISSIONER.value}},
        )

    return LeagueResponse(
        id=league_id,
        name=league_doc["name"],
        sport=league_doc.get("sport", "nhl"),
        format=league_doc["format"],
        scoring_format=league_doc["scoring_format"],
        max_teams=league_doc["max_teams"],
        current_teams=1,
        commissioner_id=league_doc["commissioner_id"],
        commissioner_name=league_doc["commissioner_name"],
        co_commissioners=league_doc.get("co_commissioners", []) or [],
        salary_cap_enabled=league_doc["salary_cap_enabled"],
        salary_cap=league_doc["salary_cap"],
        draft_type=league_doc["draft_type"],
        roster_spots=league_doc["roster_spots"],
        keepers_allowed=league_doc["keepers_allowed"],
        entry_fee=league_doc["entry_fee"],
        is_private=league_doc["is_private"],
        status=league_doc["status"],
        invite_code=league_doc.get("invite_code"),
        created_at=league_doc["created_at"],
        setup_wizard_complete=bool(league_doc.get("setup_wizard_complete", False)),
        matchups_per_week=league_doc.get("matchups_per_week"),
    )


def _league_to_response(league: dict) -> LeagueResponse:
    """Hydrate every LeagueResponse field from a raw Mongo league doc."""
    return LeagueResponse(
        id=str(league["_id"]),
        name=league["name"],
        sport=league.get("sport", "nhl"),
        format=league["format"],
        scoring_format=league["scoring_format"],
        max_teams=league["max_teams"],
        current_teams=league.get("current_teams", 0),
        commissioner_id=league["commissioner_id"],
        commissioner_name=league["commissioner_name"],
        co_commissioners=league.get("co_commissioners", []) or [],
        salary_cap_enabled=league["salary_cap_enabled"],
        salary_cap=league.get("salary_cap"),
        draft_type=league["draft_type"],
        roster_spots=league.get("roster_spots"),
        keepers_allowed=league["keepers_allowed"],
        entry_fee=league.get("entry_fee"),
        is_private=league["is_private"],
        status=league["status"],
        invite_code=league.get("invite_code"),
        created_at=league["created_at"],
        setup_wizard_complete=bool(league.get("setup_wizard_complete", False)),
        bench_spots=league.get("bench_spots"),
        minors_spots=league.get("minors_spots"),
        trade_review_period_hours=league.get("trade_review_period_hours"),
        trade_veto_threshold_pct=league.get("trade_veto_threshold_pct"),
        trade_deadline_week=league.get("trade_deadline_week"),
        trade_deadline_at=league.get("trade_deadline_at"),
        waiver_faab_budget=league.get("waiver_faab_budget"),
        waiver_period_days=league.get("waiver_period_days"),
        playoff_teams=league.get("playoff_teams"),
        playoff_start_week=league.get("playoff_start_week"),
        playoff_rounds=league.get("playoff_rounds"),
        playoff_end_week=league.get("playoff_end_week"),
        regular_season_weeks=league.get("regular_season_weeks"),
        salary_retention_enabled=league.get("salary_retention_enabled"),
        salary_retention_max_pct=league.get("salary_retention_max_pct"),
        salary_retention_slots=league.get("salary_retention_slots"),
        season_start_date=league.get("season_start_date"),
        season_end_date=league.get("season_end_date"),
        matchup_length_days=league.get("matchup_length_days"),
        opponents_per_matchup_period=league.get("opponents_per_matchup_period"),
        consolation_enabled=league.get("consolation_enabled"),
        consolation_start_week=league.get("consolation_start_week"),
        consolation_end_week=league.get("consolation_end_week"),
        consolation_uses_playoff_schedule=league.get("consolation_uses_playoff_schedule"),
        ir_slots=league.get("ir_slots"),
        ir_plus_slots=league.get("ir_plus_slots"),
        taxi_squad_size=league.get("taxi_squad_size"),
        position_limits=league.get("position_limits"),
        position_breakdown=league.get("position_breakdown"),
        enforce_position_maxes=league.get("enforce_position_maxes"),
        min_active_players=league.get("min_active_players"),
        min_games_played=league.get("min_games_played"),
        prorate_min_max_by_period=league.get("prorate_min_max_by_period"),
        allow_illegal_rosters=league.get("allow_illegal_rosters"),
        ir_eligibility_modes=league.get("ir_eligibility_modes"),
        roster_lock_type=league.get("roster_lock_type"),
        roster_lock_day=league.get("roster_lock_day"),
        roster_lock_second_day=league.get("roster_lock_second_day"),
        lineup_lock_minutes_before=league.get("lineup_lock_minutes_before"),
        # Iter 194b / 195
        draft_trade_review_minutes=league.get("draft_trade_review_minutes"),
        draft_trade_post_delay_action=league.get("draft_trade_post_delay_action"),
        playoff_week_lengths=league.get("playoff_week_lengths"),
        playoff_roster_lock_override=league.get("playoff_roster_lock_override"),
        playoff_roster_lock_type=league.get("playoff_roster_lock_type"),
        playoff_roster_lock_day=league.get("playoff_roster_lock_day"),
        playoff_roster_lock_second_day=league.get("playoff_roster_lock_second_day"),
        playoff_lineup_lock_minutes_before=league.get("playoff_lineup_lock_minutes_before"),
        stats_count_start_date=league.get("stats_count_start_date"),
        stats_count_end_date=league.get("stats_count_end_date"),
        playoff_format=league.get("playoff_format"),
        playoff_seeding_method=league.get("playoff_seeding_method"),
        playoff_custom_matchups=league.get("playoff_custom_matchups"),
        consolation_teams=league.get("consolation_teams"),
        consolation_seeding_method=league.get("consolation_seeding_method"),
        consolation_custom_matchups=league.get("consolation_custom_matchups"),
        emergency_changes_enabled=league.get("emergency_changes_enabled"),
        emergency_changes_regular=league.get("emergency_changes_regular"),
        emergency_changes_playoffs=league.get("emergency_changes_playoffs"),
        emergency_eligibility=league.get("emergency_eligibility"),
        emergency_changes_scope=league.get("emergency_changes_scope"),
        differentiate_goalie_scoring=league.get("differentiate_goalie_scoring"),
        goalie_scoring_method=league.get("goalie_scoring_method"),
        goalie_best_x_count=league.get("goalie_best_x_count"),
        goalie_avg_multiplier_count=league.get("goalie_avg_multiplier_count"),
        goalie_gp_limit_enabled=league.get("goalie_gp_limit_enabled"),
        goalie_gp_limit=league.get("goalie_gp_limit"),
        goalie_gp_count_method=league.get("goalie_gp_count_method"),
        salary_cap_year_plus_1=league.get("salary_cap_year_plus_1"),
        salary_cap_year_plus_2=league.get("salary_cap_year_plus_2"),
        salary_cap_year_plus_1_tentative=league.get("salary_cap_year_plus_1_tentative"),
        salary_cap_year_plus_2_tentative=league.get("salary_cap_year_plus_2_tentative"),
        contract_buyouts_enabled=league.get("contract_buyouts_enabled"),
        week_overrides=league.get("week_overrides"),
    )


@router.get("/leagues", response_model=List[LeagueResponse])
async def get_leagues(
    request: Request,
    my_leagues: bool = False,  # kept for backward compat (same as default)
    discover: bool = False,
    all: bool = False,
):
    """Iter 221 — Privacy hardening. By default the endpoint only returns
    leagues the current user is a member of (team owner or commissioner).
    `discover=true` returns public leagues the user has NOT joined (for the
    "browse" experience). `all=true` returns every league but is gated to
    platform admins. Unauthenticated callers get an empty list.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = None
    try:
        user = await get_current_user(request)
    except Exception:
        pass

    if not user:
        # Anonymous: only allow public discovery
        if discover or not my_leagues:
            leagues = await db.leagues.find({"is_private": False}).to_list(100)
            return [_league_to_response(league) for league in leagues]
        return []

    is_admin = (user.get("role") == "admin") or (
        user.get("permission_tier") in ("admin", "senior_admin", "owner")
    )

    # Resolve the user's own league ids (team membership + commissioner roles)
    user_teams = await db.teams.find({"owner_id": user["_id"]}, {"league_id": 1}).to_list(500)
    member_league_ids = list({t["league_id"] for t in user_teams})
    member_object_ids = []
    for lid in member_league_ids:
        try:
            member_object_ids.append(ObjectId(lid))
        except Exception:
            continue

    if all and is_admin:
        leagues = await db.leagues.find({}).sort("created_at", -1).to_list(500)
        return [_league_to_response(league) for league in leagues]

    if discover:
        # Public leagues the user is NOT already a member/commissioner of.
        # Sort newest-first so freshly created leagues are immediately visible.
        query = {
            "is_private": False,
            "_id": {"$nin": member_object_ids},
            "commissioner_id": {"$ne": user["_id"]},
        }
        leagues = (
            await db.leagues.find(query)
            .sort("created_at", -1)
            .to_list(200)
        )
        return [_league_to_response(league) for league in leagues]

    # Default + my_leagues=true → membership-scoped results only
    query = {
        "$or": [
            {"commissioner_id": user["_id"]},
            {"_id": {"$in": member_object_ids}},
        ]
    }
    leagues = await db.leagues.find(query).to_list(200)
    return [_league_to_response(league) for league in leagues]


@router.get("/leagues/{league_id}", response_model=LeagueResponse)
async def get_league(league_id: str):
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return _league_to_response(league)


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
    """Sort teams by W desc, PF desc. Deterministic tiebreaker on team _id
    so that two consecutive ranks (e.g. matchup-gen + bracket-render) agree
    even when many teams share 0-0 records.
    """
    return sorted(
        teams,
        key=lambda t: (
            -(t.get("wins", 0) or 0),
            -_score(t),
            str(t.get("_id") or ""),
        ),
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
                # Iter 199 — Finish-wizard backfill: stamp every section
                # complete so the Health Score hits 100 when the wizard's
                # explicit "Finish" path completes.
                "setup_progress": {
                    "basics": True, "cap": True, "divisions": True,
                    "schedule": True, "playoffs": True, "draft": True,
                    "trades": True,
                },
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
    # Iter 225 — Allow finishing the wizard with placeholder slots.
    # The schedule generator now pads up to `max_teams` with "Open Slot N"
    # placeholders so an empty league can still ship a working schedule;
    # we only block when there's nothing meaningful to schedule at all.
    teams_count = await db.teams.count_documents({"league_id": league_id})
    max_teams = int(league.get("max_teams") or 0)
    effective_slots = max(teams_count, max_teams)
    if effective_slots < 2:
        issues.append(
            "Set `max teams` to at least 2 (Basics step) or invite a second manager "
            "before finishing — even an all-placeholder league needs ≥2 slots."
        )
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "teams_count": teams_count,
        "max_teams": max_teams,
        "open_slot_count": max(0, max_teams - teams_count),
    }


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


def _build_consolation_block(league: dict, teams: list, team_to_slot_fn, playoff_size: int) -> dict | None:
    """Iter 196 (Task C) — build a consolation-bracket payload from the

    Output shape mirrors the main bracket (`rounds`, `seeds`) so the
    frontend can reuse the round-rendering component.
    """
    if not league.get("consolation_enabled"):
        return None
    ranked = _rank_teams(teams)
    if len(ranked) <= playoff_size:
        return None
    available = ranked[playoff_size:]
    requested = league.get("consolation_teams")
    try:
        requested = int(requested) if requested is not None else len(available)
    except (TypeError, ValueError):
        requested = len(available)
    consolation_size = max(2, min(requested, len(available)))
    # Round consolation_size DOWN to nearest power-of-two for clean bracket math.
    pow2 = 1
    while pow2 * 2 <= consolation_size:
        pow2 *= 2
    consolation_size = pow2
    if consolation_size < 2:
        return None

    # Seed within consolation: seed 1 = best record among non-playoff teams
    cons_teams = available[:consolation_size]
    slots = [team_to_slot_fn(t, i + 1) for i, t in enumerate(cons_teams)]
    seeding_method = league.get("consolation_seeding_method") or "high_vs_low"
    rounds = _build_single_elim_rounds(slots, seeding_method)
    return {
        "size": consolation_size,
        "seeding_method": seeding_method,
        "seeds": slots,
        "rounds": rounds,
    }


def _annotate_rounds_with_week_lengths(rounds: list, week_lengths: dict | None) -> None:
    """Iter 196 (Task B) — stamp `length_weeks` (default 1) onto each round
    based on `league.playoff_week_lengths` keyed by 1-based round index."""
    if not rounds:
        return
    wl = week_lengths or {}
    for idx, rd in enumerate(rounds, start=1):
        entry = wl.get(str(idx)) or wl.get(idx) or {}
        try:
            length = int(entry.get("length_weeks", 1)) if isinstance(entry, dict) else int(entry)
        except (TypeError, ValueError):
            length = 1
        rd["length_weeks"] = max(1, length)


async def _derive_champion_block(rounds_built: list, payout_doc: dict | None, team_lookup: dict) -> dict:
    """Iter 197 — extract champion + runner-up from the final round's
    completed matchup (if any) AND merge the persisted prize-distribution
    payload so the frontend can render the "Award Prizes" CTA + the
    "Distributed" summary side-by-side.
    """
    champion_id = None
    runner_up_id = None
    final_mu = None
    if rounds_built:
        final_round = rounds_built[-1]
        if final_round.get("matchups"):
            final_mu = final_round["matchups"][0]
            if final_mu.get("status") in ("completed", "final"):
                hs = final_mu.get("high_seed") or {}
                ls = final_mu.get("low_seed") or {}
                winner_id = final_mu.get("projected_winner")
                if winner_id:
                    champion_id = winner_id
                    runner_up_id = ls["team_id"] if winner_id == hs.get("team_id") else hs.get("team_id")

    def _team_summary(tid: str | None) -> dict | None:
        if not tid:
            return None
        t = team_lookup.get(str(tid))
        if not t:
            return {"team_id": str(tid)}
        return {
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "team_abbr": t.get("logo_abbr"),
            "owner_name": t.get("owner_name"),
        }

    block = {
        "decided": champion_id is not None,
        "champion": _team_summary(champion_id),
        "runner_up": _team_summary(runner_up_id),
        "final_matchup_id": final_mu.get("matchup_id") if final_mu else None,
    }
    # Iter 197 — only surface payout fields once the championship has been
    # decided. Avoids a stale "distributed" flag confusing clients that
    # consume it independently of `decided`.
    if payout_doc and champion_id is not None:
        block["distributed"] = True
        block["champion_prize"] = payout_doc.get("champion_prize")
        block["runner_up_prize"] = payout_doc.get("runner_up_prize")
        block["consolation_prize"] = payout_doc.get("consolation_prize")
        block["currency"] = payout_doc.get("currency") or "USD"
        block["distributed_at"] = payout_doc.get("distributed_at")
        block["note"] = payout_doc.get("note")
        block["consolation_champion_id"] = payout_doc.get("consolation_champion_team_id")
        block["consolation_champion"] = _team_summary(payout_doc.get("consolation_champion_team_id"))
    else:
        block["distributed"] = False
    return block


def _build_single_elim_rounds(slots: list, seeding_method: str, label_prefix: str = "") -> list:
    """Iter 196 (Task C helper) — generic single-elimination bracket from an
    already-seeded slot list. `seeding_method` is "high_vs_low" or "adjacent".
    Used for the consolation bracket. Produces rounds with `projected_winner`
    set to the higher seed of each matchup. Round names: R1, Semifinals,
    Championship for ≤8-team brackets; otherwise `Round N`.
    """
    n = len(slots)
    if n < 2:
        return []

    def _mu(hi: dict, lo: dict) -> dict:
        return {
            "high_seed": hi,
            "low_seed": lo,
            "projected_winner": hi["team_id"] if hi else None,
            "status": "projected",
        }

    # Round 1 matchups by seeding method
    if seeding_method == "adjacent":
        r1 = [_mu(slots[i], slots[i + 1]) for i in range(0, n - 1, 2)]
    else:  # high_vs_low default
        r1 = [_mu(slots[i], slots[n - 1 - i]) for i in range(n // 2)]

    rounds: list = []

    def round_name_for_count(mucount: int) -> str:
        if mucount == 1:
            return "Championship"
        if mucount == 2:
            return "Semifinals"
        if mucount == 4:
            return "Quarterfinals"
        return f"Round of {mucount * 2}"

    rounds.append({"name": f"{label_prefix}{round_name_for_count(len(r1))}", "matchups": r1})

    # Subsequent rounds: bracket winners advance — projected winners are the higher seed.
    advancing = [m["high_seed"] for m in r1]
    while len(advancing) > 1:
        nxt = []
        for i in range(0, len(advancing) - 1, 2):
            nxt.append(_mu(advancing[i], advancing[i + 1]))
        rounds.append({
            "name": f"{label_prefix}{round_name_for_count(len(nxt))}",
            "matchups": nxt,
        })
        advancing = [m["high_seed"] for m in nxt]
    return rounds


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

    # Helper used by both the actual-bracket and projected-bracket branches
    seeded_for_helper = _rank_teams(teams)[:playoff_size]
    overall_leader = seeded_for_helper[0] if seeded_for_helper else None

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

    # ── Iter 104: if persisted playoff matchups exist (generated via iter-102),
    # build rounds DIRECTLY from them so we honor the configured seeding method
    # (high_vs_low / adjacent / custom). Falls back to the projected hardcoded
    # logic below when no `is_playoff` matchups exist yet.
    persisted_playoff = await db.matchups.find({
        "league_id": league_id,
        "is_playoff": True,
    }).to_list(200)
    if persisted_playoff:
        team_lookup = {str(t["_id"]): t for t in teams}
        ranked = _rank_teams(teams)
        seed_lookup = {str(t["_id"]): idx + 1 for idx, t in enumerate(ranked)}

        def _slot_from_team_id(tid):
            t = team_lookup.get(str(tid or ""))
            if not t:
                return None
            return _team_to_slot(t, seed_lookup.get(str(t["_id"]), 99))

        # Group by bracket_round (default = 1 for legacy data)
        by_round: dict = {}
        for m in persisted_playoff:
            rnd = int(m.get("bracket_round") or 1)
            by_round.setdefault(rnd, []).append(m)

        # Iter 197 — derive round name from distance-from-final (NOT absolute
        # round number) so an 8-team / 3-round bracket reads QF → SF → Final
        # instead of "Round 1 → Quarterfinals → Championship".
        configured_rounds = int(league.get("playoff_rounds") or 0)
        max_round = max(by_round.keys()) if by_round else 1
        total_rounds = max(max_round, configured_rounds, 1)

        def _name_for_round(rnd_1based: int) -> str:
            distance = total_rounds - rnd_1based  # 0=final, 1=semis, 2=QF, 3=R16
            if distance <= 0:
                return "Championship"
            if distance == 1:
                return "Semifinals"
            if distance == 2:
                return "Quarterfinals"
            if distance == 3:
                return "Round of 16"
            return f"Round {rnd_1based}"

        # Iter 197 — synthesize missing TBD matchups so each intermediate round
        # carries the correct count (2^(total_rounds - rnd)). The iter-107
        # labelling pass below stamps "Winner of X vs Y" onto the TBD slots.
        for rnd_idx in range(1, total_rounds + 1):
            expected = 2 ** (total_rounds - rnd_idx)
            cur = by_round.get(rnd_idx, [])
            while len(cur) < expected:
                cur.append({
                    "league_id": league_id,
                    "bracket_round": rnd_idx,
                    "home_team_tbd": True,
                    "away_team_tbd": True,
                    "home_team_id": None,
                    "away_team_id": None,
                    "status": "scheduled",
                    "_synthetic": True,
                })
            by_round[rnd_idx] = cur

        rounds_built: list = []
        for rnd_idx in sorted(by_round.keys()):
            matchups_out: list = []
            for m in by_round[rnd_idx]:
                hs = None if m.get("home_team_tbd") else _slot_from_team_id(m.get("home_team_id"))
                ls = None if m.get("away_team_tbd") else _slot_from_team_id(m.get("away_team_id"))
                home_score = m.get("home_score")
                away_score = m.get("away_score")
                status = m.get("status", "scheduled")
                projected_winner = None
                if status in ("completed", "final") and home_score is not None and away_score is not None:
                    if float(home_score) > float(away_score):
                        projected_winner = m.get("home_team_id")
                    elif float(away_score) > float(home_score):
                        projected_winner = m.get("away_team_id")
                elif hs and ls:
                    projected_winner = hs["team_id"]  # projection = higher seed
                matchups_out.append({
                    "matchup_id": str(m["_id"]) if m.get("_id") else None,
                    "high_seed": hs,
                    "low_seed": ls,
                    "projected_winner": projected_winner,
                    "status": status if status != "scheduled" else "actual",
                    "home_score": home_score,
                    "away_score": away_score,
                    "week": m.get("week"),
                    "home_team_id": str(m.get("home_team_id")) if m.get("home_team_id") else None,
                    "away_team_id": str(m.get("away_team_id")) if m.get("away_team_id") else None,
                    "is_synthetic": bool(m.get("_synthetic")),
                })
            label = _name_for_round(rnd_idx)
            rounds_built.append({"name": label, "matchups": matchups_out})

        # Compute byes: any seeded team NOT in Round 1 matchups
        r1_teams = set()
        for mu in rounds_built[0]["matchups"] if rounds_built else []:
            for slot in (mu.get("high_seed"), mu.get("low_seed")):
                if slot:
                    r1_teams.add(slot["team_id"])
        seeded = _rank_teams(teams)[:playoff_size]
        playoff_teams_out = [_team_to_slot(t, i + 1) for i, t in enumerate(seeded)]
        bye_teams_out = [pt for pt in playoff_teams_out if pt["team_id"] not in r1_teams]
        if rounds_built and bye_teams_out:
            rounds_built[0]["byes"] = bye_teams_out

        # ── Iter 107: Auto-label "Winner of A vs B" for TBD slots ──
        # For each Round N TBD slot, find its parent matchup(s) in Round N-1.
        # Standard bracket math: matchup i in round N feeds from matchups
        # (2i, 2i+1) in round N-1. The label is either the actual completed
        # winner's name OR "Winner of {home_abbr} vs {away_abbr}".
        for i in range(1, len(rounds_built)):
            prev = rounds_built[i - 1]["matchups"]
            curr = rounds_built[i]["matchups"]
            for j, mu in enumerate(curr):
                # Parent slots: 2j (feeds home), 2j+1 (feeds away)
                parents = [(2 * j, "home"), (2 * j + 1, "away")]
                for parent_idx, side in parents:
                    if parent_idx >= len(prev):
                        continue
                    p = prev[parent_idx]
                    side_slot = mu.get("high_seed" if side == "home" else "low_seed")
                    if side_slot is not None:
                        continue  # actual team already assigned
                    hs, ls = p.get("high_seed"), p.get("low_seed")
                    if hs and ls:
                        p_status = p.get("status")
                        if p_status in ("completed", "final") and p.get("projected_winner"):
                            wname = (
                                hs["team_name"] if p["projected_winner"] == hs["team_id"]
                                else ls["team_name"]
                            )
                            label_str = f"Winner: {wname}"
                        else:
                            ha = hs.get("team_abbr") or hs.get("team_name") or "?"
                            la = ls.get("team_abbr") or ls.get("team_name") or "?"
                            label_str = f"Winner of {ha} vs {la}"
                        mu[f"{'high' if side == 'home' else 'low'}_seed_label"] = label_str

        # Iter 196 — annotate per-round length + emit consolation
        _annotate_rounds_with_week_lengths(rounds_built, league.get("playoff_week_lengths"))
        consolation_block = _build_consolation_block(league, teams, _team_to_slot, playoff_size)

        # Iter 197 — derive champion from the final round's completed matchup
        # (if any) + attach the persisted prize distribution.
        payout_doc = await db.payouts.find_one({"league_id": league_id}) if rounds_built else None
        champion_block = await _derive_champion_block(rounds_built, payout_doc, team_lookup)

        return {
            "league_id": league_id,
            "playoff_size": playoff_size,
            "playoff_teams": playoff_teams_out,
            "bye_teams": bye_teams_out,
            "rounds": rounds_built,
            "status": "actual",
            "seeding_method": league.get("playoff_seeding_method") or "high_vs_low",
            "playoff_format": league.get("playoff_format") or "h2h_matchup",
            "playoff_week_lengths": league.get("playoff_week_lengths") or {},
            "consolation_enabled": bool(league.get("consolation_enabled")),
            "consolation_bracket": consolation_block,
            "champion": champion_block,
        }

    # Seed by overall rank
    seeded = _rank_teams(teams)[:playoff_size]

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

    # Iter 196 — annotate per-round length + emit consolation
    _annotate_rounds_with_week_lengths(rounds, league.get("playoff_week_lengths"))
    consolation_block = _build_consolation_block(league, teams, _team_to_slot, playoff_size)

    return {
        "league_id": league_id,
        "playoff_size": playoff_size,
        "playoff_teams": playoff_teams_out,
        "bye_teams": bye_teams_out,
        "rounds": rounds,
        "status": "actual" if actual_matchups else "projected",
        "seeding_method": league.get("playoff_seeding_method") or "high_vs_low",
        "playoff_format": league.get("playoff_format") or "h2h_matchup",
        "playoff_week_lengths": league.get("playoff_week_lengths") or {},
        "consolation_enabled": bool(league.get("consolation_enabled")),
        "consolation_bracket": consolation_block,
    }


# ─── Premium feature settings (salary cap, minors) + 14-day trial clock ───
class CapSettingsUpdate(BaseModel):
    salary_cap_enabled: Optional[bool] = None
    salary_cap: Optional[int] = None
    # Iter 111 — future-year caps + "tentative" flags, consumed by the
    # Depth-Chart / Salary-Cap / Analytics pages for multi-year planning.
    salary_cap_year_plus_1: Optional[int] = None
    salary_cap_year_plus_2: Optional[int] = None
    salary_cap_year_plus_1_tentative: Optional[bool] = None
    salary_cap_year_plus_2_tentative: Optional[bool] = None
    # Iter 111 — Contract Buyouts toggle (Transactions section). When enabled,
    # buyouts may create dead-cap charges over subsequent seasons.
    contract_buyouts_enabled: Optional[bool] = None
    salary_retention_slots: Optional[int] = Field(None, ge=0, le=10)
    minors_enabled: Optional[bool] = None  # if your league offers a minor-league/prospects pool
    # Iter 120 — Salary cap FLOOR (mirrors the ceiling shape)
    cap_floor_enabled: Optional[bool] = None
    cap_floor: Optional[int] = None
    cap_floor_year_plus_1: Optional[int] = None
    cap_floor_year_plus_2: Optional[int] = None
    cap_floor_year_plus_1_tentative: Optional[bool] = None
    cap_floor_year_plus_2_tentative: Optional[bool] = None


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
            # Iter 117 bug fix — disabling the cap must also clear current
            # and future-year amounts so the league can't end up in the
            # inconsistent "disabled with $88M Year+2 still set" state that
            # made teams appear cap-locked when their league record said
            # otherwise. Tentative flags are reset to false for cleanliness.
            updates["salary_cap"] = None
            updates["salary_cap_year_plus_1"] = None
            updates["salary_cap_year_plus_2"] = None
            updates["salary_cap_year_plus_1_tentative"] = False
            updates["salary_cap_year_plus_2_tentative"] = False
        elif payload.salary_cap is not None:
            updates["salary_cap"] = int(payload.salary_cap)
    elif payload.salary_cap is not None:
        updates["salary_cap"] = int(payload.salary_cap)
    if payload.salary_retention_slots is not None:
        updates["salary_retention_slots"] = int(payload.salary_retention_slots)
    if payload.minors_enabled is not None:
        updates["minors_enabled"] = bool(payload.minors_enabled)
    # Iter 111 — future-year caps + tentative flags
    if payload.salary_cap_year_plus_1 is not None:
        updates["salary_cap_year_plus_1"] = int(payload.salary_cap_year_plus_1)
    if payload.salary_cap_year_plus_2 is not None:
        updates["salary_cap_year_plus_2"] = int(payload.salary_cap_year_plus_2)
    if payload.salary_cap_year_plus_1_tentative is not None:
        updates["salary_cap_year_plus_1_tentative"] = bool(payload.salary_cap_year_plus_1_tentative)
    if payload.salary_cap_year_plus_2_tentative is not None:
        updates["salary_cap_year_plus_2_tentative"] = bool(payload.salary_cap_year_plus_2_tentative)
    if payload.contract_buyouts_enabled is not None:
        updates["contract_buyouts_enabled"] = bool(payload.contract_buyouts_enabled)

    # ── Iter 120 — Salary cap FLOOR (parallels the ceiling) ────────
    # Floor is only meaningful when the ceiling is enabled. When the
    # ceiling flips off, floor goes off + values clear (same defensive
    # pattern as the iter-117 ceiling-orphan fix).
    if payload.cap_floor_enabled is not None:
        updates["cap_floor_enabled"] = bool(payload.cap_floor_enabled)
        if not payload.cap_floor_enabled:
            updates["cap_floor"] = None
            updates["cap_floor_year_plus_1"] = None
            updates["cap_floor_year_plus_2"] = None
            updates["cap_floor_year_plus_1_tentative"] = False
            updates["cap_floor_year_plus_2_tentative"] = False
        elif payload.cap_floor is not None:
            updates["cap_floor"] = int(payload.cap_floor)
    elif payload.cap_floor is not None:
        updates["cap_floor"] = int(payload.cap_floor)
    if payload.cap_floor_year_plus_1 is not None:
        updates["cap_floor_year_plus_1"] = int(payload.cap_floor_year_plus_1)
    if payload.cap_floor_year_plus_2 is not None:
        updates["cap_floor_year_plus_2"] = int(payload.cap_floor_year_plus_2)
    if payload.cap_floor_year_plus_1_tentative is not None:
        updates["cap_floor_year_plus_1_tentative"] = bool(payload.cap_floor_year_plus_1_tentative)
    if payload.cap_floor_year_plus_2_tentative is not None:
        updates["cap_floor_year_plus_2_tentative"] = bool(payload.cap_floor_year_plus_2_tentative)

    # If the ceiling is being disabled in this same call, also clear the
    # floor — keeping the floor while the ceiling is off would be
    # ambiguous and re-introduces the same orphan class we fixed in 117.
    if payload.salary_cap_enabled is False:
        updates["cap_floor_enabled"] = False
        updates["cap_floor"] = None
        updates["cap_floor_year_plus_1"] = None
        updates["cap_floor_year_plus_2"] = None
        updates["cap_floor_year_plus_1_tentative"] = False
        updates["cap_floor_year_plus_2_tentative"] = False

    # Start the trial clock the first time any premium feature is enabled
    # AND the league hasn't paid yet. Iter 225 — STICKY once started: we no
    # longer wipe `premium_trial_started_at` when features are toggled off.
    # Previously each toggle off/on in the setup wizard reset the 14-day
    # window, so the banner appeared to "rewind" to 13 days left on later
    # wizard steps. Trial is anchored to its first activation and only
    # cleared when the league pays.
    new_cap = updates.get("salary_cap_enabled", league.get("salary_cap_enabled"))
    new_min = updates.get("minors_enabled", league.get("minors_enabled"))
    any_premium = bool(new_cap or new_min)
    if any_premium and not league.get("premium") and not league.get("premium_trial_started_at"):
        updates["premium_trial_started_at"] = datetime.now(timezone.utc)

    if updates:
        await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": updates})
    fresh = await db.leagues.find_one({"_id": ObjectId(league_id)})
    return {
        "salary_cap_enabled": bool(fresh.get("salary_cap_enabled")),
        "salary_cap": fresh.get("salary_cap"),
        "salary_cap_year_plus_1": fresh.get("salary_cap_year_plus_1"),
        "salary_cap_year_plus_2": fresh.get("salary_cap_year_plus_2"),
        "salary_cap_year_plus_1_tentative": bool(fresh.get("salary_cap_year_plus_1_tentative")),
        "salary_cap_year_plus_2_tentative": bool(fresh.get("salary_cap_year_plus_2_tentative")),
        "contract_buyouts_enabled": bool(fresh.get("contract_buyouts_enabled")),
        "cap_floor_enabled": bool(fresh.get("cap_floor_enabled")),
        "cap_floor": fresh.get("cap_floor"),
        "cap_floor_year_plus_1": fresh.get("cap_floor_year_plus_1"),
        "cap_floor_year_plus_2": fresh.get("cap_floor_year_plus_2"),
        "cap_floor_year_plus_1_tentative": bool(fresh.get("cap_floor_year_plus_1_tentative")),
        "cap_floor_year_plus_2_tentative": bool(fresh.get("cap_floor_year_plus_2_tentative")),
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
    roster_spots: Optional[int] = Field(default=None, ge=10, le=100)
    bench_spots: Optional[int] = Field(default=None, ge=0, le=20)
    minors_spots: Optional[int] = Field(default=None, ge=0, le=100)
    # Format + scoring
    scoring_format: Optional[str] = None
    # Iter 226 — `format` (dynasty/keeper/redraft) is editable from the
    # wizard's Basics step, so it needs to be in the sparse update model.
    format: Optional[str] = None
    max_teams: Optional[int] = Field(default=None, ge=2, le=32)
    keepers_allowed: Optional[int] = Field(default=None, ge=0, le=30)
    entry_fee: Optional[float] = Field(default=None, ge=0)
    # Trade settings
    trade_review_period_hours: Optional[int] = Field(default=None, ge=0, le=168)
    trade_veto_threshold_pct: Optional[int] = Field(default=None, ge=0, le=100)
    trade_deadline_week: Optional[int] = Field(default=None, ge=1, le=30)
    # Iter 128 — explicit trade deadline datetime (ISO 8601, UTC). When set,
    # takes precedence over `trade_deadline_week`. Allows the LM to specify a
    # precise moment (e.g. "March 7, 2026 at 3:00 PM ET") rather than a coarse
    # week number. None = fall back to week-based enforcement.
    trade_deadline_at: Optional[str] = Field(default=None, max_length=40)
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
    # Iter 226 — Per-week matchup-length overrides for irregular periods
    # (late season starts, post-break weeks, all-star, etc). Each entry:
    #   {week_num: int (1..30), length_days: int (1..21), label?: str}
    # The schedule generator widens the named week's calendar window
    # without shifting subsequent weeks ("absorb" semantics).
    week_overrides: Optional[list[dict]] = Field(default=None)
    # Consolation bracket
    consolation_enabled: Optional[bool] = None
    consolation_start_week: Optional[int] = Field(default=None, ge=1, le=40)
    consolation_end_week: Optional[int] = Field(default=None, ge=1, le=40)
    consolation_uses_playoff_schedule: Optional[bool] = None
    # ── Iter 81: extended roster controls ───────────────────────
    # All optional; legacy leagues without these fields fall back to historic
    # defaults at runtime (no migration required for existing leagues).
    ir_slots: Optional[int] = Field(default=None, ge=0, le=15)
    ir_plus_slots: Optional[int] = Field(default=None, ge=0, le=10)
    taxi_squad_size: Optional[int] = Field(default=None, ge=0, le=100)
    position_limits: Optional[dict] = None  # e.g. {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 3}
    # Iter 176 — Position Breakdown: per-section position caps.
    #   {"active": {"S": 18, "G": 2, ...}, "bench": {...}, "minors": {...}}
    # Untouched cell = no limit for that position in that section.
    position_breakdown: Optional[dict] = None
    enforce_position_maxes: Optional[bool] = None
    min_active_players: Optional[int] = Field(default=None, ge=0, le=40)
    min_games_played: Optional[int] = Field(default=None, ge=0, le=200)
    prorate_min_max_by_period: Optional[bool] = None
    allow_illegal_rosters: Optional[bool] = None
    ir_eligibility_modes: Optional[List[str]] = None  # e.g. ["IR", "IR-LT"]
    # ── Iter 100: Roster lock + lineup lock + NHL stats window ───
    # Roster lock cadence governs when a manager's lineup is frozen for the
    # scoring period. `lineup_lock_minutes_before` is the cushion (0..1440)
    # before the first NHL game of the period when individual slots lock,
    # snapped to 5-minute increments client-side.
    roster_lock_type: Optional[str] = Field(default=None, pattern=r"^(daily|semi_weekly|weekly)$")
    roster_lock_day: Optional[str] = None  # e.g. "monday"
    roster_lock_second_day: Optional[str] = None  # semi-weekly only
    lineup_lock_minutes_before: Optional[int] = Field(default=None, ge=0, le=1440)
    # Playoff override — when toggled ON, the playoff_* lock fields replace
    # the regular-season lock config during playoff weeks only.
    playoff_roster_lock_override: Optional[bool] = None
    playoff_roster_lock_type: Optional[str] = Field(default=None, pattern=r"^(daily|semi_weekly|weekly)$")
    playoff_roster_lock_day: Optional[str] = None
    playoff_roster_lock_second_day: Optional[str] = None
    playoff_lineup_lock_minutes_before: Optional[int] = Field(default=None, ge=0, le=1440)
    # NHL stats-counting window (commissioner picks an NHL-calendar week range)
    stats_count_start_date: Optional[str] = Field(default=None, max_length=20)
    stats_count_end_date: Optional[str] = Field(default=None, max_length=20)
    # Iter 194b — In-draft pick trade review configuration (iter 191)
    draft_trade_review_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    draft_trade_post_delay_action: Optional[str] = Field(
        default=None,
        pattern=r"^(auto_execute|pause_draft|extend_timer|require_admin|majority_vote)$",
    )
    # Iter 195 (Task B) — Per-week playoff matchup-length overrides.
    # Keys = playoff round number as string; value = `{length_weeks: int}`.
    playoff_week_lengths: Optional[dict] = None
    # ── Iter 101: Playoff bracket + Consolation bracket configuration ───
    # Playoff format: "h2h_matchup" mirrors regular-season scoring; "playoff_tree" runs
    # an elimination bracket. Seeding methods: high_vs_low (1vN, 2vN-1…), adjacent
    # (1v2, 3v4…), or custom (commissioner-built matchup ladder).
    playoff_format: Optional[str] = Field(default=None, pattern=r"^(h2h_matchup|playoff_tree)$")
    playoff_seeding_method: Optional[str] = Field(default=None, pattern=r"^(high_vs_low|adjacent|custom)$")
    # Custom ladder: [{week, matchups: [{home, away, label?}]}]
    # `home`/`away` are team_id strings OR the literal "tbd" sentinel.
    playoff_custom_matchups: Optional[List[dict]] = None
    # Consolation bracket — count of teams (0..N-playoff_teams), same seeding knobs.
    consolation_teams: Optional[int] = Field(default=None, ge=0, le=32)
    consolation_seeding_method: Optional[str] = Field(default=None, pattern=r"^(high_vs_low|adjacent|custom)$")
    consolation_custom_matchups: Optional[List[dict]] = None
    # ── Iter 104: Emergency Roster Changes + Goalie Scoring (moved from
    # the legacy "Roster Lock Rules" mock UI in League Setup → League Structure).
    emergency_changes_enabled: Optional[bool] = None
    emergency_changes_regular: Optional[int] = Field(default=None, ge=0, le=10)
    emergency_changes_playoffs: Optional[int] = Field(default=None, ge=0, le=10)
    emergency_eligibility: Optional[List[str]] = None  # any | scratched | injured | minors | suspended | personal
    # Iter 106: budget scope — does the count reset per matchup week, or last
    # the entire season? Default = per_week (matches iter-104 server-side logic).
    emergency_changes_scope: Optional[str] = Field(default=None, pattern=r"^(per_week|per_season)$")
    differentiate_goalie_scoring: Optional[bool] = None
    goalie_scoring_method: Optional[str] = Field(default=None, pattern=r"^(cumulative|average_multiplied|best_x|daily_lock)$")
    goalie_best_x_count: Optional[int] = Field(default=None, ge=1, le=8)
    goalie_avg_multiplier_count: Optional[int] = Field(default=None, ge=1, le=8)
    goalie_gp_limit_enabled: Optional[bool] = None
    goalie_gp_limit: Optional[int] = Field(default=None, ge=1, le=10)
    goalie_gp_count_method: Optional[str] = Field(default=None, pattern=r"^(best|average)$")


_LEAGUE_UPDATE_ALLOWED = {
    "is_private", "name", "roster_spots", "bench_spots", "minors_spots",
    "scoring_format", "max_teams", "keepers_allowed", "entry_fee",
    "trade_review_period_hours", "trade_veto_threshold_pct", "trade_deadline_week",
    "trade_deadline_at",
    "waiver_faab_budget", "waiver_period_days",
    "playoff_teams", "playoff_start_week", "playoff_rounds", "playoff_end_week",
    "regular_season_weeks",
    "salary_retention_enabled", "salary_retention_max_pct", "salary_retention_slots",
    "season_start_date", "season_end_date",
    "matchup_length_days", "opponents_per_matchup_period",
    "consolation_enabled", "consolation_start_week", "consolation_end_week",
    "consolation_uses_playoff_schedule",
    # Iter 81: extended roster controls
    "ir_slots", "ir_plus_slots", "taxi_squad_size", "position_limits",
    "position_breakdown",
    "enforce_position_maxes", "min_active_players", "min_games_played",
    "prorate_min_max_by_period", "allow_illegal_rosters", "ir_eligibility_modes",
    # Iter 100: roster lock + lineup lock + NHL stats window
    "roster_lock_type", "roster_lock_day", "roster_lock_second_day",
    "lineup_lock_minutes_before",
    "playoff_roster_lock_override", "playoff_roster_lock_type",
    "playoff_roster_lock_day", "playoff_roster_lock_second_day",
    "playoff_lineup_lock_minutes_before",
    "stats_count_start_date", "stats_count_end_date",
    # Iter 101: playoff bracket + consolation bracket configuration
    "playoff_format", "playoff_seeding_method", "playoff_custom_matchups",
    "consolation_teams", "consolation_seeding_method", "consolation_custom_matchups",
    # Iter 194b / 196: in-draft pick trade review + per-week playoff lengths
    "draft_trade_review_minutes", "draft_trade_post_delay_action",
    "playoff_week_lengths",
    # Iter 104: Emergency Roster Changes + Goalie Scoring (moved from League Setup mock UI)
    "emergency_changes_enabled", "emergency_changes_regular",
    "emergency_changes_playoffs", "emergency_eligibility",
    "emergency_changes_scope",
    "differentiate_goalie_scoring", "goalie_scoring_method",
    "goalie_best_x_count", "goalie_avg_multiplier_count",
    "goalie_gp_limit_enabled", "goalie_gp_limit", "goalie_gp_count_method",
    # Iter 226 — Format editable from wizard Basics step; per-week overrides
    # for irregular matchup lengths (late starts, breaks, all-star, etc).
    "format", "week_overrides",
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

    # ── Iter 176: derive `roster_spots` from `position_breakdown.active`
    # whenever the commissioner has set per-position caps for the
    # Active Roster section AND did NOT explicitly include
    # `roster_spots` in the same payload. (Iter 176/179: Manual input wins
    # — without this guard the commissioner's typed value
    # e.g. 19 with caps summing to 20 was silently overwritten by the
    # derived sum, which is the root cause of "the Position Breakdown
    # menu is not changing the sizes of rosters" bug.)
    if ("position_breakdown" in body) and ("roster_spots" not in body):
        breakdown = (
            update.get("position_breakdown")
            or body.get("position_breakdown")
            or {}
        )
        active = (breakdown or {}).get("active") or {}
        # Sum only the cells the commissioner actually set; blank cells
        # (missing keys) mean "no cap" and should NOT contribute to the
        # derived total. An empty `active` dict means "untouched".
        if active:
            try:
                active_sum = sum(int(v) for v in active.values()
                                 if v is not None and v != "")
            except (TypeError, ValueError):
                active_sum = 0
            if active_sum > 0 and active_sum != league.get("roster_spots"):
                old_rs = league.get("roster_spots")
                update["roster_spots"] = active_sum
                diff["roster_spots"] = {"from": old_rs, "to": active_sum, "derived": True}

    # ── Iter 181: per-row caps cannot exceed the section's overall size.
    # If the active row sums to 21 but roster_spots is 19, reject the
    # save with a clear "increase Roster Size first" message — silently
    # overriding either side would surprise the commissioner. We
    # validate using the EFFECTIVE values (post-update) so a commissioner
    # who's resizing rosters and per-position caps in the same save
    # against consistent numbers is not punished by the old DB state.
    effective_breakdown = (
        update.get("position_breakdown")
        if "position_breakdown" in update
        else league.get("position_breakdown")
    )
    if effective_breakdown is not None:
        effective_roster_spots = (
            update.get("roster_spots")
            if "roster_spots" in update
            else league.get("roster_spots")
        )
        effective_bench_spots = (
            update.get("bench_spots")
            if "bench_spots" in update
            else league.get("bench_spots")
        )
        effective_minors_spots = (
            update.get("minors_spots")
            if "minors_spots" in update
            else league.get("minors_spots")
        )
        cap_err = check_position_breakdown_within_caps(
            position_breakdown=effective_breakdown,
            roster_spots=effective_roster_spots,
            bench_spots=effective_bench_spots,
            minors_spots=effective_minors_spots,
        )
        if cap_err:
            raise HTTPException(status_code=400, detail=cap_err)

    # ── Iter 100: cross-field validation for playoffs vs regular season ──
    # Only enforce when the request actually touches one of the relevant
    # fields (don't punish legacy leagues with pre-existing inconsistent data
    # when the commissioner is updating an unrelated setting).
    _validated_fields = {
        "regular_season_weeks",
        "playoff_start_week",
        "playoff_end_week",
        "playoff_rounds",
        "playoff_teams",
        "consolation_teams",
    }
    if _validated_fields & update.keys():
        def _eff(k, default=None):
            if k in update:
                return update[k]
            return league.get(k, default)

        reg_weeks = _eff("regular_season_weeks")
        ps_week = _eff("playoff_start_week")
        pe_week = _eff("playoff_end_week")
        p_rounds = _eff("playoff_rounds")
        p_teams = _eff("playoff_teams")
        if reg_weeks is not None and ps_week is not None and int(ps_week) <= int(reg_weeks):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Playoffs must start AFTER the regular season ends. "
                    f"Regular season ends week {reg_weeks}; playoffs start week {ps_week}."
                ),
            )
        if ps_week is not None and pe_week is not None and int(pe_week) < int(ps_week):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Playoff end week ({pe_week}) cannot be before playoff start week ({ps_week})."
                ),
            )
        if (
            ps_week is not None and pe_week is not None and p_rounds is not None
            and (int(pe_week) - int(ps_week) + 1) < int(p_rounds)
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot award a champion: {p_rounds} rounds need at least "
                    f"{p_rounds} week{'s' if int(p_rounds) != 1 else ''}, "
                    f"but only {int(pe_week) - int(ps_week) + 1} week"
                    f"{'s' if (int(pe_week) - int(ps_week) + 1) != 1 else ''} configured. "
                    "Extend the playoff window or reduce the round count."
                ),
            )
        if p_teams is not None and p_rounds is not None:
            min_teams = 2 ** int(p_rounds)
            if int(p_teams) < min_teams:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"With {p_rounds} round{'s' if int(p_rounds) != 1 else ''}, "
                        f"need at least {min_teams} playoff teams to award a champion. "
                        f"Currently {p_teams}."
                    ),
                )
        # Consolation teams cannot exceed teams NOT in playoffs
        c_teams = _eff("consolation_teams")
        league_team_count = int(league.get("current_teams") or league.get("max_teams") or 0)
        if (
            c_teams is not None
            and p_teams is not None
            and league_team_count > 0
            and int(c_teams) > (league_team_count - int(p_teams))
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Consolation bracket can have at most "
                    f"{league_team_count - int(p_teams)} team"
                    f"{'s' if (league_team_count - int(p_teams)) != 1 else ''} "
                    f"(teams not in the playoffs). Currently {c_teams}."
                ),
            )

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



# ─── PUT /leagues/{league_id}/salary-retention-slots ───────────
# Moved out of `server.py` (iter 82) so all `/leagues/...` mutators live in a
# single router. Same URL, body shape, and response — pure refactor.
@router.put("/leagues/{league_id}/salary-retention-slots")
async def set_salary_retention_slots(league_id: str, payload: dict, request: Request):
    """Commissioner-only setter for the per-team salary retention slot cap.

    Body: ``{"salary_retention_slots": int}``  (0–10)
    Default value is 3 (mirrors the NHL CBA). `0` disables retention trades
    entirely; higher values let teams stack more retained contracts.

    Audited via `db.audit_log` with `{from, to}` diff so co-commissioners can
    see who changed it and when.
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

    try:
        new_val = int(payload.get("salary_retention_slots", 3))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="salary_retention_slots must be an integer",
        )
    if new_val < 0 or new_val > 10:
        raise HTTPException(
            status_code=400,
            detail="salary_retention_slots must be between 0 and 10",
        )

    old_val = int(league.get("salary_retention_slots", 3))
    if new_val != old_val:
        await db.leagues.update_one(
            {"_id": league["_id"]},
            {"$set": {"salary_retention_slots": new_val}},
        )
        await db.audit_log.insert_one({
            "league_id": league_id,
            "actor_id": user["_id"],
            "actor_name": user.get("name", user.get("email", "Unknown")),
            "action": "salary_retention_slots_updated",
            "role": "commissioner" if is_comm else "co_commissioner",
            "diff": {"salary_retention_slots": {"from": old_val, "to": new_val}},
            "created_at": datetime.now(timezone.utc),
        })

    return {
        "league_id": league_id,
        "salary_retention_slots": new_val,
        "previous": old_val,
        "changed": new_val != old_val,
    }


# ─── Roster Limits (Iter 170c) ────────────────────────────────────────
# Commissioner-editable per-section roster caps. Persists on
# `league.roster_limits` so the Roster Monitor (routes/monitors.py)
# and frontend Settings panel all read from one source of truth.

ROSTER_LIMIT_FIELDS = ("starting_skaters", "starting_goalies", "bench", "ir", "minors")
DEFAULT_ROSTER_LIMITS_LEAGUES = {
    "starting_skaters": 18,
    "starting_goalies": 2,
    "bench": 6,
    "ir": 3,
    "minors": 6,
}


@router.get("/leagues/{league_id}/roster-limits")
async def get_roster_limits(league_id: str):
    """Return the league's roster section limits (defaults applied if unset)."""
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    persisted = league.get("roster_limits") or {}
    return {
        "league_id": league_id,
        "roster_limits": {**DEFAULT_ROSTER_LIMITS_LEAGUES, **persisted},
        "defaults": DEFAULT_ROSTER_LIMITS_LEAGUES,
    }


@router.put("/leagues/{league_id}/roster-limits")
async def update_roster_limits(league_id: str, payload: dict, request: Request):
    """Commissioner-only setter for roster section limits.

    Body: ``{"starting_skaters": int, "starting_goalies": int, "bench": int,
             "ir": int, "minors": int}``. Any subset can be sent; omitted
    fields retain their prior value. Each field must be ≥ 0 and ≤ 50 (a
    reasonable upper bound that catches obvious mis-entries).
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
        raise HTTPException(status_code=403, detail="Only commissioners can update roster limits")

    existing = {**DEFAULT_ROSTER_LIMITS_LEAGUES, **(league.get("roster_limits") or {})}
    new_limits = dict(existing)
    diff: dict = {}
    for key in ROSTER_LIMIT_FIELDS:
        if key not in payload:
            continue
        try:
            val = int(payload[key])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} must be an integer")
        if val < 0 or val > 50:
            raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 50")
        if val != existing[key]:
            diff[key] = {"from": existing[key], "to": val}
            new_limits[key] = val

    if diff:
        await db.leagues.update_one(
            {"_id": league["_id"]},
            {"$set": {"roster_limits": new_limits}},
        )
        await db.audit_log.insert_one({
            "league_id": league_id,
            "actor_id": user["_id"],
            "actor_name": user.get("name", user.get("email", "Unknown")),
            "action": "roster_limits_updated",
            "role": "commissioner" if is_comm else "co_commissioner",
            "diff": diff,
            "created_at": datetime.now(timezone.utc),
        })

    return {
        "league_id": league_id,
        "roster_limits": new_limits,
        "changed": bool(diff),
        "diff": diff,
    }



# ─── GET /leagues/{league_id}/veto-threshold-preview ───────────
@router.get("/leagues/{league_id}/veto-threshold-preview")
async def veto_threshold_preview(
    league_id: str,
    request: Request,
    pct: Optional[int] = None,
):
    """Return the auto-veto math for a league's current (or proposed) veto %.

    Used by the Setup Wizard and Rules & Schedule admin tab to show the
    commissioner not just the **%** but the absolute **number of teams**
    required to trigger a veto. Example: 50% of a 12-team league = **6 teams
    must veto**. Uses `math.ceil` so partial votes round up (strict majority).

    Query params:
      * `pct` — optional override; if provided, computes preview against this
        value instead of the saved one. Useful while sliding the threshold
        input in the UI before saving.
    """
    import math
    db = _deps["db"]
    await _deps["get_current_user"](request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    total_teams = int(league.get("current_teams") or 0)
    effective_pct = pct if pct is not None else league.get("trade_veto_threshold_pct")
    if effective_pct is None:
        effective_pct = 50
    effective_pct = max(0, min(100, int(effective_pct)))
    enabled = effective_pct > 0 and total_teams > 0
    teams_required = (
        max(1, math.ceil(total_teams * effective_pct / 100)) if enabled else 0
    )
    return {
        "league_id": league_id,
        "pct": effective_pct,
        "total_teams": total_teams,
        "teams_required": teams_required,
        "enabled": enabled,
        "description": (
            f"{effective_pct}% of {total_teams} teams = {teams_required} team"
            f"{'s' if teams_required != 1 else ''} required to veto a trade."
            if enabled else
            "Vetoes are disabled — trades cannot be blocked by league vote."
        ),
    }


# ─── GET /leagues/nhl-season-bounds ─────────────────────────────
# Returns NHL 2025-26 regular-season + playoff calendar week list for the
# commissioner-facing "League stats start/end counting on" dropdowns.
# Hardcoded for the current season (per user choice B) — backend-sourced
# so a future iteration can swap to a live source without UI changes.
_NHL_SEASON_2025_26 = {
    "regular_season_start": "2025-10-07",
    "regular_season_end": "2026-04-16",
    "playoffs_start": "2026-04-18",
    "playoffs_end": "2026-06-25",
}


def _build_nhl_weeks(start_iso: str, end_iso: str) -> list:
    """Generate 7-day NHL fantasy weeks (Mon→Sun) spanning [start, end]."""
    from datetime import date
    s = date.fromisoformat(start_iso)
    e = date.fromisoformat(end_iso)
    # Snap start back to Monday so weeks line up consistently.
    s = s - timedelta(days=s.weekday())
    weeks = []
    cur = s
    week_no = 1
    while cur <= e:
        wk_end = cur + timedelta(days=6)
        weeks.append({
            "number": week_no,
            "start_date": cur.isoformat(),
            "end_date": wk_end.isoformat(),
            "label": f"Week {week_no} ({cur.strftime('%b %-d')} – {wk_end.strftime('%b %-d')})",
        })
        cur = wk_end + timedelta(days=1)
        week_no += 1
    return weeks


@router.get("/nhl-season-bounds")
async def nhl_season_bounds():
    """NHL calendar reference used to populate stats-start/stats-end + playoff
    week dropdowns in the commissioner UI. Static for the 2025-26 season.
    """
    weeks = _build_nhl_weeks(
        _NHL_SEASON_2025_26["regular_season_start"],
        _NHL_SEASON_2025_26["playoffs_end"],
    )
    return {
        "season": "2025-26",
        **_NHL_SEASON_2025_26,
        "weeks": weeks,
        "total_weeks": len(weeks),
    }



# ─── GET /teams/{team_id}/emergency-swap-budget ─────────────────
# Returns the team's emergency-swap budget + used count for the current period
# so the lineup page can render a "Used X / Y" chip on the header.
@router.get("/teams/{team_id}/emergency-swap-budget")
async def team_emergency_swap_budget(team_id: str, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await db.leagues.find_one({"_id": _safe_object_id(team["league_id"], "league_id")})
    if not league or not league.get("emergency_changes_enabled"):
        return {
            "enabled": False, "scope": None, "budget": 0,
            "used": 0, "remaining": 0, "scope_label": None,
        }

    current_wk = league.get("current_week") or league.get("playoff_start_week")
    in_playoffs = (
        current_wk is not None
        and league.get("playoff_start_week") is not None
        and int(current_wk) >= int(league["playoff_start_week"])
    )
    budget = int(
        (league.get("emergency_changes_playoffs") or 0) if in_playoffs
        else (league.get("emergency_changes_regular") or 0)
    )
    scope = league.get("emergency_changes_scope") or "per_week"
    used_field = (
        f"emergency_swaps_used_{current_wk}"
        if scope == "per_week" and current_wk
        else "emergency_swaps_used_season"
    )
    used = int(team.get(used_field) or 0)
    return {
        "enabled": True,
        "scope": scope,
        "budget": budget,
        "used": used,
        "remaining": max(0, budget - used),
        "scope_label": "this week" if scope == "per_week" else "this season",
        "in_playoffs": in_playoffs,
        "current_week": current_wk,
    }


# ─── PUT /teams/{team_id}/goalie-daily-lock ─────────────────────
# Persists the per-day goalie lock map for the team. Body shape:
#   { "lock_map": {"2026-04-08": "<player_id>", "2026-04-10": "<player_id>"} }
# When `goalie_scoring_method=daily_lock`, the live-scoring worker only
# attributes goalie game points on dates present in this map.
@router.put("/teams/{team_id}/goalie-daily-lock")
async def update_team_goalie_daily_lock(team_id: str, payload: dict, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await db.leagues.find_one({"_id": _safe_object_id(team["league_id"], "league_id")})
    is_owner = team.get("owner_id") == user["_id"]
    is_commish = league and (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or (user.get("role") == "admin")
    )
    if not (is_owner or is_commish):
        raise HTTPException(status_code=403, detail="Only the team owner or commissioner may set goalie locks")
    lock_map = payload.get("lock_map") or {}
    if not isinstance(lock_map, dict):
        raise HTTPException(status_code=400, detail="lock_map must be a {date_iso: player_id} object")
    # Sanitize: keep ISO dates with a player_id string value.
    sanitized = {}
    for date_iso, player_id in lock_map.items():
        if not isinstance(date_iso, str) or len(date_iso) != 10 or date_iso.count("-") != 2:
            continue
        if player_id is None or player_id == "":
            continue
        sanitized[date_iso] = str(player_id)
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {"goalie_daily_lock": sanitized}},
    )
    return {"team_id": team_id, "lock_map": sanitized, "count": len(sanitized)}


# ─── GET /leagues/{league_id}/lock-status ──────────────────────
# Returns the live `evaluate_lineup_lock` result so the lineup UI can show a
# warning banner BEFORE the save fails. Read-only; any authenticated user
# in the league can call it. Honors `?week=N` to preview lock state for a
# specific scoring period (defaults to the league's current_week).
@router.get("/leagues/{league_id}/lock-status")
async def league_lock_status(league_id: str, request: Request, week: Optional[int] = None):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    try:
        from utils.lineup_lock import evaluate_lineup_lock
        current_wk = week if week is not None else (
            league.get("current_week") or league.get("playoff_start_week")
        )
        result = evaluate_lineup_lock(league, current_week=current_wk)
        return {
            **result,
            "league_id": league_id,
            "evaluated_for_week": current_wk,
        }
    except Exception as e:
        return {"locked": False, "reason": None, "error": str(e)}


# ─── POST /leagues/{league_id}/playoffs/check-tbd-deadlines ────
# Scans the league's playoff_custom_matchups + consolation_custom_matchups
# for any TBD slots whose matchup-period (week) is within 2 days of starting,
# and posts a top-bell notification + activity feed entry for every
# commissioner / co-commissioner. Safe to call repeatedly — idempotent within
# a 24h window per (league, week) via the `tbd_deadline_pings` collection.
#
# Returns the count of notifications fired. Intended to be hit by a daily
# cron or whenever the admin lands on `/commissioner/settings`.
@router.post("/leagues/{league_id}/playoffs/check-tbd-deadlines")
async def check_playoff_tbd_deadlines(league_id: str, request: Request):
    from datetime import date
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    create_notification = _deps.get("create_notification")

    await get_current_user(request)  # any logged-in user can trigger; safe no-op
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    matchup_len = int(league.get("matchup_length_days") or 7)
    season_start_str = league.get("season_start_date")
    if not season_start_str:
        return {"fired": 0, "reason": "season_start_date not configured"}
    try:
        season_start = date.fromisoformat(season_start_str)
    except Exception:
        return {"fired": 0, "reason": "invalid season_start_date"}

    today = date.today()
    fired = 0
    recipients = [league["commissioner_id"]] + list(league.get("co_commissioners") or [])
    recipients = list(dict.fromkeys(recipients))  # de-dupe preserving order

    for bracket_key, label in (
        ("playoff_custom_matchups", "Playoff"),
        ("consolation_custom_matchups", "Consolation"),
    ):
        for entry in (league.get(bracket_key) or []):
            try:
                week = int(entry.get("week", 0))
            except Exception:
                continue
            if week <= 0:
                continue
            # Has any TBD slot in any matchup for this week?
            has_tbd = any(
                (m.get("home") in (None, "tbd", "tbd_loser", ""))
                or (m.get("away") in (None, "tbd", "tbd_loser", ""))
                for m in (entry.get("matchups") or [])
            )
            if not has_tbd:
                continue

            week_start = season_start + timedelta(days=(week - 1) * matchup_len)
            days_until = (week_start - today).days
            # Within last 2 days of the prior matchup period (i.e. 0..2 days before start)
            if not (0 <= days_until <= 2):
                continue

            # Idempotency: have we already pinged this (league, bracket, week) in the past 22h?
            recent = await db.tbd_deadline_pings.find_one({
                "league_id": league_id,
                "bracket": bracket_key,
                "week": week,
                "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=22)},
            })
            if recent:
                continue

            if create_notification:
                for uid in recipients:
                    await create_notification(
                        uid,
                        "playoff_tbd_deadline",
                        f"{label} bracket needs matchup setup",
                        (
                            f"Week {week} starts in {days_until} day"
                            f"{'s' if days_until != 1 else ''} and has TBD slots. "
                            "Configure the matchup ladder in Commissioner → League Structure."
                        ),
                        league_id,
                        f"/commissioner/settings?tab=divisions&focus={bracket_key}-week-{week}",
                    )
                    fired += 1

            await db.tbd_deadline_pings.insert_one({
                "league_id": league_id,
                "bracket": bracket_key,
                "week": week,
                "created_at": datetime.now(timezone.utc),
            })

    return {"fired": fired, "league_id": league_id}


# ─── Iter 228i — Propagate roster shape to all team rosters ────────


@router.post("/leagues/{league_id}/propagate-roster-shape")
async def propagate_roster_shape(league_id: str, request: Request):
    """When the commissioner saves Roster Size / Position Breakdown, this
    endpoint applies the new shape to every team's structure. Active
    rosters are trimmed (excess players moved to bench/minors/free agents)
    and slot caps updated so downstream lineup validation works
    immediately."""
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    db = _deps["db"]
    try:
        oid = ObjectId(league_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league_id")
    league = await db.leagues.find_one({"_id": oid})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    roster_spots = int(league.get("roster_spots") or 20)
    bench_spots = int(league.get("bench_spots") or 0)
    minors_spots = int(league.get("minors_spots") or 0)
    cap = roster_spots + bench_spots + minors_spots

    teams = await db.teams.find({"league_id": league_id}).to_list(500)
    updated_count = 0
    trimmed_count = 0
    for t in teams:
        roster = t.get("roster") or []
        excess = roster[cap:] if len(roster) > cap else []
        new_roster = roster[:cap]
        await db.teams.update_one(
            {"_id": t["_id"]},
            {"$set": {
                "roster": new_roster,
                "roster_max": cap,
                "active_max": roster_spots,
                "bench_max": bench_spots,
                "minors_max": minors_spots,
                "roster_shape_applied_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        updated_count += 1
        if excess:
            trimmed_count += 1
    return {
        "league_id": league_id,
        "teams_updated": updated_count,
        "teams_trimmed": trimmed_count,
        "cap": cap,
        "shape": {
            "roster_spots": roster_spots,
            "bench_spots": bench_spots,
            "minors_spots": minors_spots,
        },
    }

"""Matchups: schedule generation, get-current-week, simulate-week (with auto-crown)."""
import itertools
import random as _random
from datetime import datetime, timezone, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes import awards as awards_module
from routes import scheduler as scheduler_routes
from services.schedule_store import season_query, season as schedule_season
from routes.league_guards import require_league_member, verify_team_in_league

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)
    scheduler_routes.setup(deps)


# ─── Pydantic ─────────────────────────────────────────────────
class GenerateScheduleRequest(BaseModel):
    league_id: str
    # Defaults to the league's configured `regular_season_weeks` when omitted,
    # falling back to 18 only if the league has no configured value. This keeps
    # league administration the single source of truth for schedule length.
    num_weeks: Optional[int] = Field(default=None, ge=1, le=52)


class SimulateWeekRequest(BaseModel):
    league_id: str
    week: int


# ─── Helpers ─────────────────────────────────────────────────

# Iter 225 — NHL regular season window for the 2025-2026 season (used for
# the schedule-fit sanity check that surfaces in /matchups/generate-schedule
# and /matchups/preview). Update annually when the NHL schedule changes.
NHL_REGULAR_SEASON_START = (10, 7)   # Oct 7
NHL_REGULAR_SEASON_END = (4, 18)     # Apr 18 (typical end-of-RS Saturday)


def _season_schedule_warnings(
    *,
    season_start: Optional[str],
    season_end: Optional[str],
    matchup_length_days: int,
    num_weeks: int,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the configured schedule vs the calendar.

    • Errors block generation when the configured season window cannot fit
      the requested number of weeks given the matchup length.
    • Warnings are informational: schedule extends past the typical NHL
      regular-season window (so points won't accumulate after the real
      season ends).
    """
    errors: list[str] = []
    warnings: list[str] = []

    def parse(d):
        if not d:
            return None
        try:
            return datetime.fromisoformat(str(d).split("T", 1)[0])
        except Exception:
            return None

    start = parse(season_start)
    end = parse(season_end)
    if start and end:
        if end < start:
            errors.append("Season end date is before the season start date.")
        else:
            days_available = (end - start).days + 1
            days_required = max(1, matchup_length_days) * max(1, num_weeks)
            if days_required > days_available:
                errors.append(
                    f"Season window has {days_available} days but the schedule needs "
                    f"{days_required} days ({num_weeks} weeks × {matchup_length_days}d). "
                    "Lengthen the season or shorten the matchup period."
                )

    if start:
        nhl_start = datetime(start.year, *NHL_REGULAR_SEASON_START)
        if start < nhl_start - timedelta(days=14):
            warnings.append(
                f"Season starts {start.date()} — that's well before the NHL regular season "
                f"({nhl_start.date()}). Player stats won't accumulate until games begin."
            )
    if end:
        nhl_end_yr = end.year if end.month >= 7 else end.year
        nhl_end = datetime(nhl_end_yr, *NHL_REGULAR_SEASON_END)
        if end > nhl_end + timedelta(days=14):
            warnings.append(
                f"Season ends {end.date()} — that's past the NHL regular season "
                f"({nhl_end.date()}). Points won't accumulate after the NHL season ends."
            )
    return errors, warnings


def generate_round_robin(team_ids):
    """Generate a full round-robin schedule. Returns list of rounds, each a list of (home, away) tuples."""
    teams = list(team_ids)
    if len(teams) % 2 == 1:
        teams.append(None)
    n = len(teams)
    schedule = []
    for _ in range(n - 1):
        round_matchups = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            if home is not None and away is not None:
                round_matchups.append((home, away))
        schedule.append(round_matchups)
        teams.insert(1, teams.pop())
    return schedule


def _seed_pairings(seeded_teams: list, method: str) -> list:
    """Given an ordered list of team_ids (seed 1 first), return a list of
    (home, away) Round-1 matchup tuples per the seeding method.

    `high_vs_low`  → 1vN, 2vN-1, 3vN-2, …
    `adjacent`     → 1v2, 3v4, …
    """
    teams = list(seeded_teams)
    pairs: list = []
    if method == "adjacent":
        for i in range(0, len(teams) - 1, 2):
            pairs.append((teams[i], teams[i + 1]))
    else:  # high_vs_low (default)
        i, j = 0, len(teams) - 1
        while i < j:
            pairs.append((teams[i], teams[j]))
            i += 1
            j -= 1
    return pairs


def _build_playoff_bracket(
    league: dict,
    teams: list,
    *,
    is_consolation: bool = False,
) -> list:
    """Build playoff (or consolation) matchups across the configured weeks.

    Returns a list of {week, home_team_id, away_team_id, is_playoff, is_consolation,
    bracket_round, status} dicts ready to insert into db.matchups.

    Honors:
      • playoff_format ∈ {h2h_matchup, playoff_tree}  (h2h_matchup → no bracket)
      • playoff_seeding_method ∈ {high_vs_low, adjacent, custom}
      • playoff_custom_matchups → list of {week, matchups: [{home, away}]}
    """
    if league.get("playoffs_enabled") is False:
        return []
    prefix = "consolation_" if is_consolation else "playoff_"
    fmt = "playoff_tree" if is_consolation else (league.get("playoff_format") or "h2h_matchup")
    if not is_consolation and fmt != "playoff_tree":
        return []  # legacy "all regular H2H during playoff weeks" mode

    method = league.get(f"{prefix}seeding_method") or "high_vs_low"
    start_wk = league.get(f"{prefix}start_week") or league.get("playoff_start_week")
    end_wk = league.get(f"{prefix}end_week") or league.get("playoff_end_week")
    if start_wk is None or end_wk is None:
        return []
    start_wk, end_wk = int(start_wk), int(end_wk)
    if end_wk < start_wk:
        return []

    # ── Custom: trust the commissioner's ladder ──
    if method == "custom":
        out = []
        custom = league.get(f"{prefix}custom_matchups") or []
        for entry in custom:
            try:
                wk = int(entry.get("week", 0))
            except Exception:
                continue
            if wk < start_wk or wk > end_wk:
                continue
            for m in (entry.get("matchups") or []):
                home = m.get("home")
                away = m.get("away")
                # Note: We intentionally KEEP rows where both slots are TBD
                # (winner or loser sentinels) so the bracket UI can render
                # the placeholder ladder. Pure-empty rows are still filtered.
                if home in (None, "") and away in (None, ""):
                    continue
                home_tbd_type = (
                    "loser" if home == "tbd_loser"
                    else "winner" if home in (None, "", "tbd")
                    else None
                )
                away_tbd_type = (
                    "loser" if away == "tbd_loser"
                    else "winner" if away in (None, "", "tbd")
                    else None
                )
                out.append({
                    "week": wk,
                    "home_team_id": home if home not in (None, "", "tbd", "tbd_loser") else None,
                    "away_team_id": away if away not in (None, "", "tbd", "tbd_loser") else None,
                    "home_team_tbd": home_tbd_type is not None,
                    "away_team_tbd": away_tbd_type is not None,
                    "home_tbd_type": home_tbd_type,  # "winner" | "loser" | None
                    "away_tbd_type": away_tbd_type,
                    "bracket_round": wk - start_wk + 1,
                    "is_playoff": not is_consolation,
                    "is_consolation": is_consolation,
                })
        return out

    # ── Seeded (high_vs_low or adjacent) ──
    # Rank teams by wins desc, then PF desc (matches `_rank_teams` in leagues router).
    field_count = league.get(f"{prefix}teams")
    if field_count is None:
        field_count = len(teams)
    field_count = int(field_count)

    # Use the same ranking as `routes/leagues._rank_teams` so the bracket
    # display endpoint computes identical seeds.
    ranked = sorted(
        teams,
        key=lambda t: (
            -(int(t.get("wins", 0) or 0)),
            -(float(t.get("points_for", 0) or 0) + float(t.get("live_points", 0) or 0)),
            str(t.get("_id") or ""),
        ),
    )
    if is_consolation:
        # Consolation seeds = teams ranked BELOW the playoff cut
        playoff_count = int(league.get("playoff_teams") or 0)
        seeded = ranked[playoff_count: playoff_count + field_count]
    else:
        seeded = ranked[:field_count]

    seed_ids = [str(t["_id"]) for t in seeded]
    round_pairs = _seed_pairings(seed_ids, method)

    out: list = []
    # Round 1 — start week, real matchups
    for home, away in round_pairs:
        out.append({
            "week": start_wk,
            "home_team_id": home,
            "away_team_id": away,
            "home_team_tbd": False,
            "away_team_tbd": False,
            "bracket_round": 1,
            "is_playoff": not is_consolation,
            "is_consolation": is_consolation,
        })
    # Rounds 2..N — TBD placeholders for future winners
    surviving = len(round_pairs)  # = number of round-1 winners
    for rnd_offset in range(1, end_wk - start_wk + 1):
        num_matchups = max(1, surviving // 2)
        is_final_round = num_matchups == 1 and surviving <= 2
        for _ in range(num_matchups):
            doc = {
                "week": start_wk + rnd_offset,
                "home_team_id": None,
                "away_team_id": None,
                "home_team_tbd": True,
                "away_team_tbd": True,
                "bracket_round": rnd_offset + 1,
                "is_playoff": not is_consolation,
                "is_consolation": is_consolation,
            }
            if is_final_round:
                doc["is_final"] = True
                doc["bracket"] = "consolation" if is_consolation else "championship"
            out.append(doc)
        surviving = num_matchups  # winners of this round feed into next
        if surviving <= 1:
            break
    return out


def _build_division_pairings(teams: list, cfg: dict) -> list:
    """Build a flat list of (home, away) pairings per the division-aware schedule config.

    For each unordered pair (A,B), choose a "times to play" based on:
      - same division → cfg.intra_division_games
      - same conference (diff division) → cfg.intra_conference_games
      - different conference → cfg.inter_conference_games
    Home/away alternates when a pair plays multiple times.
    Returns [(home_id, away_id), ...] — not yet distributed into weeks.
    """
    pairings = []
    n = len(teams)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = teams[i], teams[j]
            same_div = a.get("division") and a.get("division") == b.get("division")
            same_conf = a.get("conference") and a.get("conference") == b.get("conference")
            if same_div:
                games = int(cfg.get("intra_division_games") or 0)
            elif same_conf:
                games = int(cfg.get("intra_conference_games") or 0)
            else:
                games = int(cfg.get("inter_conference_games") or 0)
            for g in range(games):
                if g % 2 == 0:
                    pairings.append((str(a["_id"]), str(b["_id"])))
                else:
                    pairings.append((str(b["_id"]), str(a["_id"])))
    return pairings


# ─── Endpoints ───────────────────────────────────────────────
@router.post("/matchups/generate-schedule")
async def generate_schedule(input: GenerateScheduleRequest, request: Request):
    """Legacy entry point uses the same validated, transaction-safe combined engine."""
    from services.combined_scheduler import defaults
    from services.schedule_store import apply_preview
    user = await _deps["get_current_user"](request)
    from routes.league_guards import require_league_member
    league = await require_league_member(_deps["db"], user, input.league_id)
    if league.get("scoring_format") == "rotisserie":
        from services.roto_schedule import generate
        return await generate(_deps["db"], input.league_id, user, input.num_weeks)
    user, ctx = await scheduler_routes.authorized(request, input.league_id)
    settings = defaults(ctx["league"], ctx["teams"])
    if input.num_weeks is not None:
        settings = settings.model_copy(update={"weeks": input.num_weeks})
    result = await scheduler_routes.make_preview(_deps["db"], input.league_id, user, ctx, settings)
    if result["status"] != "feasible":
        raise HTTPException(400 if result["status"] == "infeasible" else 503, detail=" ".join(result["errors"]))
    applied = await apply_preview(_deps["db"], input.league_id, result["preview_id"], user)
    return {**applied, "message": f"Generated {applied['games']} validated matchups", "weeks": settings.weeks,
            "mode": "combined", "opponents_per_period": settings.games_per_week,
            "placeholder_team_slots": sum(bool(t.get("is_open_slot")) for t in ctx["teams"]),
            "playoff_matchups": await _deps["db"].matchups.count_documents({**season_query(input.league_id, schedule_season(ctx["league"])), "is_playoff": True}),
            "consolation_matchups": await _deps["db"].matchups.count_documents({**season_query(input.league_id, schedule_season(ctx["league"])), "is_consolation": True}),
            "warnings": []}


class PreviewScheduleRequest(BaseModel):
    """Iter 221 — Dry-run preview, NO DB writes. Used by Create-League page so
    commissioners can see the first few weeks of their schedule before finalising.
    Iter 225 — Optionally accepts `season_start`, `season_end`, and
    `matchup_length_days` so we can surface the same calendar+NHL-window
    sanity warnings the wizard's "Generate" step uses.
    """
    max_teams: int = Field(default=10, ge=2, le=32)
    matchups_per_week: int = Field(default=1, ge=1, le=31)
    num_weeks: int = Field(default=4, ge=1, le=18)
    season_start: Optional[str] = None
    season_end: Optional[str] = None
    matchup_length_days: int = Field(default=7, ge=1, le=14)


@router.post("/matchups/preview")
async def preview_schedule(input: PreviewScheduleRequest):
    """Wizard preview uses the same weekly constraint engine without live writes."""
    from services.combined_scheduler import Settings, solve
    from starlette.concurrency import run_in_threadpool
    import asyncio
    teams = [{"_id": f"team_{i + 1}", "name": f"Team {i + 1}"} for i in range(input.max_teams)]
    settings = Settings(weeks=input.num_weeks, games_per_week=input.matchups_per_week)
    try:
        await asyncio.wait_for(scheduler_routes._solvers.acquire(), timeout=1)
    except TimeoutError:
        raise HTTPException(429, "Other schedules are being generated. Try again shortly.")
    try:
        result = await run_in_threadpool(solve, teams, settings, (), 4)
    except ImportError as exc:
        raise HTTPException(503, "The schedule solver is not installed on this server") from exc
    finally:
        scheduler_routes._solvers.release()
    if result["status"] != "feasible":
        raise HTTPException(400 if result["status"] == "infeasible" else 503, result)
    errors, warnings = _season_schedule_warnings(season_start=input.season_start, season_end=input.season_end,
        matchup_length_days=input.matchup_length_days, num_weeks=input.num_weeks)
    if errors: raise HTTPException(400, {"errors": errors})
    return {"weeks": [{"week": w, "matchups": [g for g in result["games"] if g["week"] == w]} for w in range(1, input.num_weeks + 1)],
            "matchups_per_week": input.matchups_per_week, "team_count": input.max_teams,
            "total_matchups": len(result["games"]), "warnings": warnings}


# ── Iter 231ar — Open-slot resolution at read time ─────────────────
# When schedules are generated before all teams are claimed, matchups
# reference synthetic `home_team_id="open_slot_<draft_position>"`.
# Once an owner adopts the seat, the matchup row is still pointing at
# the placeholder — that's what made TFHL's League Home show "Open
# Slot 3 vs Open Slot 22" even though every seat had been adopted.
# This helper rewrites those references using each team's
# `draft_position` so the response always reflects the current roster.

async def _resolve_open_slots(db, league_id: str, matchups: list) -> list:
    """Overlay `home_team_id` / `away_team_id` (+ name) for rows that
    reference `open_slot_<N>` placeholders when a real team has since
    been seeded at that draft_position. Returns a new list — mutation
    of the source docs is fine since they're already pulled out of
    Mongo, but we never `update` the stored doc here; let the caller
    decide if it wants to persist (see the iter 231ar backfill script
    + the optional `persist` flag on `simulate_week`)."""
    has_open = any(
        (m.get("home_team_id") or "").startswith("open_slot_")
        or (m.get("away_team_id") or "").startswith("open_slot_")
        for m in matchups
    )
    if not has_open:
        return matchups

    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    by_pos: dict = {}
    for t in teams:
        pos = t.get("draft_position")
        if pos is not None:
            by_pos[int(pos)] = t

    def _resolve_one(tid: str):
        if not isinstance(tid, str) or not tid.startswith("open_slot_"):
            return None, None
        try:
            pos = int(tid.split("_")[-1])
        except Exception:
            return None, None
        t = by_pos.get(pos)
        if not t or not t.get("name"):
            return None, None
        return str(t["_id"]), t.get("name")

    for m in matchups:
        for side in ("home", "away"):
            new_id, new_name = _resolve_one(m.get(f"{side}_team_id"))
            if new_id:
                m[f"{side}_team_id"] = new_id
                m[f"{side}_team_name"] = new_name
    return matchups


@router.get("/matchups/{league_id}")
async def get_matchups(league_id: str, request: Request, week: Optional[int] = None):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    league = await require_league_member(db, user, league_id)
    query = season_query(league_id, schedule_season(league))
    if week:
        query["week"] = week
    matchups = await db.matchups.find(query).sort("week", 1).to_list(15000)
    matchups = await _resolve_open_slots(db, league_id, matchups)
    from services.h2h_scoring import live_scores
    matchups = await live_scores(db, league, matchups)
    # Scoring snapshots query Mongo by _id; serialize only after those writes.
    for m in matchups:
        m["_id"] = str(m["_id"])
    return matchups


@router.get("/matchups/{league_id}/current-week")
async def get_current_week(league_id: str, request: Request):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    league = await require_league_member(db, user, league_id)
    pipeline = [
        {"$match": {**season_query(league_id, schedule_season(league)), "status": "scheduled"}},
        {"$group": {"_id": None, "min_week": {"$min": "$week"}}},
    ]
    result = await db.matchups.aggregate(pipeline).to_list(1)
    current = result[0]["min_week"] if result else 1
    matchups = await db.matchups.find({**season_query(league_id, schedule_season(league)), "week": current}).to_list(15000)
    matchups = await _resolve_open_slots(db, league_id, matchups)
    from services.h2h_scoring import live_scores
    matchups = await live_scores(db, league, matchups)
    # Scoring snapshots query Mongo by _id; serialize only after those writes.
    for m in matchups:
        m["_id"] = str(m["_id"])
    return {"week": current, "matchups": matchups}


@router.get("/matchups/{league_id}/daily-scoring")
async def get_daily_scoring(league_id: str, team_id: str, week: Optional[int] = None, request: Request = None):
    """Return per-day fantasy point breakdowns for a team within a matchup period.

    Groups each rostered player's `live_stats` entries by game date (derived
    from `updated_at`), computes daily fantasy points, and returns a structure
    suitable for Day Pill Strips, Daily Grids, and Player Card accordions.
    Works for all scoring formats (H2H, Categories, Rotisserie).
    """
    from datetime import date as _date
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    league = await require_league_member(db, user, league_id)
    team = await verify_team_in_league(db, team_id, league_id)

    # Determine the week (default: current week from scheduled matchups)
    if week is None:
        pipeline = [
            {"$match": {"league_id": league_id, "status": {"$in": ["scheduled", "in_progress"]}}},
            {"$group": {"_id": None, "min_week": {"$min": "$week"}}},
        ]
        result = await db.matchups.aggregate(pipeline).to_list(1)
        week = result[0]["min_week"] if result else 1

    # Calculate the date range for this matchup period
    matchup_len = int(league.get("matchup_length_days") or 7)
    season_start_str = league.get("season_start_date")
    if season_start_str:
        try:
            season_start = _date.fromisoformat(str(season_start_str).split("T")[0])
        except Exception:
            season_start = _date(2025, 10, 7)
    else:
        season_start = _date(2025, 10, 7)

    period_start = season_start + timedelta(days=(week - 1) * matchup_len)
    period_end = period_start + timedelta(days=matchup_len - 1)

    # Generate day labels for the period
    days = []
    day_labels = []
    d = period_start
    while d <= period_end:
        days.append(d.isoformat())
        day_labels.append(d.strftime("%a %-m/%-d"))
        d += timedelta(days=1)

    # Fetch roster players with live_stats — ownership-aware
    # Get all players that were ever on this team in the period
    from utils.scoring_roster import get_owner_at, is_lineup_eligible_at
    from live_scoring_worker import _fantasy_points_from_live

    # First try ownership-based roster
    # Ensure period_end is a datetime for MongoDB queries
    _pe_dt = datetime.combine(period_end, datetime.min.time()).replace(tzinfo=timezone.utc) if not isinstance(period_end, datetime) else period_end
    _ps_dt = datetime.combine(period_start, datetime.min.time()).replace(tzinfo=timezone.utc) if not isinstance(period_start, datetime) else period_start
    owned_cursor = db.player_ownership_periods.find({
        "team_id": team_id, "league_id": league_id,
        "acquired_at": {"$lt": _pe_dt + timedelta(days=1)},
        "$or": [{"released_at": None}, {"released_at": {"$gt": _ps_dt}}],
    }, {"player_id": 1, "acquired_at": 1, "released_at": 1})
    ownership_spans = {}
    async for doc in owned_cursor:
        pid = doc["player_id"]
        ownership_spans.setdefault(pid, []).append(
            (doc["acquired_at"], doc.get("released_at"))
        )
    roster_ids = list(ownership_spans.keys())

    if not roster_ids:
        # No ownership data — do NOT fall back to current roster.
        # Check if league has been backfilled to distinguish "no players"
        # from "missing data".
        is_backfilled = bool(league.get("ownership_backfilled_at"))
        if not is_backfilled:
            # Try current roster as a last resort but mark as uncertain
            roster_ids = list(team.get("roster") or [])
    if not roster_ids:
        return {
            "league_id": league_id,
            "team_id": team_id,
            "team_name": team["name"],
            "week": week,
            "scoring_format": league.get("scoring_format", ""),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "days": days,
            "day_labels": day_labels,
            "players": [],
            "daily_totals": {d: 0.0 for d in days},
            "period_total_fpts": 0.0,
        }

    players = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
        {"name": 1, "position": 1, "team": 1, "player_type": 1, "live_stats": 1, "season_stats": 1},
    ).to_list(200)

    # Pre-load lineup eligibility data for all roster players
    from utils.scoring_roster import ACTIVE_SECTIONS
    lineup_by_player = {}
    lineup_cursor = db.lineup_status_periods.find({
        "team_id": team_id,
        "league_id": league_id,
        "player_id": {"$in": roster_ids},
    })
    async for lp in lineup_cursor:
        pid = lp["player_id"]
        lineup_by_player.setdefault(pid, []).append({
            "position": lp.get("position", "bench"),
            "started_at": lp.get("started_at"),
            "ended_at": lp.get("ended_at"),
        })

    from utils.game_allocation import _build_game_date_map, _parse_game_date, calc_game_fpts_from_live
    game_ids = []
    for player in players:
        for gid in (player.get("live_stats") or {}):
            try:
                game_ids.append(int(gid))
            except (TypeError, ValueError):
                continue
    game_starts = await _build_game_date_map(db, game_ids)
    scoring_config = await db.scoring_configs.find_one({"league_id": league_id})

    daily_totals = {d: 0.0 for d in days}
    player_rows = []

    for p in players:
        is_goalie = p.get("player_type") == "goalie" or p.get("position") == "G"
        pid = str(p["_id"])
        daily = {}
        total_fpts = 0.0
        total_goals = 0
        total_assists = 0
        total_shots = 0
        total_saves = 0
        total_ga = 0
        total_wins = 0
        total_games = 0

        for gid, ls in (p.get("live_stats") or {}).items():
            # Allocation follows puck drop, never the time a correction arrived.
            try:
                game_start = game_starts.get(int(gid))
            except (TypeError, ValueError):
                game_start = None
            game_start = game_start or _parse_game_date(ls.get("updated_at"))
            if game_start is None:
                continue
            game_start = game_start.astimezone(timezone.utc)
            game_date = game_start.date().isoformat()

            # Only include games within the matchup period
            if game_date < period_start.isoformat() or game_date > period_end.isoformat():
                continue

            # Per-game ownership check: credit only if owned at game date
            if ownership_spans:
                try:
                    gd_dt = game_start
                    spans = ownership_spans.get(pid, [])
                    owned = False
                    for a, r in spans:
                        a_utc = a.replace(tzinfo=timezone.utc) if a.tzinfo is None else a
                        r_utc = r.replace(tzinfo=timezone.utc) if r and r.tzinfo is None else r
                        if a_utc <= gd_dt and (r_utc is None or r_utc > gd_dt):
                            owned = True
                            break
                    if not owned:
                        continue
                except Exception:
                    pass

            # Per-game lineup eligibility check
            lineup_periods = lineup_by_player.get(pid, [])
            if lineup_periods:
                try:
                    gd_dt = game_start
                    eligible = False
                    for lp in lineup_periods:
                        s = lp["started_at"]
                        e = lp["ended_at"]
                        if s:
                            s = s.replace(tzinfo=timezone.utc) if hasattr(s, 'replace') and s.tzinfo is None else s
                        if e:
                            e = e.replace(tzinfo=timezone.utc) if hasattr(e, 'replace') and e.tzinfo is None else e
                        if s and s <= gd_dt and (e is None or e > gd_dt):
                            eligible = lp.get("position", "bench") in ACTIVE_SECTIONS
                            break
                    if lineup_periods and not eligible:
                        continue
                except Exception:
                    pass

            fpts = calc_game_fpts_from_live(ls, is_goalie, scoring_config)
            goals = ls.get("goals", 0) or 0
            assists = ls.get("assists", 0) or 0
            shots = ls.get("shots", 0) or 0
            saves = ls.get("saves", 0) or 0
            goals_against = ls.get("goals_against", 0) or 0
            wins = ls.get("wins", 0) or 0

            if game_date not in daily:
                daily[game_date] = {
                    "fpts": 0.0, "goals": 0, "assists": 0, "shots": 0,
                    "saves": 0, "goals_against": 0, "wins": 0, "games": 0,
                }
            day_entry = daily[game_date]
            day_entry["fpts"] = round(day_entry["fpts"] + fpts, 2)
            day_entry["goals"] += goals
            day_entry["assists"] += assists
            day_entry["shots"] += shots
            day_entry["saves"] += saves
            day_entry["goals_against"] += goals_against
            day_entry["wins"] += wins
            day_entry["games"] += 1

            total_fpts += fpts
            total_goals += goals
            total_assists += assists
            total_shots += shots
            total_saves += saves
            total_ga += goals_against
            total_wins += wins
            total_games += 1

            if game_date in daily_totals:
                daily_totals[game_date] = round(daily_totals[game_date] + fpts, 2)

        player_rows.append({
            "id": pid,
            "name": p.get("name"),
            "position": p.get("position"),
            "team": p.get("team"),
            "is_goalie": is_goalie,
            "total_fpts": round(total_fpts, 2),
            "total_goals": total_goals,
            "total_assists": total_assists,
            "total_shots": total_shots,
            "total_saves": total_saves,
            "total_goals_against": total_ga,
            "total_wins": total_wins,
            "total_games": total_games,
            "daily": daily,
        })

    player_rows.sort(key=lambda r: r["total_fpts"], reverse=True)
    period_total = round(sum(r["total_fpts"] for r in player_rows), 2)

    return {
        "league_id": league_id,
        "team_id": team_id,
        "team_name": team["name"],
        "week": week,
        "scoring_format": league.get("scoring_format", ""),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "days": days,
        "day_labels": day_labels,
        "players": player_rows,
        "daily_totals": daily_totals,
        "period_total_fpts": period_total,
    }


@router.get("/matchups/{league_id}/results")
async def get_week_results(league_id: str, week: int, request: Request):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    league = await require_league_member(db, user, league_id)
    matchups = await db.matchups.find({**season_query(league_id, schedule_season(league)), "week": week}).to_list(15000)
    matchups = await _resolve_open_slots(db, league_id, matchups)
    from services.h2h_scoring import live_scores
    matchups = await live_scores(db, league, matchups)
    # Scoring snapshots query Mongo by _id; serialize only after those writes.
    for m in matchups:
        m["_id"] = str(m["_id"])
    return matchups


@router.post("/matchups/simulate-week")
async def simulate_week(input: SimulateWeekRequest, request: Request):
    """Simulate a week's matchups using roster fantasy points + auto-crown playoff finals."""
    db = _deps["db"]
    sio = _deps["sio"]
    logger = _deps["logger"]
    get_current_user = _deps["get_current_user"]
    calculate_fantasy_points = _deps["calculate_fantasy_points"]
    _evaluate_conditions = _deps["_evaluate_conditions"]
    _execute_trade = _deps["_execute_trade"]
    broadcast_to_room = _deps["broadcast_to_room"]

    user = await get_current_user(request)
    from routes.league_guards import require_league_member
    league = await require_league_member(db, user, input.league_id)
    if league.get("scoring_format") == "rotisserie":
        from services.roto_schedule import finalize
        return await finalize(db, input.league_id, input.week, user)
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can simulate")

    matchups = await db.matchups.find({
        **season_query(input.league_id, schedule_season(league)),
        "week": input.week,
        "status": "scheduled",
    }).to_list(15000)
    if not matchups:
        raise HTTPException(status_code=400, detail="No scheduled matchups for this week")

    if any(not ObjectId.is_valid(m.get(f"{side}_team_id", "")) for m in matchups for side in ("home", "away")):
        raise HTTPException(status_code=400, detail="Fill all open schedule slots before simulating this week")

    config = await db.scoring_configs.find_one({"league_id": input.league_id})
    scoring_format = league.get("scoring_format", "head_to_head")

    # ── Auto-lock scoring rosters for this week (idempotent) ─────
    try:
        from utils.scoring_roster import lock_league_week
        await lock_league_week(db, league, week=input.week)
    except Exception:
        pass

    async def calc_team_score(team_id):
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
        if not team:
            return 0.0
        # Game-level allocation: credit only games owned + active at puck drop
        from utils.scoring_roster import week_to_time_range
        from utils.game_allocation import allocate_team_period_fpts
        period_start, period_end = week_to_time_range(league, input.week)
        if period_start and period_end:
            alloc = await allocate_team_period_fpts(
                db, str(team["_id"]), input.league_id,
                period_start, period_end, config,
            )
            return round(alloc["total_fpts"], 1)
        # Fallback: no season_start_date
        total = 0.0
        for pid in (team.get("roster") or []):
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total += calculate_fantasy_points(player, config)
        return round(total, 1)

    from services.profile_competition import capture_week, award, award_fields
    await capture_week(db, input.league_id, matchups)
    results = []
    for m in matchups:
        home_score = await calc_team_score(m["home_team_id"])
        away_score = await calc_team_score(m["away_team_id"])

        winner = None
        if home_score > away_score:
            winner = m["home_team_id"]
        elif away_score > home_score:
            winner = m["away_team_id"]

        category_fields = {}
        if scoring_format == "h2h-categories":
            from services.h2h_scoring import category_result
            category_fields = await category_result(db, league, m["home_team_id"], m["away_team_id"], input.week)
            winner = category_fields["winner"]

        await db.matchups.update_one(
            {"_id": m["_id"]},
            {"$set": {
                **category_fields,
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner,
                "status": "completed",
                "simulated_at": datetime.now(timezone.utc).isoformat(),
                "xp_win_award": award(20, m.get("xp_competition")),
            }}
        )

        # ─── Bracket advancement: propagate winner into next round TBD slot ──
        if winner and m.get("is_playoff") and m.get("bracket_round"):
            try:
                cur_round = int(m["bracket_round"])
                next_round = cur_round + 1
                # Resolve winner team name for the next-round matchup
                winner_team = await db.teams.find_one({"_id": ObjectId(winner)})
                winner_name = (winner_team or {}).get("name", "")
                next_matchups = await db.matchups.find({
                    "league_id": input.league_id,
                    "is_playoff": True,
                    "bracket_round": next_round,
                }).sort("_id", 1).to_list(50)
                sibs = await db.matchups.find({
                    "league_id": input.league_id,
                    "is_playoff": True,
                    "bracket_round": cur_round,
                }).sort("_id", 1).to_list(50)
                try:
                    cur_idx = [str(x["_id"]) for x in sibs].index(str(m["_id"]))
                except ValueError:
                    cur_idx = -1
                target_idx = cur_idx // 2 if cur_idx >= 0 else -1
                if target_idx >= 0 and target_idx < len(next_matchups):
                    target = next_matchups[target_idx]
                    set_fields: dict = {}
                    if not target.get("home_team_id"):
                        set_fields = {
                            "home_team_id": winner, "home_team_tbd": False,
                            "home_team_name": winner_name,
                        }
                    elif not target.get("away_team_id"):
                        set_fields = {
                            "away_team_id": winner, "away_team_tbd": False,
                            "away_team_name": winner_name,
                        }
                    if set_fields:
                        await db.matchups.update_one({"_id": target["_id"]}, {"$set": set_fields})
            except Exception as ex:
                logger.warning("bracket-advance (simulate) failed: %s", ex)

        # ─── Apply ELO ratings update for this matchup ──────────────
        try:
            from routes.ratings import apply_matchup_elo
            m_fresh = await db.matchups.find_one({"_id": m["_id"]})
            await apply_matchup_elo(input.league_id, m_fresh)
        except Exception as ex:
            logger.warning("ELO update failed for matchup %s: %s", str(m["_id"]), ex)

        # Snapshot per-team week summary for analytics rollup (idempotent upsert)
        from routes.analytics import _current_season
        _season = league.get("season") or _current_season()
        for side, opp in (("home", "away"), ("away", "home")):
            tid = m[f"{side}_team_id"]
            _doc = {
                "league_id": input.league_id, "season": _season, "week": input.week,
                "team_id": tid, "team_name": m[f"{side}_team_name"],
                "opponent_team_id": m[f"{opp}_team_id"],
                "points_for": float(home_score if side == "home" else away_score),
                "points_against": float(away_score if side == "home" else home_score),
                "win": winner == tid,
                "loss": bool(winner) and winner != tid,
                "tie": winner is None,
                "matchup_id": str(m["_id"]),
            }
            await db.week_summaries.update_one(
                {"league_id": input.league_id, "season": _season,
                 "week": input.week, "team_id": tid},
                {"$set": _doc},
                upsert=True,
            )

        win_award = award(20, m.get("xp_competition"))
        if winner == m["home_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"wins": 1, "xp_win_adjustment": win_award["awarded_xp"] - 20, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"losses": 1, "points_for": away_score, "points_against": home_score}})
        elif winner == m["away_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"wins": 1, "xp_win_adjustment": win_award["awarded_xp"] - 20, "points_for": away_score, "points_against": home_score}})
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"losses": 1, "points_for": home_score, "points_against": away_score}})
        else:
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"ties": 1, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"ties": 1, "points_for": away_score, "points_against": home_score}})

        # Iter 232N.24 — Fire an XP toast to the winning owner (and any
        # co-owners) as soon as their matchup settles. Best-effort so
        # a broadcast hiccup can't roll back the win increment above.
        if winner in (m.get("home_team_id"), m.get("away_team_id")):
            try:
                from utils.xp import emit_xp_gain
                broadcast_fn = _deps.get("broadcast_to_room")
                winner_team = await db.teams.find_one(
                    {"_id": ObjectId(winner)},
                    {"owner_id": 1, "co_owner_ids": 1, "name": 1},
                )
                if winner_team and broadcast_fn:
                    winning_name = winner_team.get("name", "your team")
                    losing_id = (
                        m["away_team_id"] if winner == m["home_team_id"]
                        else m["home_team_id"]
                    )
                    losing_team = await db.teams.find_one(
                        {"_id": ObjectId(losing_id)}, {"name": 1}
                    )
                    meta = {
                        "matchup_id": str(m["_id"]),
                        "week": int(input.week),
                        "opponent": (losing_team or {}).get("name"),
                        "team_name": winning_name,
                        "xp_award": win_award,
                    }
                    for uid in [winner_team.get("owner_id")] + list(winner_team.get("co_owner_ids") or []):
                        if uid:
                            await emit_xp_gain(
                                db, uid,
                                source="matchup_won",
                                delta=win_award["awarded_xp"],
                                broadcast_fn=broadcast_fn,
                                meta=meta,
                            )
            except Exception as ex:
                logger.debug(f"xp_awarded (matchup) skipped: {ex}")

        # Iter 108: When a playoff matchup settles, fire a one-time top-bell
        # notification to every league member ("Round N advanced — Team A defeats
        # Team B"). Idempotent within 22h via the existing tbd_deadline_pings
        # collection (we reuse its idempotency key shape).
        if m.get("is_playoff") and winner and m.get("bracket_round"):
            try:
                create_notif = _deps.get("create_notification")
                if create_notif:
                    bracket_round = int(m.get("bracket_round") or 1)
                    winner_team_name = (
                        m["home_team_name"] if winner == m["home_team_id"]
                        else m["away_team_name"]
                    )
                    loser_team_name = (
                        m["away_team_name"] if winner == m["home_team_id"]
                        else m["home_team_name"]
                    )
                    ping_key = {
                        "league_id": input.league_id,
                        "bracket": "playoff_advance",
                        "week": int(input.week),
                        "matchup_id": str(m["_id"]),
                    }
                    already = await db.tbd_deadline_pings.find_one({
                        **ping_key,
                        "created_at": {
                            "$gte": datetime.now(timezone.utc) - timedelta(hours=22)
                        },
                    })
                    if not already:
                        owner_ids = await db.teams.distinct(
                            "owner_id", {"league_id": input.league_id}
                        )
                        for uid in owner_ids:
                            if not uid:
                                continue
                            await create_notif(
                                uid,
                                "playoff_bracket_advance",
                                f"Round {bracket_round} advanced",
                                f"{winner_team_name} defeats {loser_team_name}",
                                input.league_id,
                                "/standings?tab=playoffs",
                            )
                        await db.tbd_deadline_pings.insert_one({
                            **ping_key,
                            "created_at": datetime.now(timezone.utc),
                        })
            except Exception as ex:
                logger.warning("bracket-advance notification failed: %s", ex)

        # Auto-crown for playoff finals
        if m.get("is_final") and winner:
            bracket = m.get("bracket", "championship")
            now = datetime.now(timezone.utc)
            loser_id = m["away_team_id"] if winner == m["home_team_id"] else m["home_team_id"]
            winner_name = m["home_team_name"] if winner == m["home_team_id"] else m["away_team_name"]
            if bracket == "championship":
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": await award_fields(db, winner, {"championship_won_at": now})})
                # Mark the runner-up so the profile trophy case can show it
                await db.teams.update_one({"_id": ObjectId(loser_id)},
                                          {"$set": {"playoff_runner_up_at": now}})
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "championship_awarded",
                    "description": f"🏆 {winner_name} won the championship!",
                    "message": f"Champion crowned: {winner_name}",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "championship_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}"},
                    "created_at": now,
                })
                pending = await db.trades.find({
                    "league_id": input.league_id, "conditional": True,
                    "status": {"$in": ["pending", "accepted", "conditional"]},
                }).to_list(500)
                unlocked = 0
                for t in pending:
                    try:
                        res = await _evaluate_conditions(t)
                        if res["all_met"] and t.get("status") == "accepted":
                            await _execute_trade(t)
                            unlocked += 1
                    except Exception as ex:
                        logger.warning("Conditional trade re-eval (auto-crown) failed league=%s trade=%s: %s",
                                       input.league_id, str(t.get("_id")), ex)
                # Re-evaluate pick-upgrade clauses on executed trades. Final
                # eval at championship → unmet upgrades lock as `failed`.
                apply_pu = _deps.get("_apply_pick_upgrades")
                if apply_pu:
                    executed = await db.trades.find({
                        "league_id": input.league_id, "status": "executed",
                        "pick_upgrades": {"$exists": True, "$ne": []},
                    }).to_list(500)
                    for t in executed:
                        try:
                            await apply_pu(t, final_eval=True)
                        except Exception as ex:
                            logger.warning("Pick-upgrade final-eval failed league=%s trade=%s: %s",
                                           input.league_id, str(t.get("_id")), ex)
                await sio.emit("championship_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "runner_up_team_id": loser_id,
                    "score": f"{home_score}-{away_score}",
                    "unlocked_trades": unlocked,
                    "crowned_at": now.isoformat(),
                })
            elif bracket == "consolation":
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": await award_fields(db, winner, {"consolation_won_at": now})})
                applied_steps: list = []
                prize = (league.get("consolation_prize") or {})
                if prize.get("type"):
                    await db.team_rewards.insert_one({
                        "league_id": input.league_id, "team_id": winner,
                        "team_name": winner_name, "source": "consolation_winner",
                        "prize": prize, "awarded_at": now,
                        "status": "pending_commissioner_fulfillment",
                    })
                    applied = await awards_module.apply_consolation_prize(input.league_id, winner, prize)
                    applied_steps = applied.get("steps", [])
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "consolation_awarded",
                    "description": f"Consolation bracket won by {winner_name}" + (
                        f" — {applied_steps[0]}" if applied_steps else ""
                    ),
                    "message": "Consolation bracket concluded",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "consolation_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}",
                             "prize": prize or None, "applied_steps": applied_steps},
                    "created_at": now,
                })
                await sio.emit("consolation_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "prize": prize or None,
                    "applied_steps": applied_steps,
                    "crowned_at": now.isoformat(),
                })
            elif bracket in ("conference_final", "conference"):
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": await award_fields(db, winner, {"conference_winner_at": now})})
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "conference_awarded",
                    "description": f"🥇 {winner_name} won the conference!",
                    "message": f"Conference champion crowned: {winner_name}",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "conference_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}"},
                    "created_at": now,
                })
                await sio.emit("conference_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "score": f"{home_score}-{away_score}",
                    "crowned_at": now.isoformat(),
                })
            elif bracket in ("division_final", "division"):
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": await award_fields(db, winner, {"division_winner_at": now})})
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "division_awarded",
                    "description": f"🏅 {winner_name} won the division!",
                    "message": f"Division champion crowned: {winner_name}",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "division_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}"},
                    "created_at": now,
                })
                await sio.emit("division_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "score": f"{home_score}-{away_score}",
                    "crowned_at": now.isoformat(),
                })

        results.append({
            "home": m["home_team_name"],
            "away": m["away_team_name"],
            "home_score": home_score,
            "away_score": away_score,
            "winner": m["home_team_name"] if winner == m["home_team_id"]
                      else m["away_team_name"] if winner else "Tie",
        })

    if scoring_format == "all_play":
        all_teams = await db.teams.find({"league_id": input.league_id}).to_list(15000)
        scores = {str(t["_id"]): await calc_team_score(str(t["_id"])) for t in all_teams}
        for team_id, score in scores.items():
            ap_wins = sum(1 for oid, oscore in scores.items() if oid != team_id and score > oscore)
            ap_losses = sum(1 for oid, oscore in scores.items() if oid != team_id and score < oscore)
            await db.teams.update_one({"_id": ObjectId(team_id)},
                                      {"$inc": {"wins": ap_wins, "losses": ap_losses}})

    if scoring_format == "guillotine":
        all_teams = await db.teams.find({"league_id": input.league_id, "eliminated": {"$ne": True}}).to_list(15000)
        scores = []
        for t in all_teams:
            s = await calc_team_score(str(t["_id"]))
            scores.append((str(t["_id"]), t["name"], s))
        if scores:
            scores.sort(key=lambda x: x[2])
            eliminated = scores[0]
            await db.teams.update_one({"_id": ObjectId(eliminated[0])}, {"$set": {"eliminated": True}})
            results.append({"eliminated": eliminated[1], "score": eliminated[2]})

    # Finalize automatic qualification only after every regular matchup is closed.
    regular_query = {"league_id": input.league_id, "is_playoff": {"$ne": True},
                     "is_consolation": {"$ne": True}}
    unfinished = await db.matchups.count_documents({**regular_query, "status": {"$ne": "completed"}})
    if unfinished == 0 and await db.matchups.count_documents(regular_query):
        playoff_query = {"league_id": input.league_id, "$or": [{"is_playoff": True}, {"is_consolation": True}]}
        started = await db.matchups.count_documents({**playoff_query, "status": {"$in": ["completed", "in_progress"]}})
        if not started:
            final_teams = await db.teams.find({"league_id": input.league_id}).to_list(15000)
            for consolation in (False, True):
                prefix = "consolation_" if consolation else "playoff_"
                if league.get(f"{prefix}seeding_method") == "custom":
                    continue
                seeded = _build_playoff_bracket(league, final_teams, is_consolation=consolation)
                first_round = [row for row in seeded if row.get("bracket_round") == 1]
                if not first_round:
                    continue
                query = {"league_id": input.league_id, "week": first_round[0]["week"],
                         "is_consolation": consolation, "bracket_round": 1}
                existing = await db.matchups.find(query).sort("_id", 1).to_list(15000)
                for saved, final in zip(existing, first_round):
                    await db.matchups.update_one({"_id": saved["_id"], "status": "scheduled"}, {"$set": {
                        "home_team_id": final["home_team_id"], "away_team_id": final["away_team_id"]}})

    await broadcast_to_room(f"league_{input.league_id}", "week_simulated", {
        "week": input.week,
        "results": results,
    })

    # ─── Division-winner auto-crown ──────────────────────────────
    # Fire when the just-simulated week is the FINAL regular-season week:
    #   last_regular_season_week = max(week) among matchups with is_playoff != True
    # Uses tiebreakers: (wins desc, division_wins desc, points_for desc).
    # Idempotent: skips teams that already have `division_winner_at` set.
    try:
        rs_agg = await db.matchups.aggregate([
            {"$match": {
                "league_id": input.league_id,
                "$or": [{"is_playoff": {"$exists": False}}, {"is_playoff": False}],
            }},
            {"$group": {"_id": None, "max_week": {"$max": "$week"}}},
        ]).to_list(1)
        last_rs_week = rs_agg[0]["max_week"] if rs_agg else None

        if last_rs_week is not None and input.week >= last_rs_week:
            all_league_teams = await db.teams.find({"league_id": input.league_id}).to_list(15000)
            divisions_seen = {t.get("division") for t in all_league_teams if t.get("division")}
            if len(divisions_seen) >= 2:
                now = datetime.now(timezone.utc)
                # Compute each team's division-win count from completed matchups
                completed = await db.matchups.find({
                    "league_id": input.league_id,
                    "status": {"$in": ["completed", "final"]},
                }).to_list(5000)
                team_div = {str(t["_id"]): t.get("division") for t in all_league_teams}
                div_wins: dict = {str(t["_id"]): 0 for t in all_league_teams}
                for mm in completed:
                    hid = mm.get("home_team_id")
                    aid = mm.get("away_team_id")
                    if not hid or not aid:
                        continue
                    # Only count intra-division games
                    if team_div.get(hid) and team_div.get(hid) == team_div.get(aid):
                        hs = float(mm.get("home_score") or 0)
                        as_ = float(mm.get("away_score") or 0)
                        if hs > as_:
                            div_wins[hid] = div_wins.get(hid, 0) + 1
                        elif as_ > hs:
                            div_wins[aid] = div_wins.get(aid, 0) + 1

                for div_name in divisions_seen:
                    div_teams = [t for t in all_league_teams if t.get("division") == div_name]
                    if not div_teams:
                        continue
                    # Skip if someone in this division already crowned this season
                    if any(t.get("division_winner_at") for t in div_teams):
                        continue
                    div_teams_sorted = sorted(
                        div_teams,
                        key=lambda t: (
                            int(t.get("wins", 0) or 0),
                            int(div_wins.get(str(t["_id"]), 0) or 0),
                            float(t.get("points_for", 0.0) or 0.0),
                        ),
                        reverse=True,
                    )
                    winner_team = div_teams_sorted[0]
                    winner_id = str(winner_team["_id"])
                    winner_name = winner_team.get("name", "Unknown")
                    await db.teams.update_one(
                        {"_id": winner_team["_id"]},
                        {"$set": await award_fields(db, winner_id, {"division_winner_at": now})},
                    )
                    await db.activity_feed.insert_one({
                        "league_id": input.league_id,
                        "event_type": "division_awarded",
                        "description": f"🏅 {winner_name} won the {div_name} Division!",
                        "message": f"Division champion crowned: {winner_name} ({div_name})",
                        "created_at": now,
                    })
                    await db.audit_log.insert_one({
                        "league_id": input.league_id,
                        "actor_id": "system",
                        "actor_name": "System (auto-crown)",
                        "action": "division_awarded_regular_season",
                        "role": "system",
                        "diff": {
                            "winner_team_id": winner_id,
                            "division": div_name,
                            "wins": winner_team.get("wins", 0),
                            "division_wins": div_wins.get(winner_id, 0),
                            "points_for": winner_team.get("points_for", 0.0),
                            "reason": "end_of_regular_season",
                        },
                        "created_at": now,
                    })
                    await sio.emit("division_crowned", {
                        "league_id": input.league_id,
                        "team_id": winner_id,
                        "team_name": winner_name,
                        "division": div_name,
                        "reason": "end_of_regular_season",
                        "crowned_at": now.isoformat(),
                    })
    except Exception as e:
        logger.warning(f"Division auto-crown skipped: {e}")

    # ─── Auto-snapshot season when last playoff week completes ──────
    try:
        from routes.seasons import _maybe_auto_snapshot_season
        await _maybe_auto_snapshot_season(input.league_id)
    except Exception as e:
        logger.warning(f"Auto-snapshot skipped: {e}")

    return {"week": input.week, "results": results, "matchups_simulated": len(matchups)}


router.include_router(scheduler_routes.router)

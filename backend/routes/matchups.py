"""Matchups: schedule generation, get-current-week, simulate-week (with auto-crown)."""
import itertools
import random as _random
from datetime import datetime, timezone, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes import awards as awards_module

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


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
    # Rounds 2..N — TBD placeholders, one per surviving slot
    surviving = len(round_pairs)
    for rnd_offset in range(1, end_wk - start_wk + 1):
        surviving = max(1, surviving // 2) if rnd_offset > 0 else surviving
        if surviving < 1:
            break
        for _ in range(surviving // 2 if surviving > 1 else 1):
            out.append({
                "week": start_wk + rnd_offset,
                "home_team_id": None,
                "away_team_id": None,
                "home_team_tbd": True,
                "away_team_tbd": True,
                "bracket_round": rnd_offset + 1,
                "is_playoff": not is_consolation,
                "is_consolation": is_consolation,
            })
        if surviving == 1:
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


def _distribute_to_weeks(pairings: list, team_ids: list, num_weeks: int) -> list:
    """Spread pairings across weeks so each team plays at most once per week.

    Greedy: iterate pairings in random order, placing each in the earliest
    week where neither team already has a game. If all weeks are full,
    evenly overflow the earliest weeks (rare for normal configs).
    """
    import random as _random
    weeks: list[list] = [[] for _ in range(num_weeks)]
    teams_in_week: list[set] = [set() for _ in range(num_weeks)]

    shuffled = pairings[:]
    _random.shuffle(shuffled)

    placed = []
    unplaced = []
    for home, away in shuffled:
        placed_flag = False
        for w in range(num_weeks):
            if home not in teams_in_week[w] and away not in teams_in_week[w]:
                weeks[w].append((home, away))
                teams_in_week[w].add(home)
                teams_in_week[w].add(away)
                placed.append((w + 1, home, away))
                placed_flag = True
                break
        if not placed_flag:
            unplaced.append((home, away))
    # Overflow: append leftovers into the sparsest weeks round-robin
    if unplaced:
        for home, away in unplaced:
            w = min(range(num_weeks), key=lambda x: len(weeks[x]))
            weeks[w].append((home, away))
            placed.append((w + 1, home, away))
    return placed  # list of (week, home, away)


# ─── Endpoints ───────────────────────────────────────────────
@router.post("/matchups/generate-schedule")
async def generate_schedule(input: GenerateScheduleRequest, request: Request):
    """Commissioner generates the full season schedule."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(
            status_code=403,
            detail="Only the commissioner (or a co-commissioner) can generate the schedule.",
        )

    teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
    # Iter 225 — Allow generating with empty placeholder slots.
    # Previously we required ≥2 teams which blocked commissioners from
    # finishing the setup wizard before all invitees joined. Now we pad
    # with virtual "Open Slot N" teams up to `league.max_teams`. The
    # placeholders are NOT stored in the `teams` collection — they only
    # appear in matchup rows with a synthetic team_id (`open_slot_{n}`)
    # that the UI treats as "TBD" / "Open Slot" until a real team fills it.
    max_teams_target = int(league.get("max_teams") or 0)
    actual_team_count = len(teams)

    placeholder_count = 0
    if max_teams_target > actual_team_count:
        placeholder_count = max_teams_target - actual_team_count
        for i in range(placeholder_count):
            slot_num = actual_team_count + i + 1
            teams.append({
                "_id": f"open_slot_{slot_num}",
                "name": f"Open Slot {slot_num}",
                "is_open_slot": True,
            })

    if len(teams) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Need at least 2 teams to generate a schedule — this league has {actual_team_count} team{'s' if actual_team_count != 1 else ''} "
                f"and max_teams={max_teams_target or 'unset'}. "
                "Bump `max_teams` to at least 2 or invite more managers first."
            ),
        )

    team_ids = [str(t["_id"]) for t in teams]
    team_map = {str(t["_id"]): t["name"] for t in teams}
    scoring_format = league.get("scoring_format", "head_to_head")

    # Resolve schedule length from league config when caller omits it,
    # so league administration is the single source of truth.
    num_weeks = input.num_weeks
    if num_weeks is None:
        num_weeks = int(league.get("regular_season_weeks") or 18)

    # Iter 225 — Season-window + NHL-window sanity check. Errors block,
    # warnings are returned to the UI so the commissioner can choose to
    # proceed anyway (warnings don't fail; errors do).
    s_errors, s_warnings = _season_schedule_warnings(
        season_start=league.get("season_start_date"),
        season_end=league.get("season_end_date"),
        matchup_length_days=int(league.get("matchup_length_days") or 7),
        num_weeks=num_weeks,
    )
    if s_errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Schedule doesn't fit the configured season.", "errors": s_errors},
        )

    # ── Iter 100: opponents_per_matchup_period (1..N-1) ───────────────
    # When > 1, each team plays N opponents per scoring period. We achieve
    # this by stacking the base schedule N times (each pass adds a fresh
    # opponent for every team in every week). Bounded to N-1 (can't play
    # more unique opponents than exist).
    # Iter 219 — Honour `matchups_per_week` (set on league creation) as
    # the primary source; fall back to legacy `opponents_per_matchup_period`
    # for backward compat with previously-created leagues.
    opponents_per_period = int(
        league.get("matchups_per_week")
        or league.get("opponents_per_matchup_period")
        or 1
    )
    max_opponents = max(1, len(teams) - 1)
    opponents_per_period = max(1, min(opponents_per_period, max_opponents))

    # Division-aware? Only opt-in via league.schedule_config AND ≥2 distinct
    # divisions configured. Otherwise fall back to vanilla round-robin.
    schedule_cfg = league.get("schedule_config")
    div_names = {t.get("division") for t in teams if t.get("division")}
    use_divisional = bool(schedule_cfg) and len(div_names) >= 2

    full_schedule: list = []
    if use_divisional:
        pairings = _build_division_pairings(teams, schedule_cfg)
        distributed = _distribute_to_weeks(pairings, team_ids, num_weeks)
        for week, home_id, away_id in distributed:
            if week > num_weeks:
                continue
            full_schedule.append({
                "week": week,
                "home_team_id": home_id,
                "home_team_name": team_map.get(home_id, ""),
                "away_team_id": away_id,
                "away_team_name": team_map.get(away_id, ""),
                "home_score": 0,
                "away_score": 0,
                "status": "scheduled",
                "winner": None,
            })
    else:
        base_schedule = generate_round_robin(team_ids)
        # Stack N copies of the round-robin to hit `opponents_per_period`.
        for pass_idx in range(opponents_per_period):
            week = 1
            cycle = itertools.cycle(base_schedule)
            # Skip ahead per pass so passes don't all start at round 0.
            for _ in range(pass_idx):
                next(cycle)
            while week <= num_weeks:
                round_matchups = next(cycle)
                _random.shuffle(round_matchups)
                for home_id, away_id in round_matchups:
                    full_schedule.append({
                        "week": week,
                        "home_team_id": home_id,
                        "home_team_name": team_map.get(home_id, ""),
                        "away_team_id": away_id,
                        "away_team_name": team_map.get(away_id, ""),
                        "home_score": 0,
                        "away_score": 0,
                        "status": "scheduled",
                        "winner": None,
                    })
                week += 1

        # ── Dedup safety: remove duplicate opponents in same week ──
        # Each (week, team_pair) must appear at most once.
        seen: set = set()
        deduped: list = []
        for m in full_schedule:
            pair = tuple(sorted([m["home_team_id"], m["away_team_id"]]))
            key = (m["week"], pair)
            if key not in seen:
                seen.add(key)
                deduped.append(m)
        full_schedule = deduped

    await db.matchups.delete_many({"league_id": input.league_id})
    if full_schedule:
        for m in full_schedule:
            m["league_id"] = input.league_id
            m["scoring_format"] = scoring_format
        await db.matchups.insert_many(full_schedule)

    # ── Iter 101: append playoff bracket + consolation bracket ──
    # Honors `playoff_format`, `playoff_seeding_method`, and `playoff_custom_matchups`
    # so the bracket UI on /standings (Playoffs tab) renders the configured ladder.
    bracket_matchups: list = []
    bracket_matchups.extend(_build_playoff_bracket(league, teams, is_consolation=False))
    if league.get("consolation_enabled"):
        bracket_matchups.extend(_build_playoff_bracket(league, teams, is_consolation=True))
    if bracket_matchups:
        for m in bracket_matchups:
            m["league_id"] = input.league_id
            m["scoring_format"] = scoring_format
            m["home_team_name"] = team_map.get(m.get("home_team_id") or "", "TBD")
            m["away_team_name"] = team_map.get(m.get("away_team_id") or "", "TBD")
            m["home_score"] = 0
            m["away_score"] = 0
            m["status"] = "scheduled"
            m["winner"] = None
        await db.matchups.insert_many(bracket_matchups)

    return {
        "message": f"Generated {len(full_schedule)} matchups for {num_weeks} weeks",
        "weeks": num_weeks,
        "mode": "division_aware" if use_divisional else "round_robin",
        "opponents_per_period": 1 if use_divisional else opponents_per_period,
        "playoff_matchups": len([m for m in bracket_matchups if m.get("is_playoff")]),
        "consolation_matchups": len([m for m in bracket_matchups if m.get("is_consolation")]),
        "placeholder_team_slots": placeholder_count,
        "warnings": s_warnings,
    }


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
    """Return a hypothetical round-robin schedule. No DB reads or writes.

    Uses placeholder team names ("Team 1".."Team N") so the create-league wizard
    can render an at-a-glance grid of who plays whom in each week. Honours
    `matchups_per_week` by stacking copies of the base round-robin (capped at
    `max_teams - 1` opponents per period).
    """
    n = input.max_teams
    team_ids = [f"team_{i + 1}" for i in range(n)]
    team_map = {tid: f"Team {i + 1}" for i, tid in enumerate(team_ids)}

    max_opponents = max(1, n - 1)
    opponents_per_period = max(1, min(input.matchups_per_week, max_opponents))

    base_schedule = generate_round_robin(team_ids)
    preview: list = []
    for pass_idx in range(opponents_per_period):
        week = 1
        cycle = itertools.cycle(base_schedule)
        for _ in range(pass_idx):
            next(cycle)
        while week <= input.num_weeks:
            round_matchups = next(cycle)
            for home_id, away_id in round_matchups:
                preview.append({
                    "week": week,
                    "home_team_id": home_id,
                    "home_team_name": team_map[home_id],
                    "away_team_id": away_id,
                    "away_team_name": team_map[away_id],
                })
            week += 1
    # Bucket by week for easy UI rendering
    by_week: dict[int, list] = {w: [] for w in range(1, input.num_weeks + 1)}
    for m in preview:
        by_week[m["week"]].append(m)
    return {
        "weeks": [
            {"week": w, "matchups": by_week[w]}
            for w in range(1, input.num_weeks + 1)
        ],
        "matchups_per_week": opponents_per_period,
        "team_count": n,
        "total_matchups": len(preview),
        "warnings": _season_schedule_warnings(
            season_start=input.season_start,
            season_end=input.season_end,
            matchup_length_days=input.matchup_length_days,
            num_weeks=input.num_weeks,
        )[1],
    }


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
async def get_matchups(league_id: str, week: Optional[int] = None):
    db = _deps["db"]
    query = {"league_id": league_id}
    if week:
        query["week"] = week
    matchups = await db.matchups.find(query).sort("week", 1).to_list(1000)
    for m in matchups:
        m["_id"] = str(m["_id"])
    matchups = await _resolve_open_slots(db, league_id, matchups)
    return matchups


@router.get("/matchups/{league_id}/current-week")
async def get_current_week(league_id: str):
    db = _deps["db"]
    pipeline = [
        {"$match": {"league_id": league_id, "status": "scheduled"}},
        {"$group": {"_id": None, "min_week": {"$min": "$week"}}},
    ]
    result = await db.matchups.aggregate(pipeline).to_list(1)
    current = result[0]["min_week"] if result else 1
    matchups = await db.matchups.find({"league_id": league_id, "week": current}).to_list(100)
    for m in matchups:
        m["_id"] = str(m["_id"])
    matchups = await _resolve_open_slots(db, league_id, matchups)
    return {"week": current, "matchups": matchups}


@router.get("/matchups/{league_id}/results")
async def get_week_results(league_id: str, week: int):
    db = _deps["db"]
    matchups = await db.matchups.find({"league_id": league_id, "week": week}).to_list(100)
    for m in matchups:
        m["_id"] = str(m["_id"])
    matchups = await _resolve_open_slots(db, league_id, matchups)
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
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can simulate")

    matchups = await db.matchups.find({
        "league_id": input.league_id,
        "week": input.week,
        "status": "scheduled",
    }).to_list(100)
    if not matchups:
        raise HTTPException(status_code=400, detail="No scheduled matchups for this week")

    config = await db.scoring_configs.find_one({"league_id": input.league_id})
    scoring_format = league.get("scoring_format", "head_to_head")

    async def calc_team_score(team_id):
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
        if not team:
            return 0.0
        roster = team.get("roster", [])
        total = 0.0
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total += calculate_fantasy_points(player, config)
        return round(total, 1)

    results = []
    for m in matchups:
        home_score = await calc_team_score(m["home_team_id"])
        away_score = await calc_team_score(m["away_team_id"])

        winner = None
        if home_score > away_score:
            winner = m["home_team_id"]
        elif away_score > home_score:
            winner = m["away_team_id"]

        await db.matchups.update_one(
            {"_id": m["_id"]},
            {"$set": {
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner,
                "status": "completed",
                "simulated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

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

        if winner == m["home_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"wins": 1, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"losses": 1, "points_for": away_score, "points_against": home_score}})
        elif winner == m["away_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"wins": 1, "points_for": away_score, "points_against": home_score}})
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
                    }
                    for uid in [winner_team.get("owner_id")] + list(winner_team.get("co_owner_ids") or []):
                        if uid:
                            await emit_xp_gain(
                                db, uid,
                                source="matchup_won",
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
                                          {"$set": {"championship_won_at": now}})
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
                                          {"$set": {"consolation_won_at": now}})
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
                                          {"$set": {"conference_winner_at": now}})
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
                                          {"$set": {"division_winner_at": now}})
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
        all_teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
        scores = {str(t["_id"]): await calc_team_score(str(t["_id"])) for t in all_teams}
        for team_id, score in scores.items():
            ap_wins = sum(1 for oid, oscore in scores.items() if oid != team_id and score > oscore)
            ap_losses = sum(1 for oid, oscore in scores.items() if oid != team_id and score < oscore)
            await db.teams.update_one({"_id": ObjectId(team_id)},
                                      {"$inc": {"wins": ap_wins, "losses": ap_losses}})

    if scoring_format == "guillotine":
        all_teams = await db.teams.find({"league_id": input.league_id, "eliminated": {"$ne": True}}).to_list(100)
        scores = []
        for t in all_teams:
            s = await calc_team_score(str(t["_id"]))
            scores.append((str(t["_id"]), t["name"], s))
        if scores:
            scores.sort(key=lambda x: x[2])
            eliminated = scores[0]
            await db.teams.update_one({"_id": ObjectId(eliminated[0])}, {"$set": {"eliminated": True}})
            results.append({"eliminated": eliminated[1], "score": eliminated[2]})

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
            all_league_teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
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
                        {"$set": {"division_winner_at": now}},
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

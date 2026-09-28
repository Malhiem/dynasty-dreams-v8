"""Game-level scoring allocation engine.

This module solves the core problem: for each game, determine who owned the
player at puck-drop AND whether the player was in an active lineup, then
credit only that game's stats to that team.

The key acceptance example:
  Player scores 10 goals (games 1-5) while on Team A.
  Player is traded to Team B.
  Player scores 6 goals (games 6-8) while on Team B.
  Result: Team A = 10 goals credit, Team B = 6 goals credit.
  Recomputation produces the same result.
  A correction to game 2 changes Team A's total, not Team B's.

Usage:
  from utils.game_allocation import allocate_team_period_fpts

  fpts = await allocate_team_period_fpts(
      db, team_id, league_id,
      period_start, period_end,
      config,
  )
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from bson import ObjectId

logger = logging.getLogger("game_allocation")


# ──────────────────────────────────────────────────────────────────
# Per-game fantasy point calculators
# ──────────────────────────────────────────────────────────────────

DEFAULT_SKATER_SCORING = {
    "goals": 3, "assists": 2, "plus_minus": 1, "penalty_minutes": -0.5,
    "power_play_goals": 1, "power_play_points": 0.5,
    "short_handed_goals": 2, "short_handed_points": 1,
    "game_winning_goals": 1, "shots": 0.5,
}

DEFAULT_GOALIE_SCORING = {
    "wins": 5, "losses": -2, "saves": 0.2, "goals_against": -1,
    "shutouts": 3, "overtime_losses": 0,
}

# Mapping from player_game_logs field names → scoring config field names
GAME_LOG_STAT_MAP = {
    "goals": "goals",
    "assists": "assists",
    "plus_minus": "plus_minus",
    "pim": "penalty_minutes",
    "ppg": "power_play_goals",
    "shg": "short_handed_goals",
    "sog": "shots",
}


def calc_game_fpts_from_live(live_stats: dict, is_goalie: bool,
                             config: Optional[dict] = None) -> float:
    """Compute fantasy points for one game from a player's live_stats entry."""
    if is_goalie:
        weights = (config or {}).get("goalie_scoring", DEFAULT_GOALIE_SCORING)
        return round(sum(
            (live_stats.get(stat, 0) or 0) * w for stat, w in weights.items()
        ), 2)
    weights = (config or {}).get("skater_scoring", DEFAULT_SKATER_SCORING)
    return round(sum(
        (live_stats.get(stat, 0) or 0) * w for stat, w in weights.items()
    ), 2)


def calc_game_fpts_from_game_log(game_log: dict, is_goalie: bool,
                                 config: Optional[dict] = None) -> float:
    """Compute fantasy points for one game from a player_game_logs document.

    Note: player_game_logs use different field names than scoring config
    (e.g., 'pim' instead of 'penalty_minutes', 'sog' instead of 'shots').
    Goalie game logs lack goalie-specific stats, so this only works well
    for skaters. For goalies with only game_log data, returns 0.
    """
    if is_goalie:
        # player_game_logs don't have goalie stats (saves, wins, etc.)
        return 0.0
    weights = (config or {}).get("skater_scoring", DEFAULT_SKATER_SCORING)
    total = 0.0
    for gl_field, config_field in GAME_LOG_STAT_MAP.items():
        w = weights.get(config_field, 0)
        total += (game_log.get(gl_field, 0) or 0) * w
    return round(total, 2)


def calc_game_roto_stats_from_live(live_stats: dict, is_goalie: bool) -> dict:
    """Extract roto category stats from one game's live_stats."""
    if is_goalie:
        return {
            "wins": live_stats.get("wins", 0) or 0,
            "losses": live_stats.get("losses", 0) or 0,
            "saves": live_stats.get("saves", 0) or 0,
            "goals_against": live_stats.get("goals_against", 0) or 0,
            "shutouts": live_stats.get("shutouts", 0) or 0,
            "overtime_losses": live_stats.get("overtime_losses", 0) or 0,
        }
    return {
        "goals": live_stats.get("goals", 0) or 0,
        "assists": live_stats.get("assists", 0) or 0,
        "points": (live_stats.get("goals", 0) or 0) + (live_stats.get("assists", 0) or 0),
        "plus_minus": live_stats.get("plus_minus", 0) or 0,
        "penalty_minutes": live_stats.get("penalty_minutes", 0) or 0,
        "power_play_goals": live_stats.get("power_play_goals", 0) or 0,
        "power_play_points": live_stats.get("power_play_points", 0) or 0,
        "short_handed_goals": live_stats.get("short_handed_goals", 0) or 0,
        "short_handed_points": live_stats.get("short_handed_points", 0) or 0,
        "shots": live_stats.get("shots", 0) or 0,
        "game_winning_goals": live_stats.get("game_winning_goals", 0) or 0,
    }


def calc_game_roto_stats_from_game_log(game_log: dict, is_goalie: bool) -> dict:
    """Extract roto category stats from one player_game_logs entry."""
    if is_goalie:
        return {}  # Game logs lack goalie-specific stats
    return {
        "goals": game_log.get("goals", 0) or 0,
        "assists": game_log.get("assists", 0) or 0,
        "points": (game_log.get("goals", 0) or 0) + (game_log.get("assists", 0) or 0),
        "plus_minus": game_log.get("plus_minus", 0) or 0,
        "penalty_minutes": game_log.get("pim", 0) or 0,
        "power_play_goals": game_log.get("ppg", 0) or 0,
        "short_handed_goals": game_log.get("shg", 0) or 0,
        "shots": game_log.get("sog", 0) or 0,
    }


# ──────────────────────────────────────────────────────────────────
# Game date resolution
# ──────────────────────────────────────────────────────────────────

async def _build_game_date_map(db, game_ids: list) -> dict[int, datetime]:
    """Map NHL game_ids → game start time using the games collection.

    Prefers explicit start_time/puck_drop field. Falls back to the date
    field as midnight UTC (convention: transactions AFTER midnight on the
    game date mean the game is credited to the pre-transaction owner).
    """
    if not game_ids:
        return {}
    result = {}
    cursor = db.games.find(
        {"nhl_game_id": {"$in": game_ids}},
        {"nhl_game_id": 1, "date": 1, "start_time": 1, "puck_drop": 1},
    )
    async for g in cursor:
        try:
            # Prefer explicit start_time or puck_drop
            start = g.get("start_time") or g.get("puck_drop")
            if start:
                if isinstance(start, datetime):
                    dt = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                result[g["nhl_game_id"]] = dt
                continue
            # Fall back to date string → midnight UTC
            d = str(g["date"]).split("T")[0]
            result[g["nhl_game_id"]] = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return result


def _parse_game_date(date_val) -> Optional[datetime]:
    """Parse a date/datetime value to a UTC datetime.

    Preserves time component when available. Falls back to midnight UTC
    for date-only strings.
    """
    if isinstance(date_val, datetime):
        return date_val.replace(tzinfo=timezone.utc) if date_val.tzinfo is None else date_val
    if date_val:
        try:
            s = str(date_val).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            try:
                # Date-only string
                return datetime.fromisoformat(str(date_val).split("T")[0]).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


# ──────────────────────────────────────────────────────────────────
# Core allocation: per-game ownership + eligibility check
# ──────────────────────────────────────────────────────────────────

async def _is_owned_and_eligible(
    db, player_id: str, team_id: str, league_id: str, game_start: datetime,
) -> bool:
    """Return True if team_id owned player_id at game_start AND the player
    was in an active lineup position at game_start."""
    from utils.scoring_roster import get_owner_at, is_lineup_eligible_at

    owner = await get_owner_at(db, player_id, league_id, game_start)
    if owner != team_id:
        return False
    eligible = await is_lineup_eligible_at(db, player_id, team_id, league_id, game_start)
    return eligible


# ──────────────────────────────────────────────────────────────────
# H2H / FPts allocation for a team in a period
# ──────────────────────────────────────────────────────────────────

async def allocate_team_period_fpts(
    db, team_id: str, league_id: str,
    period_start: datetime, period_end: datetime,
    config: Optional[dict] = None,
) -> dict:
    """Compute fantasy points for one team in one period using game-level
    ownership + lineup eligibility allocation.

    Returns::
        {
            "total_fpts": float,
            "game_count": int,
            "player_breakdown": { player_id: {"fpts": float, "games": int} },
        }

    Algorithm:
      1. Find all players who were ever on this team during [start, end]
         (from player_ownership_periods).
      2. For each player, get their per-game stats (live_stats + game_logs).
      3. For each game in the period, check ownership + eligibility at game start.
      4. Credit only the qualifying games to this team.
    """
    from utils.scoring_roster import ACTIVE_SECTIONS

    # Step 1: Get all players who overlapped with this team in the period
    owned_cursor = db.player_ownership_periods.find({
        "team_id": team_id,
        "league_id": league_id,
        "acquired_at": {"$lt": period_end},
        "$or": [
            {"released_at": None},
            {"released_at": {"$gt": period_start}},
        ],
    }, {"player_id": 1, "acquired_at": 1, "released_at": 1})
    ownership_spans = []
    async for doc in owned_cursor:
        ownership_spans.append(doc)
    player_ids = list({d["player_id"] for d in ownership_spans})

    if not player_ids:
        # No ownership periods recorded for this team in this period.
        # This means either:
        #   a) The team genuinely had no players during this period, OR
        #   b) The ownership history hasn't been backfilled yet.
        # We do NOT silently give all stats to the current roster owner
        # (that was the old bug). Instead, check if the league has been
        # backfilled and return appropriate results.
        league = await db.leagues.find_one(
            {"_id": ObjectId(league_id)},
            {"ownership_backfilled_at": 1},
        )
        backfilled = bool((league or {}).get("ownership_backfilled_at"))
        if backfilled:
            # Backfill ran but found no ownership for this team/period.
            # This is a genuine "no players" result.
            return {
                "total_fpts": 0.0, "game_count": 0, "player_breakdown": {},
                "uncertain": False,
            }
        # Not backfilled — we have insufficient evidence.
        # Return 0 with uncertain flag. Do NOT aggregate current roster
        # stats (that produces the exact "all stats go to current owner"
        # bug we are fixing).
        logger.warning(
            "No ownership data for team %s in league %s (period %s–%s). "
            "Run backfill to populate historical ownership.",
            team_id, league_id, period_start, period_end,
        )
        return {
            "total_fpts": 0.0, "game_count": 0, "player_breakdown": {},
            "uncertain": True, "needs_backfill": True,
        }

    # Step 2: Build per-player ownership intervals for fast in-memory checks
    ownership_by_player: dict[str, list[tuple[datetime, Optional[datetime]]]] = {}
    for span in ownership_spans:
        pid = span["player_id"]
        ownership_by_player.setdefault(pid, []).append(
            (span["acquired_at"], span.get("released_at"))
        )

    # Step 3: Build lineup eligibility intervals for fast in-memory checks
    lineup_by_player: dict[str, list[tuple[datetime, Optional[datetime], str]]] = {}
    for pid in player_ids:
        cursor = db.lineup_status_periods.find({
            "player_id": pid, "team_id": team_id, "league_id": league_id,
        }, {"started_at": 1, "ended_at": 1, "position": 1})
        async for ldoc in cursor:
            lineup_by_player.setdefault(pid, []).append(
                (ldoc["started_at"], ldoc.get("ended_at"), ldoc.get("position", "bench"))
            )

    # Step 4: Collect per-game stats from both live_stats and player_game_logs
    period_start_str = period_start.strftime("%Y-%m-%d")
    period_end_str = period_end.strftime("%Y-%m-%d")

    total_fpts = 0.0
    total_games = 0
    player_breakdown: dict[str, dict] = {}

    try:
        oid_list = [ObjectId(pid) for pid in player_ids if len(pid) == 24]
    except Exception:
        oid_list = []

    # Source A: live_stats on player documents
    if oid_list:
        players = await db.players.find(
            {"_id": {"$in": oid_list}},
            {"_id": 1, "player_type": 1, "position": 1, "live_stats": 1},
        ).to_list(500)

        # Collect all game_ids to batch-resolve dates
        all_game_ids = []
        for p in players:
            for gid_str in (p.get("live_stats") or {}):
                try:
                    all_game_ids.append(int(gid_str))
                except (ValueError, TypeError):
                    pass
        game_date_map = await _build_game_date_map(db, all_game_ids)

        for p in players:
            pid = str(p["_id"])
            is_goalie = p.get("player_type") == "goalie" or p.get("position") == "G"
            for gid_str, ls in (p.get("live_stats") or {}).items():
                try:
                    gid_int = int(gid_str)
                except (ValueError, TypeError):
                    continue
                game_date = game_date_map.get(gid_int)
                if not game_date:
                    # Try extracting from updated_at
                    game_date = _parse_game_date(ls.get("updated_at"))
                if not game_date:
                    continue
                # Check date is within period
                if game_date < period_start or game_date >= period_end:
                    continue
                # Check ownership at game start
                if not _owned_at_mem(pid, game_date, ownership_by_player):
                    continue
                # Check lineup eligibility at game start
                if not _eligible_at_mem(pid, game_date, lineup_by_player):
                    continue
                # Credit this game
                fpts = calc_game_fpts_from_live(ls, is_goalie, config)
                total_fpts += fpts
                total_games += 1
                pb = player_breakdown.setdefault(pid, {"fpts": 0.0, "games": 0})
                pb["fpts"] += fpts
                pb["games"] += 1

    # Source B: player_game_logs (for players with no live_stats coverage)
    pids_with_live = {pid for pid in player_breakdown}
    pids_needing_logs = [pid for pid in player_ids if pid not in pids_with_live]
    if pids_needing_logs:
        gl_cursor = db.player_game_logs.find({
            "player_id": {"$in": pids_needing_logs},
            "date": {"$gte": period_start_str, "$lt": period_end_str},
        })
        async for gl in gl_cursor:
            pid = gl["player_id"]
            game_date = _parse_game_date(gl.get("date") or gl.get("date_dt"))
            if not game_date:
                continue
            if game_date < period_start or game_date >= period_end:
                continue
            if not _owned_at_mem(pid, game_date, ownership_by_player):
                continue
            if not _eligible_at_mem(pid, game_date, lineup_by_player):
                continue
            # Determine if goalie
            p_doc = await db.players.find_one({"_id": ObjectId(pid)}, {"player_type": 1, "position": 1})
            is_goalie = (p_doc or {}).get("player_type") == "goalie" or (p_doc or {}).get("position") == "G"
            fpts = calc_game_fpts_from_game_log(gl, is_goalie, config)
            total_fpts += fpts
            total_games += 1
            pb = player_breakdown.setdefault(pid, {"fpts": 0.0, "games": 0})
            pb["fpts"] += fpts
            pb["games"] += 1

    # Round breakdowns
    for pid in player_breakdown:
        player_breakdown[pid]["fpts"] = round(player_breakdown[pid]["fpts"], 2)

    return {
        "total_fpts": round(total_fpts, 2),
        "game_count": total_games,
        "player_breakdown": player_breakdown,
    }


# ──────────────────────────────────────────────────────────────────
# Roto stat allocation for a team in a period
# ──────────────────────────────────────────────────────────────────

async def allocate_team_period_roto_stats(
    db, team_id: str, league_id: str,
    period_start: datetime, period_end: datetime,
    categories: list[str],
) -> dict:
    """Compute per-category roto stats using game-level ownership allocation.

    Returns: {cat: total, ...}
    """
    from utils.scoring_roster import ACTIVE_SECTIONS

    # Step 1: ownership spans
    owned_cursor = db.player_ownership_periods.find({
        "team_id": team_id, "league_id": league_id,
        "acquired_at": {"$lt": period_end},
        "$or": [{"released_at": None}, {"released_at": {"$gt": period_start}}],
    }, {"player_id": 1, "acquired_at": 1, "released_at": 1})
    ownership_spans = []
    async for doc in owned_cursor:
        ownership_spans.append(doc)
    player_ids = list({d["player_id"] for d in ownership_spans})

    if not player_ids:
        # Same logic as allocate_team_period_fpts: check backfill status.
        league = await db.leagues.find_one(
            {"_id": ObjectId(league_id)},
            {"ownership_backfilled_at": 1},
        )
        backfilled = bool((league or {}).get("ownership_backfilled_at"))
        if backfilled:
            result = {cat: 0 for cat in categories}
            result["uncertain"] = False
            return result
        logger.warning(
            "No ownership data for team %s in league %s (roto, period %s–%s). "
            "Run backfill to populate historical ownership.",
            team_id, league_id, period_start, period_end,
        )
        result = {cat: 0 for cat in categories}
        result["uncertain"] = True
        result["needs_backfill"] = True
        return result

    ownership_by_player: dict[str, list] = {}
    for span in ownership_spans:
        ownership_by_player.setdefault(span["player_id"], []).append(
            (span["acquired_at"], span.get("released_at"))
        )

    lineup_by_player: dict[str, list] = {}
    for pid in player_ids:
        cursor = db.lineup_status_periods.find({
            "player_id": pid, "team_id": team_id, "league_id": league_id,
        }, {"started_at": 1, "ended_at": 1, "position": 1})
        async for ldoc in cursor:
            lineup_by_player.setdefault(pid, []).append(
                (ldoc["started_at"], ldoc.get("ended_at"), ldoc.get("position", "bench"))
            )

    period_start_str = period_start.strftime("%Y-%m-%d")
    period_end_str = period_end.strftime("%Y-%m-%d")
    totals = {cat: 0 for cat in categories}

    try:
        oid_list = [ObjectId(pid) for pid in player_ids if len(pid) == 24]
    except Exception:
        oid_list = []

    # Source A: live_stats
    if oid_list:
        players = await db.players.find(
            {"_id": {"$in": oid_list}},
            {"_id": 1, "player_type": 1, "position": 1, "live_stats": 1},
        ).to_list(500)
        all_game_ids = []
        for p in players:
            for gid_str in (p.get("live_stats") or {}):
                try:
                    all_game_ids.append(int(gid_str))
                except (ValueError, TypeError):
                    pass
        game_date_map = await _build_game_date_map(db, all_game_ids)
        pids_covered = set()

        for p in players:
            pid = str(p["_id"])
            is_goalie = p.get("player_type") == "goalie" or p.get("position") == "G"
            has_games = False
            for gid_str, ls in (p.get("live_stats") or {}).items():
                try:
                    gid_int = int(gid_str)
                except (ValueError, TypeError):
                    continue
                game_date = game_date_map.get(gid_int) or _parse_game_date(ls.get("updated_at"))
                if not game_date or game_date < period_start or game_date >= period_end:
                    continue
                if not _owned_at_mem(pid, game_date, ownership_by_player):
                    continue
                if not _eligible_at_mem(pid, game_date, lineup_by_player):
                    continue
                has_games = True
                game_stats = calc_game_roto_stats_from_live(ls, is_goalie)
                for cat in categories:
                    totals[cat] += game_stats.get(cat, 0)
            if has_games:
                pids_covered.add(pid)

    # Source B: player_game_logs fallback
    pids_needing_logs = [pid for pid in player_ids if pid not in (pids_covered if oid_list else set())]
    if pids_needing_logs:
        gl_cursor = db.player_game_logs.find({
            "player_id": {"$in": pids_needing_logs},
            "date": {"$gte": period_start_str, "$lt": period_end_str},
        })
        async for gl in gl_cursor:
            pid = gl["player_id"]
            game_date = _parse_game_date(gl.get("date") or gl.get("date_dt"))
            if not game_date or game_date < period_start or game_date >= period_end:
                continue
            if not _owned_at_mem(pid, game_date, ownership_by_player):
                continue
            if not _eligible_at_mem(pid, game_date, lineup_by_player):
                continue
            p_doc = await db.players.find_one({"_id": ObjectId(pid)}, {"player_type": 1, "position": 1})
            is_goalie = (p_doc or {}).get("player_type") == "goalie" or (p_doc or {}).get("position") == "G"
            game_stats = calc_game_roto_stats_from_game_log(gl, is_goalie)
            for cat in categories:
                totals[cat] += game_stats.get(cat, 0)

    return totals


# ──────────────────────────────────────────────────────────────────
# In-memory ownership / eligibility checks (avoid DB round-trips)
# ──────────────────────────────────────────────────────────────────

def _normalize_dt(dt):
    """Ensure a datetime is timezone-aware (UTC) for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _owned_at_mem(
    player_id: str, at: datetime,
    ownership_by_player: dict[str, list[tuple[datetime, Optional[datetime]]]],
) -> bool:
    """Check ownership from pre-loaded spans (no DB call)."""
    at = _normalize_dt(at)
    spans = ownership_by_player.get(player_id, [])
    for acquired, released in spans:
        acquired = _normalize_dt(acquired)
        released = _normalize_dt(released)
        if acquired <= at and (released is None or released > at):
            return True
    return False


def _eligible_at_mem(
    player_id: str, at: datetime,
    lineup_by_player: dict[str, list[tuple[datetime, Optional[datetime], str]]],
) -> bool:
    """Check lineup eligibility from pre-loaded periods (no DB call).

    No data → assume eligible (backward compat for un-tracked leagues).
    Gap in data → assume eligible (the gap typically represents the
    initial active state before any lineup change was recorded).
    """
    from utils.scoring_roster import ACTIVE_SECTIONS
    at = _normalize_dt(at)
    periods = lineup_by_player.get(player_id, [])
    if not periods:
        return True  # No tracking data at all → assume eligible
    for started, ended, position in periods:
        started = _normalize_dt(started)
        ended = _normalize_dt(ended)
        if started <= at and (ended is None or ended > at):
            return position in ACTIVE_SECTIONS
    return True  # Gap in data → assume eligible (pre-tracking period)


# ──────────────────────────────────────────────────────────────────
# Fallback: aggregate scoring (no ownership data available)
# ──────────────────────────────────────────────────────────────────

async def _fallback_aggregate_scoring(
    db, team_id: str, player_ids: list[str], config: Optional[dict],
) -> dict:
    """Backward-compat: sum full player stats when no ownership data exists."""
    from server import calculate_fantasy_points
    total = 0.0
    for pid in player_ids:
        try:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total += calculate_fantasy_points(player, config)
        except Exception:
            pass
    return {"total_fpts": round(total, 1), "game_count": 0, "player_breakdown": {}}


async def _fallback_aggregate_roto(
    db, player_ids: list[str], categories: list[str],
) -> dict:
    """Backward-compat: sum full player stats for roto categories."""
    totals = {cat: 0 for cat in categories}
    for pid in player_ids:
        try:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                for cat in categories:
                    totals[cat] += player.get(cat, 0)
        except Exception:
            pass
    return totals

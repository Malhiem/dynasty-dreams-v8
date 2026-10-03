"""Historical scoring-roster helpers — point-in-time ownership & lineup eligibility.

Fixes the "retroactive stat reassignment" bug: stats are credited based on
who owned the player AND whether the player was lineup-eligible at the time
each stat was earned — not based on the current (live) roster.

Collections
-----------
``player_ownership_periods``
    Continuous ownership ledger. Each doc represents one ownership span::

        { player_id, team_id, league_id,
          acquired_at: datetime, released_at: datetime|null,
          source: "trade"|"add"|"draft"|"waiver"|"admin",
          release_source: "trade"|"drop"|"release"|"admin"|null }

    ``released_at = null`` → player is currently on this team.
    Unique compound: (player_id, league_id, acquired_at).

``lineup_status_periods``
    Tracks when players move between active / bench / IR / etc.::

        { player_id, team_id, league_id,
          position: "forward"|"defense"|"goalie"|"bench"|"ir"|"ir-plus"|"taxi"|"minors",
          started_at: datetime, ended_at: datetime|null }

    ``ended_at = null`` → current position.

``scoring_rosters``  (kept for fast weekly caching)
``roster_change_log`` (kept for auditing)

Key helpers
-----------
``record_ownership_start / record_ownership_end`` — write to ownership_periods
``record_lineup_change``  — write to lineup_status_periods
``get_owner_at``          — who owned player P in league L at time T?
``get_roster_at``         — which players did team T own at time T?
``is_lineup_eligible_at`` — was player P active (not bench/IR) at time T?
``get_eligible_roster_for_period`` — the big one: returns only players who
    were both owned AND lineup-eligible during [start, end], respecting
    the league's lock rules.
``get_scoring_roster``    — backward-compatible wrapper (week-based).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from bson import ObjectId

logger = logging.getLogger("scoring_roster")

ACTIVE_SECTIONS = {"forward", "defense", "goalie"}


def _resolve_league_start_dt(league: Optional[dict]) -> datetime:
    """Return the league's season start as a UTC datetime.

    Falls back to league created_at, then to a hardcoded epoch.
    """
    if league:
        ssd = league.get("season_start_date")
        if ssd:
            try:
                dt = datetime.fromisoformat(str(ssd).split("T", 1)[0])
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
        created = league.get("created_at")
        if created:
            if isinstance(created, datetime):
                return created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
            try:
                return datetime.fromisoformat(str(created)).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
    return datetime(2025, 10, 1, tzinfo=timezone.utc)


def _section_to_canonical(section: str) -> str:
    """Map lineup section names to canonical position names."""
    section = section.lower()
    if section in ("forward", "forwards", "f", "c", "lw", "rw", "w"):
        return "forward"
    if section in ("defense", "d", "defence"):
        return "defense"
    if section in ("goalie", "goalies", "g", "goalies_minors"):
        return "goalie"
    if section in ("ir", "ir-plus", "ir+", "injured_reserve"):
        return "ir"
    if section in ("taxi", "taxi_squad"):
        return "taxi"
    if section in ("minors", "minor"):
        return "minors"
    return "bench"


# ──────────────────────────────────────────────────────────────────
# Ownership Periods
# ──────────────────────────────────────────────────────────────────

async def record_ownership_start(
    db, *, player_id: str, team_id: str, league_id: str,
    source: str, timestamp: Optional[datetime] = None,
) -> None:
    """Open a new ownership span for (player, team, league)."""
    now = timestamp or datetime.now(timezone.utc)
    try:
        await db.player_ownership_periods.insert_one({
            "player_id": player_id,
            "team_id": team_id,
            "league_id": league_id,
            "acquired_at": now,
            "released_at": None,
            "source": source,
            "release_source": None,
        })
    except Exception as exc:
        logger.warning("ownership_start write failed: %s", exc)


async def record_ownership_end(
    db, *, player_id: str, team_id: str, league_id: str,
    release_source: str, timestamp: Optional[datetime] = None,
) -> None:
    """Close the open ownership span for (player, team, league).

    If no open span exists (initial ownership was never seeded), creates
    a retroactive closed period from the league's season start to *now*.
    This preserves the old team's historical stat credit.
    """
    now = timestamp or datetime.now(timezone.utc)
    try:
        result = await db.player_ownership_periods.update_one(
            {"player_id": player_id, "team_id": team_id,
             "league_id": league_id, "released_at": None},
            {"$set": {"released_at": now, "release_source": release_source}},
        )
        if result.modified_count == 0:
            # No open span found → initial ownership was never seeded.
            # Create a retroactive closed period so the old team retains
            # credit for games during its ownership.
            league = await db.leagues.find_one(
                {"_id": ObjectId(league_id)},
                {"season_start_date": 1, "created_at": 1},
            )
            start = _resolve_league_start_dt(league)
            await db.player_ownership_periods.insert_one({
                "player_id": player_id,
                "team_id": team_id,
                "league_id": league_id,
                "acquired_at": start,
                "released_at": now,
                "source": "inferred_initial",
                "release_source": release_source,
            })
            logger.info(
                "Created retroactive ownership for player %s on team %s "
                "(league %s): %s → %s [source: inferred_initial]",
                player_id, team_id, league_id, start, now,
            )
    except Exception as exc:
        logger.warning("ownership_end write failed: %s", exc)


async def get_owner_at(
    db, player_id: str, league_id: str, at: datetime,
) -> Optional[str]:
    """Return team_id that owned *player_id* at datetime *at*, or None."""
    doc = await db.player_ownership_periods.find_one({
        "player_id": player_id,
        "league_id": league_id,
        "acquired_at": {"$lte": at},
        "$or": [
            {"released_at": None},
            {"released_at": {"$gt": at}},
        ],
    })
    return doc["team_id"] if doc else None


async def get_roster_at(
    db, team_id: str, league_id: str, at: datetime,
) -> list[str]:
    """Return player_ids owned by *team_id* at datetime *at*."""
    cursor = db.player_ownership_periods.find({
        "team_id": team_id,
        "league_id": league_id,
        "acquired_at": {"$lte": at},
        "$or": [
            {"released_at": None},
            {"released_at": {"$gt": at}},
        ],
    }, {"player_id": 1})
    return [doc["player_id"] async for doc in cursor]


async def get_player_ownership_history(
    db, player_id: str, league_id: str,
) -> list[dict]:
    """Return full ownership timeline for a player in a league, newest first."""
    cursor = db.player_ownership_periods.find(
        {"player_id": player_id, "league_id": league_id},
        {"_id": 0},
    ).sort("acquired_at", -1)
    return await cursor.to_list(200)


# ──────────────────────────────────────────────────────────────────
# Lineup Status Periods
# ──────────────────────────────────────────────────────────────────

async def record_lineup_change(
    db, *, player_id: str, team_id: str, league_id: str,
    new_position: str, timestamp: Optional[datetime] = None,
) -> None:
    """Close the current lineup period and open a new one."""
    now = timestamp or datetime.now(timezone.utc)
    try:
        # Close the current open period
        await db.lineup_status_periods.update_one(
            {"player_id": player_id, "team_id": team_id,
             "league_id": league_id, "ended_at": None},
            {"$set": {"ended_at": now}},
        )
        # Open a new period
        await db.lineup_status_periods.insert_one({
            "player_id": player_id,
            "team_id": team_id,
            "league_id": league_id,
            "position": new_position,
            "started_at": now,
            "ended_at": None,
        })
    except Exception as exc:
        logger.warning("lineup_change write failed: %s", exc)


async def is_lineup_eligible_at(
    db, player_id: str, team_id: str, league_id: str, at: datetime,
) -> bool:
    """Was the player in an active (scoring-eligible) position at *at*?

    Active sections: forward, defense, goalie.
    Bench, IR, IR+, taxi, minors are NOT eligible.

    Falls back to True when no lineup_status_periods exist (backward compat).
    """
    doc = await db.lineup_status_periods.find_one({
        "player_id": player_id,
        "team_id": team_id,
        "league_id": league_id,
        "started_at": {"$lte": at},
        "$or": [
            {"ended_at": None},
            {"ended_at": {"$gt": at}},
        ],
    })
    if not doc:
        return True  # No tracking data → assume eligible (backward compat)
    return doc.get("position", "bench") in ACTIVE_SECTIONS


async def get_player_lineup_history(
    db, player_id: str, team_id: str, league_id: str,
) -> list[dict]:
    """Return lineup position timeline for a player, newest first."""
    cursor = db.lineup_status_periods.find(
        {"player_id": player_id, "team_id": team_id, "league_id": league_id},
        {"_id": 0},
    ).sort("started_at", -1)
    return await cursor.to_list(500)


# ──────────────────────────────────────────────────────────────────
# Eligible Roster for a Period (the main scoring helper)
# ──────────────────────────────────────────────────────────────────

async def get_eligible_roster_for_period(
    db, team_id: str, league_id: str,
    period_start: datetime, period_end: datetime,
) -> list[str]:
    """Return player_ids that were BOTH owned by *team_id* AND in an
    active lineup position for at least part of [period_start, period_end].

    This is the canonical helper for all scoring computations.
    """
    # Step 1: all players owned during the period (ownership overlaps)
    owned_cursor = db.player_ownership_periods.find({
        "team_id": team_id,
        "league_id": league_id,
        "acquired_at": {"$lt": period_end},
        "$or": [
            {"released_at": None},
            {"released_at": {"$gt": period_start}},
        ],
    }, {"player_id": 1})
    owned_pids = [doc["player_id"] async for doc in owned_cursor]
    if not owned_pids:
        return []

    # Step 2: filter to those who were lineup-eligible during the period
    eligible = []
    for pid in owned_pids:
        # Check if any active lineup period overlaps with the scoring period
        active_doc = await db.lineup_status_periods.find_one({
            "player_id": pid,
            "team_id": team_id,
            "league_id": league_id,
            "position": {"$in": list(ACTIVE_SECTIONS)},
            "started_at": {"$lt": period_end},
            "$or": [
                {"ended_at": None},
                {"ended_at": {"$gt": period_start}},
            ],
        })
        if active_doc:
            eligible.append(pid)
        else:
            # Backward compat: if NO lineup_status_periods exist for this
            # player at all, assume eligible (data predates tracking).
            has_any = await db.lineup_status_periods.find_one({
                "player_id": pid, "team_id": team_id, "league_id": league_id,
            })
            if not has_any:
                eligible.append(pid)

    return eligible


# ──────────────────────────────────────────────────────────────────
# Week ↔ Time Range Resolution
# ──────────────────────────────────────────────────────────────────

def week_to_time_range(
    league: dict, week: int,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Convert a matchup week number to (start_dt, end_dt) using the
    league's season_start_date and matchup_length_days.

    Returns (None, None) if the league has no season_start_date.
    """
    start_str = league.get("season_start_date")
    if not start_str:
        return None, None
    try:
        season_start = datetime.fromisoformat(str(start_str).split("T", 1)[0])
        season_start = season_start.replace(tzinfo=timezone.utc)
    except Exception:
        return None, None
    length = max(1, int(league.get("matchup_length_days") or 7))
    period_start = season_start + timedelta(days=(week - 1) * length)
    period_end = period_start + timedelta(days=length)
    return period_start, period_end


# ──────────────────────────────────────────────────────────────────
# Scoring Roster — unified entry point
# ──────────────────────────────────────────────────────────────────

async def get_scoring_roster(
    db, team_id: str, league_id: str,
    week: Optional[int] = None,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> list[str]:
    """Return the roster to use for scoring.

    Resolution order:
      1. If period_start/period_end are given → point-in-time eligible roster.
      2. If week is given → resolve to time range via league config, then (1).
         Falls back to week-level scoring_rosters snapshot if league has no
         season_start_date, then to live roster.
      3. No week → live roster (current state).
    """
    # Direct time-range query
    if period_start and period_end:
        eligible = await get_eligible_roster_for_period(
            db, team_id, league_id, period_start, period_end,
        )
        if eligible:
            return eligible
        # Fallback to live roster if no ownership data exists
        team = await db.teams.find_one({"_id": ObjectId(team_id)}, {"roster": 1})
        return list((team or {}).get("roster") or [])

    # Week-based resolution
    if week is not None:
        league = await db.leagues.find_one(
            {"_id": ObjectId(league_id)},
            {"season_start_date": 1, "matchup_length_days": 1},
        )
        if league:
            ps, pe = week_to_time_range(league, week)
            if ps and pe:
                eligible = await get_eligible_roster_for_period(
                    db, team_id, league_id, ps, pe,
                )
                if eligible:
                    return eligible

        # Fall back to week-level snapshot
        snap = await db.scoring_rosters.find_one({
            "league_id": league_id,
            "team_id": team_id,
            "week": week,
        })
        if snap:
            return list(snap.get("roster") or [])

    # Final fallback: live roster
    team = await db.teams.find_one({"_id": ObjectId(team_id)}, {"roster": 1})
    return list((team or {}).get("roster") or [])


# ──────────────────────────────────────────────────────────────────
# Roster Change Log (kept for auditing)
# ──────────────────────────────────────────────────────────────────

async def log_roster_change(
    db, *, team_id: str, league_id: str, player_id: str,
    action: str, source: str,
    week: Optional[int] = None, metadata: Optional[dict] = None,
    timestamp: Optional[datetime] = None,
) -> None:
    """Append a row to roster_change_log AND update ownership + lineup periods.

    Args:
        timestamp: When the change occurred. Defaults to now if not given.
            Passing an explicit time is important for retroactive processing
            (e.g., waiver claims, test fixtures).
    """
    now = timestamp or datetime.now(timezone.utc)
    try:
        doc = {
            "team_id": team_id, "league_id": league_id,
            "player_id": player_id, "action": action,
            "source": source, "week": week, "timestamp": now,
        }
        if metadata:
            doc["metadata"] = metadata
        await db.roster_change_log.insert_one(doc)
    except Exception as exc:
        logger.warning("roster_change_log write failed: %s", exc)

    # Maintain ownership periods
    if action == "add":
        await record_ownership_start(
            db, player_id=player_id, team_id=team_id,
            league_id=league_id, source=source, timestamp=now,
        )
        # Seed initial lineup position from team's current lineup state.
        # This ensures no gap exists for eligibility checks.
        try:
            team = await db.teams.find_one(
                {"_id": ObjectId(team_id)}, {"lineup": 1},
            )
            lineup = (team or {}).get("lineup") or {}
            player_slot = lineup.get(player_id)
            if isinstance(player_slot, dict):
                section = (player_slot.get("section") or "bench").lower()
            else:
                section = "bench"
            # Map section to canonical position
            position = _section_to_canonical(section)
            await db.lineup_status_periods.insert_one({
                "player_id": player_id,
                "team_id": team_id,
                "league_id": league_id,
                "position": position,
                "started_at": now,
                "ended_at": None,
            })
        except Exception as exc:
            logger.warning("initial lineup seed failed: %s", exc)

    elif action == "remove":
        await record_ownership_end(
            db, player_id=player_id, team_id=team_id,
            league_id=league_id, release_source=source, timestamp=now,
        )
        # Close any open lineup period for this player on this team
        try:
            await db.lineup_status_periods.update_many(
                {"player_id": player_id, "team_id": team_id,
                 "league_id": league_id, "ended_at": None},
                {"$set": {"ended_at": now}},
            )
        except Exception as exc:
            logger.warning("lineup period close on remove failed: %s", exc)


# ──────────────────────────────────────────────────────────────────
# Scoring Roster Snapshots (week-level cache, kept for fast lookups)
# ──────────────────────────────────────────────────────────────────

async def ensure_scoring_roster(db, league: dict, team_id: str, week: int) -> dict:
    """Idempotent week-level snapshot (first write wins)."""
    league_id = str(league["_id"])
    existing = await db.scoring_rosters.find_one({
        "league_id": league_id, "team_id": team_id, "week": week,
    })
    if existing:
        return existing

    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        return {"roster": [], "lineup": {}}

    doc = {
        "league_id": league_id, "team_id": team_id, "week": week,
        "roster": list(team.get("roster") or []),
        "lineup": dict(team.get("lineup") or {}),
        "locked_at": datetime.now(timezone.utc),
    }
    try:
        await db.scoring_rosters.insert_one(doc)
    except Exception:
        existing = await db.scoring_rosters.find_one({
            "league_id": league_id, "team_id": team_id, "week": week,
        })
        if existing:
            return existing
    return doc


async def lock_league_week(db, league: dict, week: Optional[int] = None) -> int:
    """Batch-lock all teams in a league for *week*."""
    league_id = str(league["_id"])
    if week is None:
        week = int(league.get("current_week") or 1)
    teams = await db.teams.find({"league_id": league_id}, {"_id": 1}).to_list(200)
    created = 0
    for t in teams:
        tid = str(t["_id"])
        existing = await db.scoring_rosters.find_one({
            "league_id": league_id, "team_id": tid, "week": week,
        })
        if not existing:
            await ensure_scoring_roster(db, league, tid, week)
            created += 1
    return created


# ──────────────────────────────────────────────────────────────────
# Index bootstrap
# ──────────────────────────────────────────────────────────────────

async def ensure_indexes(db) -> None:
    """Create all required indexes."""
    try:
        await db.scoring_rosters.create_index(
            [("league_id", 1), ("team_id", 1), ("week", 1)],
            unique=True, name="ux_scoring_roster_league_team_week",
        )
        await db.roster_change_log.create_index(
            [("team_id", 1), ("timestamp", -1)],
            name="ix_roster_change_log_team_time",
        )
        await db.roster_change_log.create_index(
            [("league_id", 1), ("week", 1)],
            name="ix_roster_change_log_league_week",
        )
        # Ownership periods indexes
        await db.player_ownership_periods.create_index(
            [("player_id", 1), ("league_id", 1), ("acquired_at", -1)],
            name="ix_ownership_player_league_time",
        )
        await db.player_ownership_periods.create_index(
            [("team_id", 1), ("league_id", 1), ("acquired_at", 1), ("released_at", 1)],
            name="ix_ownership_team_league_range",
        )
        # Lineup status periods indexes
        await db.lineup_status_periods.create_index(
            [("player_id", 1), ("team_id", 1), ("league_id", 1), ("started_at", -1)],
            name="ix_lineup_status_player_team_time",
        )
        await db.lineup_status_periods.create_index(
            [("team_id", 1), ("league_id", 1), ("position", 1),
             ("started_at", 1), ("ended_at", 1)],
            name="ix_lineup_status_team_position_range",
        )
    except Exception as exc:
        logger.warning("scoring_roster index creation: %s", exc)

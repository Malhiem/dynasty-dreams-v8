"""Historical scoring-roster helpers.

Solves the "retroactive stat reassignment" bug: every scoring path
previously read `team.roster` (the live/current roster), so a mid-week
trade would retroactively credit historical stats to the new owner.

This module introduces two collections and one key helper:

Collections
-----------
`scoring_rosters`  — per-team, per-week snapshots locked at the start of
                     each matchup period.  Schema::

    { league_id, team_id, week, roster: [str], lineup: {}, locked_at: datetime }

    Unique index: (league_id, team_id, week)

`roster_change_log` — append-only ledger of every roster mutation
                      (trade, drop, add, draft, waiver, admin).  Schema::

    { team_id, league_id, player_id, action: "add"|"remove",
      source: "trade"|"drop"|"add"|"draft"|"waiver"|"admin"|"undo",
      week, timestamp }

Helpers
-------
`log_roster_change(db, ...)` — call from every roster-mutating code path.
`ensure_scoring_roster(db, league, team_id, week)` — idempotent: creates
    a scoring-roster snapshot for (team, week) if one doesn't exist yet.
`get_scoring_roster(db, team_id, league_id, week)` — returns the locked
    roster list for the given week. Falls back to current roster when no
    snapshot exists (backward-compat for older leagues / pre-lock weeks).
`lock_league_week(db, league)` — batch-lock every team in a league for
    the current week (called on week-start or first scoring call).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

logger = logging.getLogger("scoring_roster")


# ── Roster Change Log ────────────────────────────────────────────

async def log_roster_change(
    db,
    *,
    team_id: str,
    league_id: str,
    player_id: str,
    action: str,          # "add" | "remove"
    source: str,          # "trade" | "drop" | "add" | "draft" | "waiver" | "admin" | "undo"
    week: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Append one row to `roster_change_log`. Best-effort; never raises."""
    try:
        doc = {
            "team_id": team_id,
            "league_id": league_id,
            "player_id": player_id,
            "action": action,
            "source": source,
            "week": week,
            "timestamp": datetime.now(timezone.utc),
        }
        if metadata:
            doc["metadata"] = metadata
        await db.roster_change_log.insert_one(doc)
    except Exception as exc:
        logger.warning("roster_change_log write failed: %s", exc)


# ── Scoring Roster Snapshots ─────────────────────────────────────

async def ensure_scoring_roster(
    db,
    league: dict,
    team_id: str,
    week: int,
) -> dict:
    """Idempotent: return the scoring-roster doc for (team, week).

    If none exists yet, snapshot the team's *current* roster+lineup
    and persist it. Subsequent calls are no-ops (first write wins).
    """
    league_id = str(league["_id"])
    existing = await db.scoring_rosters.find_one({
        "league_id": league_id,
        "team_id": team_id,
        "week": week,
    })
    if existing:
        return existing

    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        return {"roster": [], "lineup": {}}

    doc = {
        "league_id": league_id,
        "team_id": team_id,
        "week": week,
        "roster": list(team.get("roster") or []),
        "lineup": dict(team.get("lineup") or {}),
        "locked_at": datetime.now(timezone.utc),
    }
    try:
        await db.scoring_rosters.insert_one(doc)
        logger.info("scoring_roster locked: league=%s team=%s week=%d (%d players)",
                     league_id, team_id, week, len(doc["roster"]))
    except Exception:
        # Duplicate key race — another process won; read theirs.
        existing = await db.scoring_rosters.find_one({
            "league_id": league_id,
            "team_id": team_id,
            "week": week,
        })
        if existing:
            return existing
    return doc


async def get_scoring_roster(
    db,
    team_id: str,
    league_id: str,
    week: Optional[int] = None,
) -> list[str]:
    """Return the roster that should be used for scoring in *week*.

    Priority:
      1. Locked scoring-roster snapshot for (team, week).
      2. Current live roster (fallback for weeks before the feature
         existed, or when no lock has fired yet).
    """
    if week is not None:
        snap = await db.scoring_rosters.find_one({
            "league_id": league_id,
            "team_id": team_id,
            "week": week,
        })
        if snap:
            return list(snap.get("roster") or [])

    # Fallback: live roster
    team = await db.teams.find_one({"_id": ObjectId(team_id)}, {"roster": 1})
    return list((team or {}).get("roster") or [])


async def lock_league_week(db, league: dict, week: Optional[int] = None) -> int:
    """Batch-lock all teams in a league for *week* (default: current_week).

    Returns the number of newly created snapshots.
    """
    league_id = str(league["_id"])
    if week is None:
        week = int(league.get("current_week") or 1)

    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1},
    ).to_list(200)

    created = 0
    for t in teams:
        tid = str(t["_id"])
        existing = await db.scoring_rosters.find_one({
            "league_id": league_id,
            "team_id": tid,
            "week": week,
        })
        if not existing:
            await ensure_scoring_roster(db, league, tid, week)
            created += 1
    return created


# ── Index bootstrap (call once at startup) ───────────────────────

async def ensure_indexes(db) -> None:
    """Create required indexes for scoring_rosters and roster_change_log."""
    try:
        await db.scoring_rosters.create_index(
            [("league_id", 1), ("team_id", 1), ("week", 1)],
            unique=True,
            name="ux_scoring_roster_league_team_week",
        )
        await db.roster_change_log.create_index(
            [("team_id", 1), ("timestamp", -1)],
            name="ix_roster_change_log_team_time",
        )
        await db.roster_change_log.create_index(
            [("league_id", 1), ("week", 1)],
            name="ix_roster_change_log_league_week",
        )
    except Exception as exc:
        logger.warning("scoring_roster index creation: %s", exc)

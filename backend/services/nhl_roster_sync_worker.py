"""Iter 230e — NHL roster sync worker.

Wakes up every `interval_seconds` (default 6h), fetches each NHL team's
current roster via the public NHL API, and for every player on file
diffs the incoming `current_team_abbrev` / `current_team_id` against
the stored `players` document. Diffs route through
`services.nhl_sync_dispatcher.apply_player_diff_and_notify` so that
NHL ↔ AHL movements automatically fan out `player_sent_down` /
`player_called_up` notifications to every team that rosters the
player.

Today the worker tracks two fields:
  • `current_team_id`     (NHL team integer id)
  • `current_team_abbrev` (3-letter code)

When a player's `current_team_abbrev` is present in the NHL roster
response, we infer they're on the NHL roster (league_status = "NHL").
When a previously-listed player vanishes from every NHL roster we
fetch, we infer they've been sent down (league_status = "AHL"). The
dispatcher handles all transition classification and notification
fanout — this worker is JUST the ingestion + diff loop.

Crucially this is an additive worker that NEVER deletes player rows or
modifies non-team fields. It's safe to run alongside the existing
`player_data_backfill_worker.py` (which handles birth dates + career
GP).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Optional, Set

import httpx

logger = logging.getLogger("nhl_roster_sync")

DEFAULT_INTERVAL_SEC = int(os.environ.get("NHL_ROSTER_SYNC_INTERVAL", str(6 * 60 * 60)))
NHL_ROSTER_URL = "https://api-web.nhle.com/v1/roster/{team}/current"
NHL_TEAMS_URL = "https://api-web.nhle.com/v1/standings/now"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
HEADERS = {"User-Agent": "DynastyDreams/iter230e-nhl-roster-sync"}


def _normalize_player_dict(raw: dict) -> Optional[dict]:
    """Maps the NHL roster API's player shape to the fields we care about.
    Returns None if the row is malformed."""
    nhl_id = raw.get("id")
    if not nhl_id:
        return None
    try:
        nhl_id = int(nhl_id)
    except Exception:
        return None
    return {"nhl_id": nhl_id, "raw": raw}


async def _fetch_team_codes(http: httpx.AsyncClient) -> list:
    """Returns a list of 3-letter NHL team codes from the standings."""
    try:
        r = await http.get(NHL_TEAMS_URL, timeout=TIMEOUT)
        if r.status_code != 200:
            logger.warning("NHL standings fetch returned %d", r.status_code)
            return []
        data = r.json()
        # `standings` is a flat array of team rows.
        rows = data.get("standings") or []
        codes: list = []
        for row in rows:
            abbrev = (row.get("teamAbbrev") or {}).get("default") if isinstance(row.get("teamAbbrev"), dict) else row.get("teamAbbrev")
            if abbrev:
                codes.append(abbrev)
        return codes
    except Exception as e:
        logger.warning("NHL standings fetch failed: %s", e)
        return []


async def _fetch_team_roster(http: httpx.AsyncClient, team_code: str) -> Optional[list]:
    """Returns a flat list of player dicts (forwards + defensemen +
    goalies merged) for a single NHL team. Returns None on hard
    failure (network error, non-200) so callers can distinguish
    "team has a roster of length 0" (impossible) from "the request
    failed" (likely outage)."""
    try:
        r = await http.get(NHL_ROSTER_URL.format(team=team_code), timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        body = r.json()
        out: list = []
        for section in ("forwards", "defensemen", "goalies"):
            for p in (body.get(section) or []):
                normalized = _normalize_player_dict(p)
                if normalized:
                    normalized["team_code"] = team_code
                    out.append(normalized)
        return out
    except Exception as e:
        logger.debug("NHL roster fetch %s failed: %s", team_code, e)
        return None


async def sync_once(
    db,
    *,
    create_notification: Optional[Callable[..., Awaitable]] = None,
    concurrency: int = 8,
) -> dict:
    """Single pass: fetch all NHL rosters, build {nhl_id → team_code} map,
    diff against `players` collection, route diffs through the
    dispatcher. Returns a summary dict for the log line + tests."""
    counts = {
        "teams_fetched": 0,
        "nhl_players_seen": 0,
        "team_changes": 0,
        "notifications_sent": 0,
    }
    summary_transitions: dict = {}

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as http:
        team_codes = await _fetch_team_codes(http)
        if not team_codes:
            return counts
        sem = asyncio.Semaphore(concurrency)
        roster_lookup: Dict[int, str] = {}
        successful_team_count = 0

        async def _gather(team_code: str):
            nonlocal successful_team_count
            async with sem:
                roster = await _fetch_team_roster(http, team_code)
                if roster is None:
                    return  # Hard failure — don't count this team.
                successful_team_count += 1
                for entry in roster:
                    roster_lookup[entry["nhl_id"]] = team_code

        await asyncio.gather(*[_gather(t) for t in team_codes], return_exceptions=True)
        counts["teams_fetched"] = successful_team_count
        counts["nhl_players_seen"] = len(roster_lookup)

    # No-op safety: if NO team responded successfully, treat the entire
    # sync as a failure and bail out — never mark every NHL player as
    # AHL because of a transient outage. We require >=50% of teams to
    # have responded to proceed.
    if successful_team_count < max(1, len(team_codes) // 2):
        logger.warning(
            "nhl_roster_sync: only %d/%d teams responded — bailing",
            successful_team_count, len(team_codes),
        )
        return counts

    # Iter 230e — Only diff players we already track AND that have a real
    # nhl_id; never invent rows here.
    from services.nhl_sync_dispatcher import apply_player_diff_and_notify

    diff_count = 0
    notifications_sent = 0
    async for player in db.players.find(
        {"nhl_id": {"$exists": True, "$ne": None, "$gt": 0}},
        {"_id": 1, "nhl_id": 1, "current_team_abbrev": 1, "league_status": 1},
    ):
        try:
            nhl_id = int(player["nhl_id"])
        except Exception:
            continue
        observed_team = roster_lookup.get(nhl_id)
        prev_team = player.get("current_team_abbrev")
        prev_league = (player.get("league_status") or "").upper()

        # Determine the new league_status:
        #   present in any NHL roster → "NHL"
        #   absent + currently "NHL"  → "AHL" (sent down)
        #   absent + already "AHL"    → no-op (nothing changed)
        if observed_team:
            new_league = "NHL"
            new_team = observed_team
        else:
            if prev_league == "NHL":
                new_league = "AHL"
                new_team = prev_team  # Keep last-known team for context.
            else:
                continue  # No transition to record.

        new_fields: dict = {}
        if new_team and new_team != prev_team:
            new_fields["current_team_abbrev"] = new_team
        if new_league != prev_league:
            new_fields["league_status"] = new_league
        if not new_fields:
            continue

        diff_count += 1
        summary = await apply_player_diff_and_notify(
            db,
            player_id=str(player["_id"]),
            new_fields=new_fields,
            create_notification=create_notification,
        )
        notifications_sent += int(summary.get("notifications_sent", 0))
        for t in (summary.get("transitions") or []):
            summary_transitions[t] = summary_transitions.get(t, 0) + 1

    counts["team_changes"] = diff_count
    counts["notifications_sent"] = notifications_sent
    counts["transitions"] = summary_transitions
    logger.info("nhl_roster_sync: %s", counts)
    return counts


async def nhl_roster_sync_loop(
    db,
    create_notification: Callable[..., Awaitable],
    interval_sec: int = DEFAULT_INTERVAL_SEC,
):
    """Run sync_once forever on the given interval. Defers the first
    pass by 90s so the rest of the app boots cleanly first."""
    logger.info("NHL roster sync worker started (interval=%ds)", interval_sec)
    await asyncio.sleep(90)
    while True:
        try:
            await sync_once(db, create_notification=create_notification)
        except asyncio.CancelledError:
            logger.info("nhl_roster_sync loop cancelled")
            raise
        except Exception as e:
            logger.exception("nhl_roster_sync iteration failed: %s", e)
            await asyncio.sleep(300)
            continue
        await asyncio.sleep(interval_sec)

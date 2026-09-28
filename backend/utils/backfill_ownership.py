"""Evidence-based ownership & lineup backfill engine.

Reconstructs `player_ownership_periods` and `lineup_status_periods` from
verifiable transaction records — executed trades, activity-feed events, and
roster-change-log entries.

Design principles:
  • Evidence-based: every period carries an `evidence` tag indicating the
    source. Periods are never invented from thin air.
  • Idempotent: safe to re-run. Clears existing backfilled records (those
    with `backfilled: True`) before writing, leaving manually-created
    records untouched.
  • Honest about gaps: if a player is on the current roster but has no
    recorded acquisition event, the period is tagged
    `evidence: "inferred_baseline"` so downstream can treat it
    differently from verified data.

Usage:
    from utils.backfill_ownership import backfill_league_ownership
    result = await backfill_league_ownership(db, league_id)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

logger = logging.getLogger("backfill_ownership")


# ──────────────────────────────────────────────────────────────────
# Event extraction — collect evidence from all available sources
# ──────────────────────────────────────────────────────────────────

async def _extract_trade_events(db, league_id: str) -> list[dict]:
    """Extract player movements from executed trades.

    Each executed trade has an `execution_moves` array with:
      {player_id, from (team_id), to (team_id), from_name, to_name}
    The trade's `processed_at` is the timestamp.

    For two-party trades without `execution_moves`, we reconstruct
    from `assets_offered` / `assets_requested`.
    """
    events = []
    cursor = db.trades.find(
        {"league_id": league_id, "status": "executed"},
        {"execution_moves": 1, "assets_offered": 1, "assets_requested": 1,
         "proposer_team_id": 1, "target_team_id": 1,
         "processed_at": 1, "executed_at": 1, "submitted_at": 1,
         "is_multi_party": 1, "parties": 1},
    )
    async for trade in cursor:
        # Determine timestamp: prefer processed_at, then executed_at, then submitted_at
        ts = _parse_timestamp(
            trade.get("processed_at")
            or trade.get("executed_at")
            or trade.get("submitted_at")
        )
        if not ts:
            continue

        moves = trade.get("execution_moves") or []
        if isinstance(moves, list) and moves:
            for m in moves:
                if not isinstance(m, dict):
                    continue
                pid = m.get("player_id")
                from_team = m.get("from")
                to_team = m.get("to")
                if pid and from_team and to_team:
                    events.append({
                        "player_id": pid,
                        "from_team": from_team,
                        "to_team": to_team,
                        "timestamp": ts,
                        "source": "trade",
                        "evidence": "trade",
                        "trade_id": str(trade["_id"]),
                    })
        elif isinstance(moves, list) and not moves:
            # No moves list — try to reconstruct from assets or parties
            parties = trade.get("parties") or []
            if parties and isinstance(parties, list):
                # Multi-party trade with parties array
                for party in parties:
                    if not isinstance(party, dict):
                        continue
                    party_tid = party.get("team_id")
                    for a in (party.get("sends") or []):
                        pid = a.get("player_id") if isinstance(a, dict) else None
                        dest = a.get("to_team_id") if isinstance(a, dict) else None
                        if pid and party_tid and dest:
                            events.append({
                                "player_id": pid,
                                "from_team": party_tid,
                                "to_team": dest,
                                "timestamp": ts,
                                "source": "trade",
                                "evidence": "trade",
                                "trade_id": str(trade["_id"]),
                            })
            else:
                # Two-party trade: reconstruct from assets
                proposer = trade.get("proposer_team_id")
                target = trade.get("target_team_id")
                if proposer and target:
                    for a in (trade.get("assets_offered") or []):
                        pid = a.get("player_id") if isinstance(a, dict) else None
                        if pid:
                            events.append({
                                "player_id": pid,
                                "from_team": proposer,
                                "to_team": target,
                                "timestamp": ts,
                                "source": "trade",
                                "evidence": "trade",
                                "trade_id": str(trade["_id"]),
                            })
                    for a in (trade.get("assets_requested") or []):
                        pid = a.get("player_id") if isinstance(a, dict) else None
                        if pid:
                            events.append({
                                "player_id": pid,
                                "from_team": target,
                                "to_team": proposer,
                                "timestamp": ts,
                                "source": "trade",
                                "evidence": "trade",
                                "trade_id": str(trade["_id"]),
                            })

    return events


async def _extract_activity_events(db, league_id: str) -> list[dict]:
    """Extract roster add/drop events from the activity feed."""
    events = []
    cursor = db.activity_feed.find(
        {"league_id": league_id, "event_type": {"$in": ["roster_add", "roster_drop"]}},
        {"event_type": 1, "metadata": 1, "created_at": 1},
    )
    async for doc in cursor:
        meta = doc.get("metadata") or {}
        pid = meta.get("player_id")
        tid = meta.get("team_id")
        ts = _parse_timestamp(doc.get("created_at"))
        if not (pid and tid and ts):
            continue
        evt_type = doc["event_type"]
        if evt_type == "roster_add":
            events.append({
                "player_id": pid,
                "to_team": tid,
                "from_team": None,
                "timestamp": ts,
                "source": "add",
                "evidence": "activity_feed",
            })
        elif evt_type == "roster_drop":
            events.append({
                "player_id": pid,
                "from_team": tid,
                "to_team": None,
                "timestamp": ts,
                "source": "drop",
                "evidence": "activity_feed",
            })
    return events


async def _extract_roster_change_log_events(db, league_id: str) -> list[dict]:
    """Extract events from the roster_change_log collection."""
    events = []
    cursor = db.roster_change_log.find(
        {"league_id": league_id},
        {"player_id": 1, "team_id": 1, "action": 1, "source": 1, "timestamp": 1},
    )
    async for doc in cursor:
        pid = doc.get("player_id")
        tid = doc.get("team_id")
        ts = _parse_timestamp(doc.get("timestamp"))
        action = doc.get("action")
        if not (pid and tid and ts and action):
            continue
        if action == "add":
            events.append({
                "player_id": pid,
                "to_team": tid,
                "from_team": None,
                "timestamp": ts,
                "source": doc.get("source", "add"),
                "evidence": "roster_change_log",
            })
        elif action == "remove":
            events.append({
                "player_id": pid,
                "from_team": tid,
                "to_team": None,
                "timestamp": ts,
                "source": doc.get("source", "drop"),
                "evidence": "roster_change_log",
            })
    return events


# ──────────────────────────────────────────────────────────────────
# Period reconstruction
# ──────────────────────────────────────────────────────────────────

def _build_ownership_periods(
    events: list[dict],
    current_rosters: dict[str, list[str]],
    league_start: Optional[datetime],
) -> list[dict]:
    """Build ownership periods from chronologically-sorted events.

    Returns a list of period dicts ready for insertion into
    `player_ownership_periods`.

    Algorithm:
      1. Group events by player_id, sort by timestamp.
      2. Walk events and build ownership spans:
         - "add/trade-in" → open a new span (acquired_at = event time)
         - "drop/trade-out" → close the open span (released_at = event time)
      3. For players on a current roster with no events at all, create
         an "inferred_baseline" period starting at league_start (if known)
         or marked as unknown.
      4. Deduplicate: if the same (player, team, acquired_at) appears
         multiple times, keep only one.
    """
    from collections import defaultdict

    # Group events per player
    player_events: dict[str, list[dict]] = defaultdict(list)
    for evt in events:
        pid = evt["player_id"]
        player_events[pid].append(evt)

    # Sort each player's events by timestamp
    for pid in player_events:
        player_events[pid].sort(key=lambda e: e["timestamp"])

    periods: list[dict] = []
    seen_players: set[str] = set()

    for pid, evts in player_events.items():
        seen_players.add(pid)
        # Track open spans per team
        open_spans: dict[str, dict] = {}

        for evt in evts:
            ts = evt["timestamp"]
            from_team = evt.get("from_team")
            to_team = evt.get("to_team")
            evidence = evt.get("evidence", "unknown")
            source = evt.get("source", "unknown")

            # Close span on the from_team (if any)
            if from_team and from_team in open_spans:
                span = open_spans.pop(from_team)
                span["released_at"] = ts
                span["release_source"] = source
                periods.append(span)
            elif from_team:
                # No open span to close — this means we have evidence of
                # departure but no recorded arrival. Create a span with
                # unknown start.
                periods.append({
                    "player_id": pid,
                    "team_id": from_team,
                    "acquired_at": league_start or ts,
                    "released_at": ts,
                    "source": "unknown",
                    "release_source": source,
                    "evidence": "inferred_pre_history" if league_start else "unknown",
                    "backfilled": True,
                })

            # Open span on the to_team (if any)
            if to_team:
                # Close any existing open span for this team first
                # (shouldn't happen normally, but handles data quirks)
                if to_team in open_spans:
                    old = open_spans.pop(to_team)
                    old["released_at"] = ts
                    old["release_source"] = "data_correction"
                    periods.append(old)
                open_spans[to_team] = {
                    "player_id": pid,
                    "team_id": to_team,
                    "acquired_at": ts,
                    "released_at": None,
                    "source": source,
                    "release_source": None,
                    "evidence": evidence,
                    "backfilled": True,
                }

        # Flush remaining open spans
        for team_id, span in open_spans.items():
            # Check if the player is actually still on this team
            team_roster = current_rosters.get(team_id, [])
            if pid in team_roster:
                span["released_at"] = None  # still owned
            else:
                # Player left but we have no evidence of when. The span
                # stays open-ended. Downstream allocation will still
                # only credit games during verified intervals.
                # Actually, if the player is NOT on the roster, they must
                # have left at some point. Mark as unknown end.
                span["released_at"] = None
                span["evidence"] = span.get("evidence", "unknown")
                span["_note"] = "player_not_on_current_roster_but_no_release_event"
            periods.append(span)

    # Handle players on current rosters with NO events at all
    for team_id, roster in current_rosters.items():
        for pid in roster:
            if pid in seen_players:
                continue
            # This player is on the roster but has no transaction history.
            # Create an inferred baseline period.
            periods.append({
                "player_id": pid,
                "team_id": team_id,
                "acquired_at": league_start or datetime(2026, 1, 1, tzinfo=timezone.utc),
                "released_at": None,
                "source": "inferred",
                "release_source": None,
                "evidence": "inferred_baseline",
                "backfilled": True,
            })

    return periods


def _build_lineup_periods(
    current_lineups: dict[str, dict],
    current_rosters: dict[str, list[str]],
    baseline_time: datetime,
    league_id: str,
) -> list[dict]:
    """Build lineup_status_periods from current team.lineup state.

    We only know the CURRENT lineup position. We create a single period
    per player starting at `baseline_time` (typically now) with
    `evidence: "current_state"`. This honestly reflects that we don't
    know historical lineup positions.

    Players on a roster but not in the lineup dict default to "bench"
    (the most conservative assumption — they don't score).
    """
    from utils.scoring_roster import ACTIVE_SECTIONS

    periods = []
    for team_id, lineup in current_lineups.items():
        roster = current_rosters.get(team_id, [])
        seen_pids: set = set()

        for pid, info in lineup.items():
            if pid not in roster:
                continue
            seen_pids.add(pid)
            if isinstance(info, dict):
                section = (info.get("section") or "bench").lower()
            else:
                section = "bench"
            # Map section names to our canonical positions
            position = _section_to_position(section)
            periods.append({
                "player_id": pid,
                "team_id": team_id,
                "league_id": league_id,
                "position": position,
                "started_at": baseline_time,
                "ended_at": None,
                "evidence": "current_state",
                "backfilled": True,
            })

        # Players on roster but not in lineup → bench (conservative)
        for pid in roster:
            if pid in seen_pids:
                continue
            periods.append({
                "player_id": pid,
                "team_id": team_id,
                "league_id": league_id,
                "position": "bench",
                "started_at": baseline_time,
                "ended_at": None,
                "evidence": "current_state_default",
                "backfilled": True,
            })

    return periods


def _section_to_position(section: str) -> str:
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
# Main backfill entry point
# ──────────────────────────────────────────────────────────────────

async def backfill_league_ownership(
    db,
    league_id: str,
    *,
    dry_run: bool = False,
) -> dict:
    """Reconstruct ownership and lineup periods for a league from
    evidence in trades, activity feed, and roster change log.

    Args:
        db: Motor database instance
        league_id: The league to backfill
        dry_run: If True, compute periods but don't write to DB

    Returns:
        Summary dict with counts and any warnings.
    """
    logger.info("Starting ownership backfill for league %s (dry_run=%s)", league_id, dry_run)

    # Load league metadata
    league = await db.leagues.find_one(
        {"_id": ObjectId(league_id)},
        {"season_start_date": 1, "created_at": 1, "name": 1},
    )
    if not league:
        return {"error": f"League {league_id} not found"}

    league_start = _resolve_league_start(league)

    # Load current rosters and lineups
    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "roster": 1, "lineup": 1, "name": 1},
    ).to_list(200)

    current_rosters: dict[str, list[str]] = {}
    current_lineups: dict[str, dict] = {}
    for t in teams:
        tid = str(t["_id"])
        current_rosters[tid] = [str(p) for p in (t.get("roster") or [])]
        current_lineups[tid] = t.get("lineup") or {}

    # Collect evidence from all sources
    trade_events = await _extract_trade_events(db, league_id)
    activity_events = await _extract_activity_events(db, league_id)
    rcl_events = await _extract_roster_change_log_events(db, league_id)

    # Merge and deduplicate events
    all_events = _deduplicate_events(trade_events + activity_events + rcl_events)
    all_events.sort(key=lambda e: e["timestamp"])

    # Build ownership periods
    ownership_periods = _build_ownership_periods(all_events, current_rosters, league_start)

    # Add league_id to all periods
    for p in ownership_periods:
        p["league_id"] = league_id

    # Build lineup periods from current state
    now = datetime.now(timezone.utc)
    lineup_periods = _build_lineup_periods(
        current_lineups, current_rosters, now, league_id,
    )

    # Compute stats
    evidence_counts: dict[str, int] = {}
    for p in ownership_periods:
        ev = p.get("evidence", "unknown")
        evidence_counts[ev] = evidence_counts.get(ev, 0) + 1

    result = {
        "league_id": league_id,
        "league_name": league.get("name"),
        "league_start": league_start.isoformat() if league_start else None,
        "events_found": len(all_events),
        "events_by_source": {
            "trade": len(trade_events),
            "activity_feed": len(activity_events),
            "roster_change_log": len(rcl_events),
        },
        "ownership_periods_created": len(ownership_periods),
        "lineup_periods_created": len(lineup_periods),
        "evidence_breakdown": evidence_counts,
        "teams_processed": len(teams),
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    # Write to database — clear previous backfilled records first
    await db.player_ownership_periods.delete_many({
        "league_id": league_id,
        "backfilled": True,
    })
    await db.lineup_status_periods.delete_many({
        "league_id": league_id,
        "backfilled": True,
    })

    if ownership_periods:
        await db.player_ownership_periods.insert_many(ownership_periods)
    if lineup_periods:
        await db.lineup_status_periods.insert_many(lineup_periods)

    # Mark that this league has been backfilled
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "ownership_backfilled_at": now,
            "ownership_backfill_evidence": evidence_counts,
        }},
    )

    logger.info(
        "Backfill complete for league %s: %d ownership, %d lineup periods",
        league_id, len(ownership_periods), len(lineup_periods),
    )
    return result


async def backfill_all_leagues(db, *, dry_run: bool = False) -> list[dict]:
    """Run backfill for every league in the database."""
    leagues = await db.leagues.find({}, {"_id": 1}).to_list(200)
    results = []
    for lg in leagues:
        lid = str(lg["_id"])
        result = await backfill_league_ownership(db, lid, dry_run=dry_run)
        results.append(result)
    return results


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _parse_timestamp(val) -> Optional[datetime]:
    """Parse various timestamp formats into a UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    try:
        s = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _resolve_league_start(league: dict) -> Optional[datetime]:
    """Get the league's season start as a datetime, or None."""
    ssd = league.get("season_start_date")
    if ssd:
        ts = _parse_timestamp(ssd)
        if ts:
            return ts
    created = league.get("created_at")
    if created:
        return _parse_timestamp(created)
    return None


def _deduplicate_events(events: list[dict]) -> list[dict]:
    """Remove duplicate events (same player, same direction, same time).

    Prefers trade evidence > roster_change_log > activity_feed.
    """
    EVIDENCE_PRIORITY = {
        "trade": 0,
        "roster_change_log": 1,
        "activity_feed": 2,
        "unknown": 3,
    }
    seen: dict[tuple, dict] = {}
    for evt in events:
        key = (
            evt["player_id"],
            evt.get("from_team"),
            evt.get("to_team"),
            evt["timestamp"].isoformat() if evt.get("timestamp") else "",
        )
        existing = seen.get(key)
        if existing:
            # Keep the one with higher priority evidence
            old_pri = EVIDENCE_PRIORITY.get(existing.get("evidence", ""), 99)
            new_pri = EVIDENCE_PRIORITY.get(evt.get("evidence", ""), 99)
            if new_pri < old_pri:
                seen[key] = evt
        else:
            seen[key] = evt
    return list(seen.values())

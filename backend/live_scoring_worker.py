"""Live NHL playoff/regular-season scoring worker.

Periodically polls nhlpy for today's games. For any LIVE / OFF / CRIT game, it
pulls the boxscore and updates per-player cumulative stats in the `players`
collection, plus records per-team fantasy point deltas in `live_scoring`.
Fires Socket.IO `live_scoring_update` events to all connected clients.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

logger = logging.getLogger("live_scoring")

POLL_INTERVAL_SEC = 60
ACTIVE_GAME_STATES = {"LIVE", "CRIT", "OFF", "FINAL"}


def _toi_to_minutes(toi: Optional[str]) -> float:
    if not toi or not isinstance(toi, str):
        return 0.0
    try:
        m, s = toi.split(":")
        return float(m) + float(s) / 60.0
    except Exception:
        return 0.0


def _flatten_boxscore(bx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert an NHL boxscore into a flat list of player stat dicts."""
    out: List[Dict[str, Any]] = []
    ps = bx.get("playerByGameStats") or {}
    for side in ("homeTeam", "awayTeam"):
        team = ps.get(side, {}) or {}
        team_abbrev = (bx.get(side.replace("Team", "Team"), {}) or {}).get("abbrev")
        for bucket in ("forwards", "defense"):
            for p in team.get(bucket, []) or []:
                out.append({
                    "nhl_id": p.get("playerId"),
                    "name": (p.get("name") or {}).get("default"),
                    "team_abbrev": team_abbrev,
                    "is_goalie": False,
                    "goals": int(p.get("goals", 0) or 0),
                    "assists": int(p.get("assists", 0) or 0),
                    "shots": int(p.get("sog", 0) or 0),
                    "plus_minus": int(p.get("plusMinus", 0) or 0),
                    "penalty_minutes": int(p.get("pim", 0) or 0),
                    "hits": int(p.get("hits", 0) or 0),
                    "blocked_shots": int(p.get("blockedShots", 0) or 0),
                    "toi": _toi_to_minutes(p.get("toi")),
                    "power_play_goals": int(p.get("powerPlayGoals", 0) or 0),
                    "short_handed_goals": int(p.get("shorthandedGoals", 0) or 0),
                })
        for g in team.get("goalies", []) or []:
            saves = int(g.get("saves", 0) or 0)
            sa = int(g.get("shotsAgainst", 0) or 0)
            out.append({
                "nhl_id": g.get("playerId"),
                "name": (g.get("name") or {}).get("default"),
                "team_abbrev": team_abbrev,
                "is_goalie": True,
                "saves": saves,
                "goals_against": max(0, sa - saves),
                "decision": g.get("decision"),  # W/L/O
                "wins": 1 if g.get("decision") == "W" else 0,
                "losses": 1 if g.get("decision") == "L" else 0,
                "overtime_losses": 1 if g.get("decision") == "O" else 0,
                "shutouts": 1 if (g.get("decision") == "W" and sa - saves == 0) else 0,
                "toi": _toi_to_minutes(g.get("toi")),
            })
    return out


async def _apply_player_updates(db, game_id: int, gm_type: int, game_state: str,
                                players: List[Dict[str, Any]]):
    """Upsert live stat deltas into the `players` collection (keyed by nhl_id).

    We write to a `live_stats` sub-document keyed by game_id so repeated polls
    for the same game overwrite cleanly (idempotent). An aggregated
    `playoff_totals` field sums all playoff games for quick fantasy scoring.
    """
    now = datetime.now(timezone.utc)
    is_playoff = gm_type == 3

    for p in players:
        if not p.get("nhl_id"):
            continue
        key = f"live_stats.{game_id}"
        update = {
            "$set": {
                key: {
                    **{k: v for k, v in p.items() if k not in ("nhl_id",)},
                    "game_id": game_id,
                    "game_state": game_state,
                    "game_type": gm_type,
                    "is_playoff": is_playoff,
                    "updated_at": now,
                },
                "live_updated_at": now,
            }
        }
        await db.players.update_one({"nhl_id": p["nhl_id"]}, update)


def _fantasy_points_from_live(live: Dict[str, Any], is_goalie: bool) -> float:
    """Use the Dynasty Dreams default scoring weights against live deltas."""
    if is_goalie:
        return round(
            (live.get("wins", 0) or 0) * 5
            + (live.get("losses", 0) or 0) * -2
            + (live.get("saves", 0) or 0) * 0.2
            + (live.get("goals_against", 0) or 0) * -1
            + (live.get("shutouts", 0) or 0) * 3,
            2,
        )
    return round(
        (live.get("goals", 0) or 0) * 3
        + (live.get("assists", 0) or 0) * 2
        + (live.get("plus_minus", 0) or 0) * 1
        + (live.get("penalty_minutes", 0) or 0) * -0.5
        + (live.get("power_play_goals", 0) or 0) * 1
        + (live.get("short_handed_goals", 0) or 0) * 2
        + (live.get("shots", 0) or 0) * 0.5,
        2,
    )


async def _recompute_team_live_totals(db):
    """Aggregate each team's live playoff points and store on `teams.live_points`."""
    all_players = await db.players.find(
        {"live_stats": {"$exists": True}},
        {"_id": 1, "nhl_id": 1, "player_type": 1, "position": 1, "live_stats": 1},
    ).to_list(10000)

    # Compute per-player cumulative live fpts
    player_fpts: Dict[str, float] = {}
    for p in all_players:
        is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
        total = 0.0
        for _gid, live in (p.get("live_stats") or {}).items():
            total += _fantasy_points_from_live(live, is_g)
        player_fpts[str(p["_id"])] = round(total, 2)

    # Walk teams and sum
    teams = await db.teams.find({}, {"_id": 1, "league_id": 1, "roster": 1, "name": 1}).to_list(1000)
    team_deltas = []
    for t in teams:
        fpts = round(sum(player_fpts.get(pid, 0.0) for pid in (t.get("roster") or [])), 2)
        await db.teams.update_one({"_id": t["_id"]}, {"$set": {"live_points": fpts}})
        team_deltas.append({
            "team_id": str(t["_id"]),
            "team_name": t["name"],
            "league_id": t["league_id"],
            "live_points": fpts,
        })
    return team_deltas


async def run_once(db, sio=None):
    """Single poll cycle. Returns summary dict for logs/WebSocket broadcast."""
    try:
        from nhlpy import NHLClient
    except Exception as e:
        logger.warning("nhlpy not available: %s", e)
        return {"error": "nhlpy missing"}

    client = NHLClient()
    try:
        sched = client.schedule.daily_schedule()
    except Exception as e:
        logger.warning("schedule fetch failed: %s", e)
        return {"error": str(e)}

    games = sched.get("games", []) or []
    today = sched.get("date")
    active_games = [g for g in games if g.get("gameState") in ACTIVE_GAME_STATES]

    # Fallback: if no active games today, look at the previous day so the worker has
    # something meaningful to display during the demo window (offseason / day-off).
    if not active_games and sched.get("previousStartDate"):
        try:
            prev = client.schedule.daily_schedule(date=sched["previousStartDate"])
            games = prev.get("games", []) or []
            today = prev.get("date")
            active_games = [g for g in games if g.get("gameState") in ACTIVE_GAME_STATES]
        except Exception:
            pass

    summary = {
        "date": today,
        "polled_at": datetime.now(timezone.utc).isoformat(),
        "games_processed": 0,
        "players_updated": 0,
        "playoff_games": 0,
        "games": [],
    }

    for g in active_games:
        gid = g.get("id")
        gtype = g.get("gameType")
        gstate = g.get("gameState")
        try:
            bx = client.game_center.boxscore(game_id=gid)
        except Exception as e:
            logger.debug("boxscore failed %s: %s", gid, e)
            continue

        players = _flatten_boxscore(bx)
        await _apply_player_updates(db, gid, gtype, gstate, players)
        summary["games_processed"] += 1
        summary["players_updated"] += len(players)
        if gtype == 3:
            summary["playoff_games"] += 1
        summary["games"].append({
            "id": gid,
            "state": gstate,
            "type": gtype,
            "is_playoff": gtype == 3,
            "away": g.get("awayTeam", {}).get("abbrev"),
            "home": g.get("homeTeam", {}).get("abbrev"),
            "away_score": (bx.get("awayTeam", {}) or {}).get("score"),
            "home_score": (bx.get("homeTeam", {}) or {}).get("score"),
        })

    team_totals = await _recompute_team_live_totals(db)
    summary["team_totals_updated"] = len(team_totals)

    # Cache the latest summary for the read API
    await db.system_state.update_one(
        {"_id": "live_scoring"},
        {"$set": {"latest": summary, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    if sio is not None:
        try:
            await sio.emit("live_scoring_update", summary)
        except Exception as e:
            logger.debug("sio emit failed: %s", e)

    return summary


async def live_scoring_loop(db, sio=None, interval_sec: int = POLL_INTERVAL_SEC):
    logger.info("Live scoring worker started (interval=%ss)", interval_sec)
    while True:
        try:
            summary = await run_once(db, sio)
            logger.info(
                "Live poll: %s games (%s playoff) / %s players, %s team totals",
                summary.get("games_processed", 0),
                summary.get("playoff_games", 0),
                summary.get("players_updated", 0),
                summary.get("team_totals_updated", 0),
            )
        except asyncio.CancelledError:
            logger.info("Live scoring worker cancelled")
            raise
        except Exception as e:
            logger.exception("Live scoring poll failed: %s", e)
        await asyncio.sleep(interval_sec)

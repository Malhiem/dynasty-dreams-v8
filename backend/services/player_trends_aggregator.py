"""Iter 232N.7 — Cross-league player trend aggregator.

Runs nightly. For every player_id that shows up in any add/drop/trade
event in the last N days across ALL leagues, computes a summary snapshot
and upserts into `player_trends`. Fantasy managers see this snapshot as
a compact "trending" badge next to player names + a dedicated "League
Movers" widget.

Signals aggregated (last 7 days):
  • adds  — count of `roster_add` activity events + won waiver_claims
  • drops — count of `roster_drop` activity events
  • trades — count of executed trades this player appears in
             (assets_offered/requested for two-party; parties.sends/
              receives for multi-party)

Snapshot schema (`player_trends` collection):
    {
        _id: ObjectId,
        player_id: str,                   # dedup key
        adds_7d: int,
        drops_7d: int,
        trades_7d: int,
        total_events_7d: int,
        # Number of DISTINCT leagues each signal fired in — critical
        # for filtering out noise from bot-driven test leagues.
        leagues_adds_7d: int,
        leagues_drops_7d: int,
        leagues_trades_7d: int,
        distinct_leagues_7d: int,
        # Derived label the frontend uses for the badge.
        trend: "hot" | "dropped" | "traded" | None,
        # Snapshot bookkeeping.
        computed_at: ISO str,
        window_days: 7,
    }

Trend label rules (kept simple and legible; tuned to real dynasty
volume, not one-off league scale):
    • "hot"     — adds_7d ≥ 3   AND  leagues_adds_7d ≥ 2
    • "dropped" — drops_7d ≥ 3  AND  leagues_drops_7d ≥ 2
    • "traded"  — trades_7d ≥ 2 AND  leagues_trades_7d ≥ 2
    Multiple qualifying signals → the one with the highest count wins;
    ties break in the order (hot > dropped > traded) since hot is the
    highest-utility signal for waiver decisions.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 24 * 60 * 60  # nightly
WINDOW_DAYS = 7


def _derive_trend(adds: int, drops: int, trades: int,
                  leagues_adds: int, leagues_drops: int,
                  leagues_trades: int) -> Optional[str]:
    """Pick the strongest qualifying label. Requires signal to be
    present in >= 2 distinct leagues so single-league noise never
    triggers a badge for the wider dynasty audience."""
    candidates: list[tuple[str, int]] = []
    if adds >= 3 and leagues_adds >= 2:
        candidates.append(("hot", adds))
    if drops >= 3 and leagues_drops >= 2:
        candidates.append(("dropped", drops))
    if trades >= 2 and leagues_trades >= 2:
        candidates.append(("traded", trades))
    if not candidates:
        return None
    priority = {"hot": 3, "dropped": 2, "traded": 1}
    candidates.sort(key=lambda c: (c[1], priority[c[0]]), reverse=True)
    return candidates[0][0]


async def aggregate_player_trends_once(db, window_days: int = WINDOW_DAYS) -> dict:
    """Single pass. Returns counts dict for observability + tests."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cutoff_iso = cutoff.isoformat()

    # ─── adds via activity ('roster_add') ───────────────────────────
    adds_by_pid: dict[str, int] = {}
    adds_leagues: dict[str, set[str]] = {}
    async for a in db.activity.find(
        {"event_type": "roster_add", "created_at": {"$gte": cutoff}},
        {"metadata.player_id": 1, "league_id": 1},
    ):
        pid = (a.get("metadata") or {}).get("player_id")
        if not pid:
            continue
        adds_by_pid[pid] = adds_by_pid.get(pid, 0) + 1
        adds_leagues.setdefault(pid, set()).add(str(a.get("league_id") or ""))

    # ─── adds via won waiver claims ─────────────────────────────────
    async for w in db.waiver_claims.find(
        {"status": "won", "processed_at": {"$gte": cutoff}},
        {"player_id": 1, "league_id": 1},
    ):
        pid = w.get("player_id")
        if not pid:
            continue
        adds_by_pid[pid] = adds_by_pid.get(pid, 0) + 1
        adds_leagues.setdefault(pid, set()).add(str(w.get("league_id") or ""))

    # ─── drops via activity ('roster_drop') ─────────────────────────
    drops_by_pid: dict[str, int] = {}
    drops_leagues: dict[str, set[str]] = {}
    async for a in db.activity.find(
        {"event_type": "roster_drop", "created_at": {"$gte": cutoff}},
        {"metadata.player_id": 1, "league_id": 1},
    ):
        pid = (a.get("metadata") or {}).get("player_id")
        if not pid:
            continue
        drops_by_pid[pid] = drops_by_pid.get(pid, 0) + 1
        drops_leagues.setdefault(pid, set()).add(str(a.get("league_id") or ""))

    # ─── trades via executed trades (two-party + multi-party) ───────
    trades_by_pid: dict[str, int] = {}
    trades_leagues: dict[str, set[str]] = {}
    async for t in db.trades.find(
        {"status": "executed", "processes_at": {"$gte": cutoff_iso}},
        {
            "assets_offered": 1, "assets_requested": 1,
            "parties": 1, "league_id": 1, "is_multi_party": 1,
        },
    ):
        league_id = str(t.get("league_id") or "")
        pids: set[str] = set()
        if t.get("is_multi_party") and t.get("parties"):
            for party in t.get("parties") or []:
                for asset in (party.get("sends") or []) + (party.get("receives") or []):
                    if asset.get("asset_type") == "player" and asset.get("player_id"):
                        pids.add(asset["player_id"])
        else:
            for asset in (t.get("assets_offered") or []) + (t.get("assets_requested") or []):
                if asset.get("asset_type") == "player" and asset.get("player_id"):
                    pids.add(asset["player_id"])
        for pid in pids:
            trades_by_pid[pid] = trades_by_pid.get(pid, 0) + 1
            trades_leagues.setdefault(pid, set()).add(league_id)

    # ─── Merge → upsert ─────────────────────────────────────────────
    all_pids = set(adds_by_pid) | set(drops_by_pid) | set(trades_by_pid)
    now_iso = datetime.now(timezone.utc).isoformat()
    upserted = 0
    for pid in all_pids:
        adds = adds_by_pid.get(pid, 0)
        drops = drops_by_pid.get(pid, 0)
        trades = trades_by_pid.get(pid, 0)
        l_adds = len(adds_leagues.get(pid) or set())
        l_drops = len(drops_leagues.get(pid) or set())
        l_trades = len(trades_leagues.get(pid) or set())
        distinct_leagues = len(
            (adds_leagues.get(pid) or set())
            | (drops_leagues.get(pid) or set())
            | (trades_leagues.get(pid) or set())
        )
        trend = _derive_trend(adds, drops, trades, l_adds, l_drops, l_trades)
        await db.player_trends.update_one(
            {"player_id": pid},
            {"$set": {
                "player_id": pid,
                "adds_7d": adds,
                "drops_7d": drops,
                "trades_7d": trades,
                "total_events_7d": adds + drops + trades,
                "leagues_adds_7d": l_adds,
                "leagues_drops_7d": l_drops,
                "leagues_trades_7d": l_trades,
                "distinct_leagues_7d": distinct_leagues,
                "trend": trend,
                "computed_at": now_iso,
                "window_days": window_days,
            }},
            upsert=True,
        )
        upserted += 1

    # ─── Zero-out stale snapshots outside the window ────────────────
    # If a player had a trend last week but no events this week, mark
    # their trend=None so the badge disappears. Keep the row for
    # historical scrubbing but zero the counts.
    zeroed = await db.player_trends.update_many(
        {"player_id": {"$nin": list(all_pids)}, "trend": {"$ne": None}},
        {"$set": {
            "adds_7d": 0, "drops_7d": 0, "trades_7d": 0,
            "total_events_7d": 0,
            "leagues_adds_7d": 0, "leagues_drops_7d": 0, "leagues_trades_7d": 0,
            "distinct_leagues_7d": 0,
            "trend": None,
            "computed_at": now_iso,
        }},
    )

    result = {
        "upserted": upserted,
        "zeroed": zeroed.modified_count,
        "adds_pids": len(adds_by_pid),
        "drops_pids": len(drops_by_pid),
        "trades_pids": len(trades_by_pid),
        "computed_at": now_iso,
    }
    logger.info("player_trends: %s", result)
    return result


async def player_trends_loop(db, interval_sec: int = DEFAULT_INTERVAL_SEC):
    """Long-running asyncio task. Defers first pass by 60s so the rest
    of the app boots cleanly."""
    logger.info("Player trends aggregator started (interval=%ds)", interval_sec)
    await asyncio.sleep(60)
    while True:
        try:
            await aggregate_player_trends_once(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("player_trends iteration failed: %s", e)
            await asyncio.sleep(300)
            continue
        await asyncio.sleep(interval_sec)

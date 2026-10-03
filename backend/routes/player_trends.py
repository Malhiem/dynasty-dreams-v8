"""Iter 232N.7 — Player trends endpoints.

Two public reads:
  • GET /api/player-trends/leaderboard?movers=hot|dropped|traded|all&days=7&limit=10
        → dedicated widget data (rank-ordered list of players with the
        strongest signal in the chosen category).
  • GET /api/player-trends/for-players?ids=<comma-separated>
        → helper for callers that want to enrich their own list of
        players with the same badge (used sparingly — most callers get
        the trend inline on their own endpoint payload).

Both are read-only. The nightly aggregator in
`services/player_trends_aggregator.py` populates `player_trends`.
"""
from __future__ import annotations

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Request

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def fetch_trends_map(db_or_none, player_ids: list[str] = None) -> dict[str, dict]:
    """Helper used by /players, /waivers/available, /roster/{team_id},
    and the player-status feed to enrich rows with a compact trend
    payload. Returns `{player_id: {trend, adds_7d, drops_7d,
    trades_7d, distinct_leagues_7d}}` for every requested id that has
    an active trend (missing entries → no badge).

    Iter 232N.7 — Accepts an explicit `db` handle as the first arg
    so callers can pass their own Motor instance without needing to
    call `setup(...)` first (avoids tight coupling in tests).
    Backwards-compatible: when called with a single list arg (legacy)
    it falls back to `_deps["db"]`.
    """
    # Legacy single-arg call — fall back to the module-registered db.
    if player_ids is None:
        player_ids = db_or_none if isinstance(db_or_none, list) else []
        db = _db()
    else:
        db = db_or_none if db_or_none is not None else _db()
    if not player_ids:
        return {}
    ids = [str(p) for p in player_ids if p]
    if not ids:
        return {}
    out: dict[str, dict] = {}
    async for row in db.player_trends.find(
        {"player_id": {"$in": ids}, "trend": {"$ne": None}},
        {
            "player_id": 1, "trend": 1,
            "adds_7d": 1, "drops_7d": 1, "trades_7d": 1,
            "distinct_leagues_7d": 1,
        },
    ):
        out[row["player_id"]] = {
            "trend": row.get("trend"),
            "adds_7d": row.get("adds_7d", 0),
            "drops_7d": row.get("drops_7d", 0),
            "trades_7d": row.get("trades_7d", 0),
            "distinct_leagues_7d": row.get("distinct_leagues_7d", 0),
        }
    return out


@router.get("/player-trends/leaderboard")
async def get_trends_leaderboard(
    request: Request,
    movers: str = "hot",
    days: int = 7,
    limit: int = 10,
):
    """Top movers in the last `days` days across ALL leagues. `movers`
    picks the sort key: hot → adds_7d desc, dropped → drops_7d desc,
    traded → trades_7d desc, all → total_events_7d desc.

    Response shape: `{players: [{player_id, name, position, team,
    trend, adds_7d, drops_7d, trades_7d, distinct_leagues_7d}, ...]}`.
    """
    db = _db()
    sort_key = {
        "hot": "adds_7d",
        "dropped": "drops_7d",
        "traded": "trades_7d",
        "all": "total_events_7d",
    }.get(movers, "adds_7d")
    query: dict = {sort_key: {"$gt": 0}}
    if movers != "all":
        # Restrict to rows whose derived trend matches the category so
        # the leaderboard mirrors what the badge on each row shows.
        query["trend"] = movers
    rows = (
        await db.player_trends.find(query).sort(sort_key, -1).limit(max(1, min(int(limit or 10), 100))).to_list(limit)
    )
    # Enrich with basic player fields for the widget (name/position/team).
    pids = [r["player_id"] for r in rows]
    players_by_id: dict[str, dict] = {}
    if pids:
        obj_ids: list = []
        for p in pids:
            try:
                obj_ids.append(ObjectId(p))
            except Exception:
                continue
        async for p in db.players.find(
            {"_id": {"$in": obj_ids}},
            {"name": 1, "position": 1, "team": 1, "current_team_abbrev": 1, "player_type": 1},
        ):
            players_by_id[str(p["_id"])] = p

    out = []
    for r in rows:
        p = players_by_id.get(r["player_id"], {})
        out.append({
            "player_id": r["player_id"],
            "name": p.get("name"),
            "position": p.get("position"),
            "team": p.get("team") or p.get("current_team_abbrev"),
            "player_type": p.get("player_type") or "skater",
            "trend": r.get("trend"),
            "adds_7d": r.get("adds_7d", 0),
            "drops_7d": r.get("drops_7d", 0),
            "trades_7d": r.get("trades_7d", 0),
            "distinct_leagues_7d": r.get("distinct_leagues_7d", 0),
        })
    return {"players": out, "movers": movers, "days": days}


@router.get("/player-trends/for-players")
async def get_trends_for_players(request: Request, ids: str = ""):
    """Bulk enrichment: given a comma-separated list of player_ids,
    return `{player_id: {trend, adds_7d, drops_7d, trades_7d,
    distinct_leagues_7d}}` for every id with an active trend."""
    id_list = [i.strip() for i in (ids or "").split(",") if i.strip()]
    return {"trends": await fetch_trends_map(id_list)}

"""Iter 232L (refactor) — Trade asset hydration helpers.

Extracted from `routes/trades.py` so the 2.2k-line trades module stays
focused on route handlers and business logic, and the Transactions-page
enrichment layer has a single testable home.

Historical trade docs only stored `{player_name, position, points, goals,
assists}` per asset. The Transactions page needs `age`, `cap_hit`, fantasy
points (season + per-game), games played, and a stat-category breakdown so
managers can properly evaluate the trade. `hydrate_trade_assets(db, trade)`
enriches assets from the live `players` + `contracts` collections, computes
fantasy points against the league's current `scoring_configs`, and stamps
`scoring_categories` on the trade so the frontend can render dynamic
Category vs FPts columns.

The helpers use a `deps` dict (populated at startup via `setup(deps)`) so
they can call the same `calculate_fantasy_points` implementation that
`routes/scoring.py`, `routes/roster.py`, and `routes/trades.py` already
share — no duplicate scoring math.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


# Human-friendly abbreviations for every counting stat we might score on.
# Unknown keys fall back to Title Case (see `_label_for`).
STAT_CATEGORY_LABELS: dict[str, str] = {
    "goals": "G",
    "assists": "A",
    "points": "P",
    "plus_minus": "+/-",
    "penalty_minutes": "PIM",
    "power_play_goals": "PPG",
    "power_play_points": "PPP",
    "short_handed_goals": "SHG",
    "short_handed_points": "SHP",
    "game_winning_goals": "GWG",
    "shots": "SOG",
    "hits": "HIT",
    "blocked_shots": "BLK",
    "faceoffs_won": "FOW",
    "wins": "W",
    "losses": "L",
    "saves": "SV",
    "goals_against": "GA",
    "shutouts": "SO",
    "overtime_losses": "OTL",
    "save_pct": "SV%",
    "goals_against_avg": "GAA",
}


_deps: dict = {}


def setup(deps: dict) -> None:
    """Wire in the shared deps (`calculate_fantasy_points`, `logger`)."""
    _deps.update(deps)


def _logger() -> logging.Logger:
    return _deps.get("logger") or logging.getLogger("trade_hydration")


def _label_for(key: str) -> str:
    return STAT_CATEGORY_LABELS.get(key, key.replace("_", " ").title())


async def _fetch_scoring_config(db, league_id: str) -> dict:
    cfg = await db.scoring_configs.find_one({"league_id": league_id})
    if not cfg:
        from routes.scoring import DEFAULT_SKATER_SCORING, DEFAULT_GOALIE_SCORING
        return {
            "skater_scoring": DEFAULT_SKATER_SCORING,
            "goalie_scoring": DEFAULT_GOALIE_SCORING,
        }
    return cfg


def _asset_stat_categories(player: dict, scoring_cfg: dict) -> dict:
    """Return `{category_key: {label, value}}` for the categories the league
    scores, keyed on whether the player is a skater or goalie."""
    is_goalie = (player.get("player_type") == "goalie") or (player.get("position") == "G")
    section = "goalie_scoring" if is_goalie else "skater_scoring"
    cat_map = (scoring_cfg or {}).get(section) or {}
    return {
        key: {"label": _label_for(key), "value": player.get(key, 0) or 0}
        for key in cat_map.keys()
    }


def _order_categories(cfg_section: dict) -> list[dict]:
    return [{"key": k, "label": _label_for(k)} for k in (cfg_section or {}).keys()]


def _compute_age(player: dict) -> int:
    """Prefer the flat `age` field; fall back to computing from `birth_date`
    for older seeds. Returns 0 when neither is available."""
    age = player.get("age")
    if age:
        return int(age)
    bd = player.get("birth_date")
    if not bd:
        return 0
    try:
        bd_dt = datetime.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        return int(
            today.year - bd_dt.year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
        )
    except Exception:
        return 0


async def _resolve_cap_hit(db, league_id: str, player_id: str, player: dict, scoring_cfg: dict) -> float:
    """Contract AAV wins; else fall back to the same synthesized salary the
    roster/team pages use so every surface shows a consistent cap hit."""
    try:
        contract = await db.contracts.find_one({"league_id": league_id, "player_id": player_id})
    except Exception:
        contract = None
    if contract and contract.get("aav"):
        return float(contract["aav"])
    try:
        from routes.roster import _synthesize_player_salary
        return float(_synthesize_player_salary(player, scoring_cfg))
    except Exception:
        return float(player.get("salary") or player.get("aav") or 0)


def _is_pick_asset(asset: dict) -> bool:
    return (
        asset.get("asset_type") == "pick"
        or asset.get("item_type") == "pick"
        or not asset.get("player_id")
    )


async def _hydrate_side(db, league_id: str, scoring_cfg: dict, calc_fn, assets: list) -> list:
    if not assets:
        return assets
    out = []
    for raw in assets:
        asset = dict(raw) if not isinstance(raw, dict) else raw
        if _is_pick_asset(asset):
            out.append(asset)
            continue
        pid = asset["player_id"]
        try:
            player = await db.players.find_one({"_id": ObjectId(pid)})
        except Exception:
            player = None
        if not player:
            out.append(asset)
            continue

        asset["player_name"] = player.get("name") or asset.get("player_name")
        asset["position"] = player.get("position") or asset.get("position")
        asset["nhl_team"] = player.get("team") or asset.get("nhl_team", "")
        asset["age"] = _compute_age(player)

        cap_hit = await _resolve_cap_hit(db, league_id, pid, player, scoring_cfg)
        asset["salary"] = cap_hit
        asset["cap_hit"] = cap_hit

        asset["goals"] = player.get("goals", 0) or 0
        asset["assists"] = player.get("assists", 0) or 0
        asset["points"] = player.get("points", 0) or 0
        gp = int(player.get("games_played", 0) or 0)
        asset["games_played"] = gp

        fpts = float(calc_fn(player, scoring_cfg) if callable(calc_fn) else 0.0)
        asset["fantasy_points"] = round(fpts, 1)
        asset["fantasy_points_per_game"] = round(fpts / gp, 2) if gp else 0.0

        asset["stat_categories"] = _asset_stat_categories(player, scoring_cfg)
        asset["player_type"] = player.get("player_type") or "skater"
        out.append(asset)
    return out


async def hydrate_trade_assets(db, trade: dict) -> dict:
    """Enrich a trade's `assets_offered`/`assets_requested` with age, cap
    hit, fantasy points (season + per-game), games played, and a
    stat-category breakdown. Also stamps `trade.scoring_categories` so the
    frontend knows which columns to render.

    Idempotent — safe to call on already-hydrated trades.
    """
    league_id = trade.get("league_id")
    if not league_id:
        return trade
    scoring_cfg = await _fetch_scoring_config(db, league_id)
    calc_fn = _deps.get("calculate_fantasy_points")

    trade["scoring_categories"] = {
        "skater": _order_categories(scoring_cfg.get("skater_scoring") or {}),
        "goalie": _order_categories(scoring_cfg.get("goalie_scoring") or {}),
    }
    trade["assets_offered"] = await _hydrate_side(
        db, league_id, scoring_cfg, calc_fn, trade.get("assets_offered") or []
    )
    trade["assets_requested"] = await _hydrate_side(
        db, league_id, scoring_cfg, calc_fn, trade.get("assets_requested") or []
    )
    return trade


async def hydrate_trades(db, trades: list[Any]) -> list[Any]:
    """Best-effort bulk hydrate — errors on any one trade are logged and
    swallowed so a single bad row can't blow up the whole list response."""
    for t in trades:
        try:
            await hydrate_trade_assets(db, t)
        except Exception as e:
            _logger().debug(f"trade asset hydrate failed for {t.get('_id')}: {e}")
    return trades

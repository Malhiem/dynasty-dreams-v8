"""Trade Value Analyzer + Player Projections (Pro paywall).

Free tier: **1 full trade analysis per calendar year**. Pro = unlimited.
Player projections + single-asset valuations are unmetered (cheap, encourages exploration);
only the full multi-asset `analyze_trade` call burns the yearly quota.

Value model (deterministic — no LLM):
  - Player value = projected ROS fantasy points × positional scarcity multiplier
  - Pick value = round-based curve × year-discount (0.85 ** offset)
  - FAAB value = $ × 0.4 (rough peg: $50 FAAB ≈ 1 R5 pick)
  - Salary retention = retained $ pro-rated against player's value
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}

FREE_ANALYSES_PER_YEAR = 1

# Round-based pick value curve (R1 = 100, decreases). Tuned for redraft + dynasty.
PICK_ROUND_VALUE = {
    1: 100.0, 2: 60.0, 3: 40.0, 4: 28.0, 5: 20.0,
    6: 15.0, 7: 11.0, 8: 8.0, 9: 6.0, 10: 4.5,
    11: 3.5, 12: 3.0, 13: 2.5, 14: 2.0, 15: 1.5,
}

YEAR_DISCOUNT = 0.85          # per future year offset
FAAB_PER_DOLLAR = 0.4         # value units per FAAB $

# Positional scarcity multipliers (rough heuristic — top scoring positions
# are scarcer relative to FPTS production).
POSITION_SCARCITY = {
    "C": 1.10, "LW": 1.00, "RW": 1.00, "D": 1.05,
    "LD": 1.05, "RD": 1.05, "G": 1.20,
}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request):
    return await _deps["get_current_user"](request)


def _year_key(now: datetime) -> str:
    return now.strftime("%Y")


async def _ensure_analyzer_quota(db, user: dict) -> dict:
    """Reset yearly analyzer counter on Jan 1. Return current quota state."""
    now = datetime.now(timezone.utc)
    period_key = _year_key(now)
    is_pro = bool(user.get("is_pro"))
    used = int(user.get("analyses_used_this_year") or 0)
    user_period_key = user.get("analyses_period_key")
    user_oid = ObjectId(user["_id"]) if isinstance(user["_id"], str) else user["_id"]
    if user_period_key != period_key:
        used = 0
        await db.users.update_one(
            {"_id": user_oid},
            {"$set": {
                "analyses_used_this_year": 0,
                "analyses_period_key": period_key,
            }},
        )
    return {
        "is_pro": is_pro,
        "used": used,
        "remaining": max(0, FREE_ANALYSES_PER_YEAR - used),
        "user_oid": user_oid,
    }


@router.get("/users/me/analyzer-status")
async def get_analyzer_status(request: Request):
    db = _db()
    user = await _get_user(request)
    q = await _ensure_analyzer_quota(db, user)
    return {
        "is_pro": q["is_pro"],
        "free_analyses_per_year": FREE_ANALYSES_PER_YEAR,
        "analyses_used_this_year": q["used"],
        "analyses_remaining": (None if q["is_pro"] else q["remaining"]),
    }


# -----------------------------------------------------------------------------
# Player projections
# -----------------------------------------------------------------------------

async def _player_blended_fpg(db, player: dict, scoring_cfg: Optional[dict]) -> dict:
    """Compute blended fantasy-points-per-game for a player.
    Returns {season_fpg, recent_fpg, blended_fpg, gp_season, gp_recent, source}.
    """
    is_goalie = (player.get("position") == "G") or (player.get("player_type") == "goalie")
    calc = _deps["calculate_fantasy_points"]

    # Season totals from the player doc
    season_payload = {
        "goals": player.get("goals", 0), "assists": player.get("assists", 0),
        "points": player.get("points", 0), "plus_minus": player.get("plus_minus", 0),
        "shots": player.get("shots", 0),
        "ppg": player.get("power_play_goals", 0),
        "ppp": player.get("power_play_points", 0),
        "shg": player.get("short_handed_goals", 0),
        "pim": player.get("penalty_minutes", 0),
        "saves": player.get("saves", 0),
        "goals_against": player.get("goals_against", 0),
        "wins": player.get("wins", 0),
        "shutouts": player.get("shutouts", 0),
        "games_played": player.get("games_played", 0),
        "position": player.get("position") or "C",
        "player_type": "goalie" if is_goalie else "skater",
    }
    gp_season = max(0, int(player.get("games_played") or 0))
    season_fpts = calc(season_payload, scoring_cfg)
    season_fpg = (season_fpts / gp_season) if gp_season > 0 else 0.0

    # Recent — last 14 days from player_game_logs
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    cursor = db.player_game_logs.find({
        "player_id": str(player["_id"]) if isinstance(player.get("_id"), ObjectId) else player.get("_id"),
        "date_dt": {"$gte": cutoff},
    })
    agg = {k: 0 for k in [
        "games_played", "goals", "assists", "points", "plus_minus", "shots",
        "ppg", "shg", "ppp", "shp", "pim",
        "saves", "goals_against", "wins", "losses", "shutouts",
    ]}
    async for g in cursor:
        agg["games_played"] += 1
        agg["goals"] += g.get("goals", 0) or 0
        agg["assists"] += g.get("assists", 0) or 0
        agg["points"] += g.get("points", 0) or 0
        agg["plus_minus"] += g.get("plus_minus", 0) or 0
        agg["shots"] += g.get("sog", 0) or 0
        agg["ppg"] += g.get("ppg", 0) or 0
        agg["ppp"] += g.get("ppp", 0) or 0
        agg["pim"] += g.get("pim", 0) or 0
        agg["saves"] += g.get("saves", 0) or 0
        agg["goals_against"] += g.get("goals_against", 0) or 0
        agg["wins"] += g.get("wins", 0) or 0
        agg["losses"] += g.get("losses", 0) or 0
        agg["shutouts"] += g.get("shutouts", 0) or 0
    gp_recent = agg["games_played"]
    agg["position"] = player.get("position") or "C"
    agg["player_type"] = "goalie" if is_goalie else "skater"
    recent_fpts = calc(agg, scoring_cfg)
    recent_fpg = (recent_fpts / gp_recent) if gp_recent > 0 else 0.0

    # Blended: 60% season, 40% recent (when recent has data)
    if gp_recent > 0:
        blended = 0.6 * season_fpg + 0.4 * recent_fpg
        source = "blended"
    else:
        blended = season_fpg
        source = "season_only"

    return {
        "season_fpg": round(season_fpg, 2),
        "recent_fpg": round(recent_fpg, 2),
        "blended_fpg": round(blended, 2),
        "gp_season": gp_season,
        "gp_recent": gp_recent,
        "source": source,
    }


def _games_remaining_estimate(gp_season: int, league: Optional[dict]) -> int:
    """Estimate remaining NHL games for a player. Uses 82-game season minus
    GP, clamped to [0, 82]. Honors league.regular_season_games override."""
    season_total = 82
    if league and league.get("regular_season_games"):
        season_total = int(league["regular_season_games"])
    return max(0, season_total - gp_season)


def _scarcity_mult(position: Optional[str]) -> float:
    if not position:
        return 1.0
    return POSITION_SCARCITY.get(position.upper(), 1.0)


async def _value_player(
    db, player: dict, scoring_cfg: Optional[dict], league: Optional[dict],
) -> dict:
    bf = await _player_blended_fpg(db, player, scoring_cfg)
    gr = _games_remaining_estimate(bf["gp_season"], league)
    proj_ros = bf["blended_fpg"] * gr
    scarcity = _scarcity_mult(player.get("position"))
    raw_value = proj_ros * scarcity
    return {
        "player_id": str(player["_id"]),
        "name": player.get("name"),
        "team": player.get("team"),
        "position": player.get("position"),
        "blended_fpg": bf["blended_fpg"],
        "season_fpg": bf["season_fpg"],
        "recent_fpg": bf["recent_fpg"],
        "games_remaining": gr,
        "projected_ros_fpts": round(proj_ros, 1),
        "scarcity_mult": scarcity,
        "value": round(raw_value, 1),
        "source": bf["source"],
    }


def _value_pick(pick: dict) -> dict:
    """Value a draft pick. `pick` shape: {round, year, slot?, league_id, ...}.
    Slot reduces value linearly within a round (1.00 → 0.60 by end of round).
    Future years get a YEAR_DISCOUNT compounding penalty.
    """
    rnd = int(pick.get("round") or 1)
    year = int(pick.get("year") or datetime.now(timezone.utc).year)
    slot = pick.get("slot")
    teams_in_round = int(pick.get("teams_in_round") or 12)

    base = PICK_ROUND_VALUE.get(rnd, max(1.0, 1.5 - 0.1 * (rnd - 14)))
    slot_mult = 1.0
    if slot is not None:
        # Pick #1 in round → 1.00, last pick → 0.60
        position_in_round = max(0, min(slot - 1, teams_in_round - 1))
        slot_mult = 1.0 - (0.4 * (position_in_round / max(1, teams_in_round - 1)))

    current_year = datetime.now(timezone.utc).year
    year_offset = max(0, year - current_year)
    year_mult = YEAR_DISCOUNT ** year_offset

    value = base * slot_mult * year_mult
    return {
        "round": rnd,
        "year": year,
        "slot": slot,
        "base_value": base,
        "slot_mult": round(slot_mult, 2),
        "year_mult": round(year_mult, 2),
        "value": round(value, 1),
        "label": f"{year} R{rnd}" + (f".{slot:02d}" if slot else ""),
    }


@router.post("/trade-analyzer/value-player")
async def value_player_endpoint(payload: dict, request: Request):
    """Cheap (unmetered) — value a single player against a league's scoring."""
    db = _db()
    await _get_user(request)
    pid = payload.get("player_id")
    league_id = payload.get("league_id")
    if not pid:
        raise HTTPException(status_code=400, detail="player_id required")
    try:
        player = await db.players.find_one({"_id": ObjectId(pid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid player_id")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scoring_cfg = await db.scoring_configs.find_one({"league_id": league_id}) if league_id else None
    league = None
    if league_id:
        try:
            league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        except Exception:
            league = None
    return await _value_player(db, player, scoring_cfg, league)


@router.post("/trade-analyzer/value-pick")
async def value_pick_endpoint(payload: dict, request: Request):
    """Cheap (unmetered) — value a single draft pick."""
    await _get_user(request)
    if "round" not in payload:
        raise HTTPException(status_code=400, detail="round required")
    return _value_pick(payload)


# -----------------------------------------------------------------------------
# Player projections endpoint
# -----------------------------------------------------------------------------
@router.get("/players/{player_id}/projections")
async def get_player_projections(
    player_id: str, request: Request,
    league_id: Optional[str] = None, horizon: str = "ros",
):
    """Return player projections.
    horizon: "ros" (rest-of-season, default) | "weekly" (current week, ~3.5 games)
    """
    db = _db()
    await _get_user(request)
    try:
        player = await db.players.find_one({"_id": ObjectId(player_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid player_id")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    scoring_cfg = await db.scoring_configs.find_one({"league_id": league_id}) if league_id else None
    league = None
    if league_id:
        try:
            league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        except Exception:
            league = None

    bf = await _player_blended_fpg(db, player, scoring_cfg)
    gr = _games_remaining_estimate(bf["gp_season"], league)

    # ROS projection
    proj_ros = bf["blended_fpg"] * gr
    # Weekly projection: assume ~3.5 games in a 7-day fantasy week
    games_per_week = 3.5
    proj_week = bf["blended_fpg"] * games_per_week

    return {
        "player_id": player_id,
        "league_id": league_id,
        "horizon": horizon,
        "blended_fpg": bf["blended_fpg"],
        "season_fpg": bf["season_fpg"],
        "recent_fpg": bf["recent_fpg"],
        "gp_season": bf["gp_season"],
        "gp_recent": bf["gp_recent"],
        "games_remaining": gr,
        "projected_ros_fpts": round(proj_ros, 1),
        "projected_week_fpts": round(proj_week, 1),
        "games_per_week_assumed": games_per_week,
        "source": bf["source"],
    }


# -----------------------------------------------------------------------------
# Full trade analysis (paywalled)
# -----------------------------------------------------------------------------
async def _value_side(
    db, side: dict, scoring_cfg: Optional[dict], league: Optional[dict],
) -> dict:
    """Value one side of a trade. side shape:
    { "team_id": str, "players": [player_id], "picks": [{round,year,slot?}],
      "faab": int, "salary_retentions": [{player_id, amount}] }
    Returns total value + per-asset breakdown.
    """
    out_players, out_picks = [], []
    total = 0.0

    # Players
    for pid in (side.get("players") or []):
        try:
            p = await db.players.find_one({"_id": ObjectId(pid)})
        except Exception:
            continue
        if not p:
            continue
        v = await _value_player(db, p, scoring_cfg, league)
        out_players.append(v)
        total += v["value"]

    # Picks
    for pk in (side.get("picks") or []):
        v = _value_pick(pk)
        out_picks.append(v)
        total += v["value"]

    # FAAB
    faab = float(side.get("faab") or 0)
    faab_value = faab * FAAB_PER_DOLLAR

    # Salary retentions — value paid by THIS side (cost of retention)
    retention_cost = 0.0
    for r in (side.get("salary_retentions") or []):
        retention_cost += float(r.get("amount") or 0) * (FAAB_PER_DOLLAR / 1_000_000.0)
        # 1M retained ≈ $1 FAAB equivalent — heuristic; salary cap leagues vary widely

    side_total = total + faab_value - retention_cost

    return {
        "team_id": side.get("team_id"),
        "players": out_players,
        "picks": out_picks,
        "faab": faab,
        "faab_value": round(faab_value, 1),
        "retention_cost": round(retention_cost, 1),
        "asset_value_total": round(total, 1),
        "total_value": round(side_total, 1),
    }


@router.post("/trade-analyzer/analyze")
async def analyze_trade(payload: dict, request: Request):
    """Full trade analysis. Quota: 1 free analysis / calendar year (Pro = unlimited).

    Body shape:
    {
      "league_id": "...",
      "side_a": {team_id, players[], picks[], faab, salary_retentions[]},
      "side_b": {team_id, players[], picks[], faab, salary_retentions[]}
    }
    """
    db = _db()
    user = await _get_user(request)

    q = await _ensure_analyzer_quota(db, user)
    if not q["is_pro"] and q["remaining"] <= 0:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "upgrade_required",
                "message": "You've used your 1 free trade analysis this year. Upgrade to Pro for unlimited.",
                "free_analyses_per_year": FREE_ANALYSES_PER_YEAR,
                "analyses_used_this_year": q["used"],
            },
        )

    league_id = payload.get("league_id")
    side_a = payload.get("side_a") or {}
    side_b = payload.get("side_b") or {}
    if not (side_a.get("players") or side_a.get("picks") or side_a.get("faab")):
        raise HTTPException(status_code=400, detail="side_a is empty")
    if not (side_b.get("players") or side_b.get("picks") or side_b.get("faab")):
        raise HTTPException(status_code=400, detail="side_b is empty")

    scoring_cfg = await db.scoring_configs.find_one({"league_id": league_id}) if league_id else None
    league = None
    if league_id:
        try:
            league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        except Exception:
            league = None

    a_eval = await _value_side(db, side_a, scoring_cfg, league)
    b_eval = await _value_side(db, side_b, scoring_cfg, league)

    a_total = a_eval["total_value"]
    b_total = b_eval["total_value"]
    delta = round(a_total - b_total, 1)
    bigger = max(abs(a_total), abs(b_total), 1.0)
    fairness_pct = round(100.0 * (1.0 - abs(delta) / bigger), 1)
    if delta > 0:
        winner = "a"
    elif delta < 0:
        winner = "b"
    else:
        winner = "tie"

    # Verdict bands
    if fairness_pct >= 90:
        verdict = "Fair Trade"
    elif fairness_pct >= 75:
        verdict = "Slightly Lopsided"
    elif fairness_pct >= 60:
        verdict = "Lopsided"
    else:
        verdict = "Heavily Lopsided"

    # Burn quota AFTER successful build
    if not q["is_pro"]:
        await db.users.update_one(
            {"_id": q["user_oid"]},
            {"$inc": {"analyses_used_this_year": 1}},
        )

    return {
        "league_id": league_id,
        "side_a": a_eval,
        "side_b": b_eval,
        "delta": delta,                      # +N => A's side gains more
        "winner": winner,
        "fairness_pct": fairness_pct,
        "verdict": verdict,
        "is_pro": q["is_pro"],
        "analyses_remaining": (None if q["is_pro"]
                               else max(0, FREE_ANALYSES_PER_YEAR - q["used"] - 1)),
    }

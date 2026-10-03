"""Iter 232N.86 — Rotisserie (Roto) scoring engine + endpoints.

Design goals
------------
Roto leagues rank teams within each stat category over a scoring
period, award points based on that rank (12-team league → 1st = 12,
last = 1), and sum the points across periods to produce season
standings. This module powers:

  GET  /api/leagues/{id}/roto/categories/catalog    — every trackable stat
  GET  /api/leagues/{id}/roto/standings             — season totals
  GET  /api/leagues/{id}/roto/matchup?period=N      — current period stats
  POST /api/leagues/{id}/roto/recompute             — manual recompute

The engine is pure-python (no external deps). It reads player stats
from `db.players.season_stats` and roster memberships from
`db.teams.roster`, computes per-team category totals for the target
period (or full season), ranks each category, awards points using
the league's tie-break rule, and persists the result to
`db.roto_period_results`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field


from routes.league_guards import require_league_member


router = APIRouter()
_deps: dict = {}


def register_dependencies(**kwargs):
    _deps.update(kwargs)


# ─── Stat catalog ────────────────────────────────────────────────

SKATER_CATEGORIES = [
    {"key": "goals",              "label": "Goals (G)",              "type": "skater", "higher_is_better": True},
    {"key": "assists",            "label": "Assists (A)",            "type": "skater", "higher_is_better": True},
    {"key": "points",             "label": "Points (P)",             "type": "skater", "higher_is_better": True},
    {"key": "plus_minus",         "label": "Plus/Minus (+/-)",       "type": "skater", "higher_is_better": True},
    {"key": "penalty_minutes",    "label": "Penalty Minutes (PIM)",  "type": "skater", "higher_is_better": False},
    {"key": "power_play_goals",   "label": "Power Play Goals (PPG)", "type": "skater", "higher_is_better": True},
    {"key": "power_play_points",  "label": "Power Play Points (PPP)","type": "skater", "higher_is_better": True},
    {"key": "short_handed_goals", "label": "Short-handed Goals (SHG)","type": "skater","higher_is_better": True},
    {"key": "short_handed_points","label": "Short-handed Points (SHP)","type": "skater","higher_is_better": True},
    {"key": "game_winning_goals", "label": "Game-Winning Goals (GWG)","type": "skater","higher_is_better": True},
    {"key": "shots",              "label": "Shots on Goal (SOG)",    "type": "skater", "higher_is_better": True},
    {"key": "hits",               "label": "Hits (HIT)",             "type": "skater", "higher_is_better": True},
    {"key": "blocks",             "label": "Blocked Shots (BLK)",    "type": "skater", "higher_is_better": True},
    {"key": "faceoff_wins",       "label": "Faceoff Wins (FOW)",     "type": "skater", "higher_is_better": True},
]
GOALIE_CATEGORIES = [
    {"key": "wins",             "label": "Wins (W)",           "type": "goalie", "higher_is_better": True},
    {"key": "losses",           "label": "Losses (L)",         "type": "goalie", "higher_is_better": False},
    {"key": "saves",            "label": "Saves (SV)",         "type": "goalie", "higher_is_better": True},
    {"key": "save_percentage",  "label": "Save % (SV%)",       "type": "goalie", "higher_is_better": True},
    {"key": "goals_against_avg","label": "GAA",                "type": "goalie", "higher_is_better": False},
    {"key": "shutouts",         "label": "Shutouts (SO)",      "type": "goalie", "higher_is_better": True},
    {"key": "overtime_losses",  "label": "Overtime Losses (OTL)","type": "goalie","higher_is_better": False},
]
ALL_CATEGORIES = SKATER_CATEGORIES + GOALIE_CATEGORIES
CATEGORY_BY_KEY = {c["key"]: c for c in ALL_CATEGORIES}
DEFAULT_ROTO_CATEGORIES = [
    "goals", "assists", "points", "power_play_points",
    "shots", "hits", "blocks", "plus_minus",
    "wins", "saves", "save_percentage", "shutouts",
]


# ─── Engine ──────────────────────────────────────────────────────

async def _team_stat_totals(db, league_id: str, period: Optional[int], periods: Optional[list[int]] = None):
    """For each team in the league, compute roto category stats using
    game-level ownership allocation.

    Each game's stats are credited only to the team that owned the player
    at puck-drop AND had the player in an active lineup position.

    Returns: {team_id: {"team_name": str, "stats": {stat: float}}}
    """
    from utils.scoring_roster import week_to_time_range
    from utils.game_allocation import allocate_team_period_roto_stats

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        return {}

    # Resolve which weeks/periods to compute
    weeks_to_compute = []
    if periods is not None:
        weeks_to_compute = list(periods)
    elif period is not None:
        weeks_to_compute = [period]
    else:
        # Full season: compute all weeks up to current_week
        cw = int(league.get("current_week") or 1)
        weeks_to_compute = list(range(1, cw + 1))

    category_keys = [c["key"] for c in ALL_CATEGORIES]

    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    out = {}
    for t in teams:
        tid = str(t["_id"])
        agg: dict = {k: 0 for k in category_keys}

        has_period_data = False
        for w in weeks_to_compute:
            ps, pe = week_to_time_range(league, w)
            if ps and pe:
                has_period_data = True
                period_stats = await allocate_team_period_roto_stats(
                    db, tid, league_id, ps, pe, category_keys,
                )
                for k in category_keys:
                    agg[k] = round(float(agg.get(k, 0)) + float(period_stats.get(k, 0)), 3)

        if not has_period_data:
            # Fallback: no season_start_date → use aggregate player stats
            from utils.scoring_roster import get_scoring_roster
            roster = await get_scoring_roster(db, tid, league_id)
            for pid in roster:
                try:
                    p = await db.players.find_one({"_id": ObjectId(pid)})
                except Exception:
                    continue
                if not p:
                    continue
                if periods is not None:
                    player_period_stats = p.get("period_stats") or {}
                    for pnum in periods:
                        src = player_period_stats.get(str(pnum)) or {}
                        for cat in ALL_CATEGORIES:
                            k = cat["key"]
                            agg[k] = round(float(agg.get(k, 0)) + float(src.get(k, 0) or 0), 3)
                elif period is not None:
                    src = (p.get("period_stats") or {}).get(str(period)) or p.get("season_stats") or {}
                    for cat in ALL_CATEGORIES:
                        k = cat["key"]
                        agg[k] = round(float(agg.get(k, 0)) + float(src.get(k, 0) or 0), 3)
                else:
                    src = p.get("season_stats") or {}
                    for cat in ALL_CATEGORIES:
                        k = cat["key"]
                        agg[k] = round(float(agg.get(k, 0)) + float(src.get(k, 0) or 0), 3)

        out[tid] = {"team_name": t.get("name"), "stats": agg}
    return out


def _rank_category(
    team_stats: list[tuple[str, float]],
    higher_is_better: bool,
    tiebreak: str,
    num_teams: int,
) -> tuple[dict, dict]:
    """Rank a single category. Returns (team_id → points, team_id → rank).

    Ranks use standard competition ranking (1-indexed; ties share the
    same rank and the next rank skips, e.g. 1,1,3).

    tiebreak "split":  Tied teams share the sum of their ranks' points
                       (rank 3+4 tie → both get (10+11)/2 = 10.5).
    tiebreak "high":   All tied teams get the HIGHER rank's points
                       (rank 3+4 tie → both get 11).
    """
    # Sort by value (descending if higher is better, else ascending).
    sorted_teams = sorted(
        team_stats,
        key=lambda x: (-x[1] if higher_is_better else x[1], x[0]),
    )
    points: dict[str, float] = {}
    ranks: dict[str, int] = {}
    i = 0
    while i < len(sorted_teams):
        j = i
        # Group ties.
        while (
            j + 1 < len(sorted_teams)
            and sorted_teams[j + 1][1] == sorted_teams[i][1]
        ):
            j += 1
        tied = sorted_teams[i:j + 1]
        rank = i + 1  # Standard competition rank (1-indexed)
        # Ranks for the tie window (0-indexed → position from top).
        ranks_points = [num_teams - (i + k) for k in range(len(tied))]
        if tiebreak == "split" and len(tied) > 1:
            share = sum(ranks_points) / len(tied)
            for tid, _ in tied:
                points[tid] = round(share, 3)
                ranks[tid] = rank
        elif tiebreak == "high" and len(tied) > 1:
            top = max(ranks_points)
            for tid, _ in tied:
                points[tid] = float(top)
                ranks[tid] = rank
        else:
            for (tid, _), rp in zip(tied, ranks_points):
                points[tid] = float(rp)
                ranks[tid] = rank
        i = j + 1
    return points, ranks


async def compute_period(
    db, league_id: str, period: Optional[int] = None,
    periods: Optional[list[int]] = None,
) -> dict:
    """Compute per-team stats + category points for the given period.

    When *periods* (a list of week numbers) is supplied, stats are
    aggregated across all those weeks — used by condensed-roto fresh
    totals to restrict to the playoff window.

    Returns:
      {
        "period": Optional[int],
        "categories": [{"key", "label", "team_stats", "points"}],
        "totals": {team_id: {"team_name", "total_points"}},
      }
    """
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    cats = league.get("roto_categories") or DEFAULT_ROTO_CATEGORIES
    tiebreak = league.get("roto_tiebreak") or "split"
    team_totals = await _team_stat_totals(db, league_id, period, periods=periods)
    team_ids = list(team_totals.keys())
    num_teams = len(team_ids)
    if num_teams == 0:
        return {"period": period, "categories": [], "totals": {}, "num_teams": 0}
    out_cats = []
    running: dict[str, float] = {tid: 0.0 for tid in team_ids}
    for c_key in cats:
        cat = CATEGORY_BY_KEY.get(c_key)
        if not cat:
            continue
        pairs = [(tid, team_totals[tid]["stats"].get(c_key, 0.0)) for tid in team_ids]
        points_by_tid, ranks_by_tid = _rank_category(
            pairs, cat["higher_is_better"], tiebreak, num_teams,
        )
        out_cats.append({
            "key": c_key,
            "label": cat["label"],
            "higher_is_better": cat["higher_is_better"],
            "team_stats": {tid: v for (tid, v) in pairs},
            "points": points_by_tid,
            "ranks": ranks_by_tid,
        })
        for tid, pts in points_by_tid.items():
            running[tid] = round(running.get(tid, 0.0) + pts, 3)
    totals = {tid: {
        "team_name": team_totals[tid]["team_name"],
        "total_points": running[tid],
    } for tid in team_ids}
    return {
        "period": period,
        "periods": periods,
        "fresh_totals": periods is not None,
        "categories": out_cats,
        "totals": totals,
        "num_teams": num_teams,
        "tiebreak": tiebreak,
    }


async def compute_season(db, league_id: str) -> dict:
    """Sum per-period points across every persisted period. Falls back
    to the full-season snapshot when no periods exist yet.

    When the league uses condensed_roto with fresh_totals, stats are
    restricted to the playoff weeks (playoff_start → playoff_end)."""
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # ── Condensed-roto fresh totals ─────────────────────────────
    fresh = (
        bool(league.get("playoffs_enabled"))
        and league.get("playoff_format") == "condensed_roto"
        and bool(league.get("playoff_roto_fresh_totals"))
    )
    if fresh:
        start = league.get("playoff_start_week")
        end = league.get("playoff_end_week")
        if start is not None and end is not None:
            playoff_periods = list(range(int(start), int(end) + 1))
            result = await compute_period(
                db, league_id, period=None, periods=playoff_periods,
            )
            # Count closed playoff periods for metadata
            closed_count = await db.roto_period_results.count_documents({
                "league_id": league_id,
                "closed": True,
                "period": {"$in": playoff_periods},
            })
            result["periods_closed"] = closed_count
            # Apply seed bonuses: seeds are based on regular-season ranking
            seed_bonuses = league.get("playoff_roto_seed_bonuses") or {}
            if seed_bonuses and result.get("totals"):
                # Determine seeds from regular-season standings
                reg_result = await compute_period(db, league_id, period=None)
                reg_sorted = sorted(
                    reg_result.get("totals", {}).items(),
                    key=lambda x: -x[1].get("total_points", 0),
                )
                seed_map: dict[str, int] = {}
                for idx, (tid, _) in enumerate(reg_sorted):
                    seed_map[tid] = idx + 1  # 1-indexed seed
                # Add bonus to each team's total
                for tid, team_data in result["totals"].items():
                    seed = seed_map.get(tid, 999)
                    bonus = float(seed_bonuses.get(str(seed), 0))
                    if bonus:
                        team_data["total_points"] = round(
                            team_data["total_points"] + bonus, 3
                        )
                        team_data["seed_bonus"] = bonus
                        team_data["seed"] = seed
                result["seed_bonuses_applied"] = True
            return result

    periods = await db.roto_period_results.find(
        {"league_id": league_id, "closed": True},
        sort=[("period", 1)],
    ).to_list(200)
    if not periods:
        # No closed periods → return live full-season snapshot.
        result = await compute_period(db, league_id, period=None)
        result["periods_closed"] = 0
        return result
    # Aggregate points across every closed period. Structure the same
    # as compute_period so the frontend renders identically.
    running: dict[str, float] = {}
    team_names: dict[str, str] = {}
    per_category: dict[str, dict[str, float]] = {}
    per_category_stats: dict[str, dict[str, float]] = {}
    for p in periods:
        for tid, t in (p.get("totals") or {}).items():
            running[tid] = round(running.get(tid, 0.0) + float(t.get("total_points", 0)), 3)
            team_names[tid] = t.get("team_name", team_names.get(tid))
        for cat in (p.get("categories") or []):
            key = cat["key"]
            for tid, pts in (cat.get("points") or {}).items():
                per_category.setdefault(key, {}).setdefault(tid, 0.0)
                per_category[key][tid] = round(per_category[key][tid] + float(pts), 3)
            for tid, val in (cat.get("team_stats") or {}).items():
                per_category_stats.setdefault(key, {}).setdefault(tid, 0.0)
                per_category_stats[key][tid] = round(
                    per_category_stats[key][tid] + float(val), 3,
                )
    # Compute ranks from aggregated season points per category.
    cats_out = []
    num_teams = len(running)
    tiebreak = league.get("roto_tiebreak") or "split"
    for k, pts_map in per_category.items():
        cat_meta = CATEGORY_BY_KEY.get(k, {})
        stats_map = per_category_stats.get(k, {})
        # Rank by aggregated points (higher is better for accumulated roto pts).
        pairs = [(tid, pts) for tid, pts in pts_map.items()]
        _, ranks_by_tid = _rank_category(pairs, True, tiebreak, num_teams)
        cats_out.append({
            "key": k,
            "label": cat_meta.get("label", k),
            "higher_is_better": cat_meta.get("higher_is_better", True),
            "points": pts_map,
            "ranks": ranks_by_tid,
            "team_stats": stats_map,
        })
    return {
        "period": None,
        "aggregated": True,
        "periods_closed": len(periods),
        "totals": {tid: {"team_name": team_names.get(tid), "total_points": pts}
                   for tid, pts in running.items()},
        "categories": cats_out,
        "num_teams": num_teams,
        "tiebreak": tiebreak,
    }


# ─── Endpoints ───────────────────────────────────────────────────


async def _require_user(request: Request):
    return await _deps["get_current_user"](request)


@router.get("/leagues/{league_id}/roto/categories/catalog")
async def roto_catalog(league_id: str, request: Request):
    """Full catalog of stat categories a commissioner can pick from,
    plus the current league's selection so the settings UI can
    pre-check the right rows."""
    user = await _require_user(request)
    db = _deps["db"]
    league = await require_league_member(db, user, league_id)
    return {
        "categories": ALL_CATEGORIES,
        "defaults": DEFAULT_ROTO_CATEGORIES,
        "selected": league.get("roto_categories") or DEFAULT_ROTO_CATEGORIES,
        "tiebreak": league.get("roto_tiebreak") or "split",
        "period_length_weeks": league.get("roto_period_length_weeks", 1),
        "playoffs_enabled": bool(league.get("roto_playoffs_enabled")),
        "auto_recompute": bool(league.get("roto_auto_recompute", True)),
    }


@router.get("/leagues/{league_id}/roto/standings")
async def roto_standings(league_id: str, request: Request):
    """Season-level standings: total_points DESC + per-category rank."""
    user = await _require_user(request)
    db = _deps["db"]
    await require_league_member(db, user, league_id)
    return await compute_season(db, league_id)


@router.get("/leagues/{league_id}/roto/matchup")
async def roto_matchup(
    league_id: str, request: Request,
    period: Optional[int] = Query(None, ge=0, le=52),
):
    """Live per-team category stats for the requested scoring period."""
    user = await _require_user(request)
    db = _deps["db"]
    await require_league_member(db, user, league_id)
    return await compute_period(db, league_id, period=period)


class RecomputeRequest(BaseModel):
    period: Optional[int] = Field(None, ge=0, le=52)
    close: bool = False


@router.post("/leagues/{league_id}/roto/recompute")
async def roto_recompute(
    league_id: str, input: RecomputeRequest, request: Request,
):
    """Commissioner-triggered recompute. Persists to
    `db.roto_period_results` so `compute_season` can accumulate."""
    user = await _require_user(request)
    db = _deps["db"]
    league = await require_league_member(db, user, league_id)
    is_commissioner = str(league.get("commissioner_id")) == str(user.get("_id"))
    is_admin = user.get("role") in ("admin", "senior_admin")
    if not is_commissioner and not is_admin:
        raise HTTPException(status_code=403, detail="Commissioner only")
    # If condensed_roto + fresh totals, scope to playoff weeks
    fresh = (
        league.get("playoff_format") == "condensed_roto"
        and bool(league.get("playoff_roto_fresh_totals"))
        and input.period is None
    )
    playoff_periods = None
    if fresh:
        start = league.get("playoff_start_week")
        end = league.get("playoff_end_week")
        if start is not None and end is not None:
            playoff_periods = list(range(int(start), int(end) + 1))
    result = await compute_period(db, league_id, period=input.period, periods=playoff_periods)
    await db.roto_period_results.update_one(
        {"league_id": league_id, "period": input.period},
        {"$set": {
            "league_id": league_id,
            "period": input.period,
            "totals": result["totals"],
            "categories": result["categories"],
            "num_teams": result["num_teams"],
            "closed": bool(input.close),
            "recomputed_at": datetime.now(timezone.utc).isoformat(),
            "recomputed_by": user.get("email"),
        }},
        upsert=True,
    )
    return {
        "ok": True,
        "period": input.period,
        "closed": bool(input.close),
        "num_teams": result["num_teams"],
        "leader": next(
            iter(sorted(
                result["totals"].items(),
                key=lambda x: -x[1]["total_points"],
            )),
            (None, {"team_name": None, "total_points": 0}),
        )[1],
    }

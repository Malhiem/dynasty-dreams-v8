"""Scoring config + calculate + ROTO standings. Extracted from server.py
during Iter 108 server-extraction sweep. Endpoints/payloads/auth identical
to the pre-extraction implementation.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from routes.league_guards import require_league_member


from services.fantasy_scoring import DEFAULT_SKATER_SCORING, DEFAULT_GOALIE_SCORING

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class ScoringConfigCreate(BaseModel):
    league_id: str
    skater_scoring: dict
    goalie_scoring: dict
    roto_categories: list = []
    expected_revision: Optional[int] = None


@router.post("/scoring/config")
async def save_scoring_config(input: ScoringConfigCreate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if str(league["commissioner_id"]) != str(user["_id"]) and str(user["_id"]) not in [str(x) for x in league.get("co_commissioners", [])]:
        raise HTTPException(status_code=403, detail="Only commissioner can update scoring")

    config_doc = {
        "league_id": input.league_id,
        "skater_scoring": input.skater_scoring,
        "goalie_scoring": input.goalie_scoring,
        "roto_categories": input.roto_categories,
        "updated_by": user["_id"],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    current = await db.scoring_configs.find_one({"league_id": input.league_id})
    revision = (current or {}).get("revision", 0)
    if input.expected_revision is not None and input.expected_revision != revision:
        raise HTTPException(status_code=409, detail="Scoring changed since you loaded it. Reload the saved settings before trying again.")
    config_doc["revision"] = revision + 1
    if current:
        query = {"_id": current["_id"], "$or": [{"revision": revision}, {"revision": {"$exists": False}}]} if revision == 0 else {"_id": current["_id"], "revision": revision}
        saved = await db.scoring_configs.update_one(query, {"$set": config_doc})
        if saved.matched_count != 1:
            raise HTTPException(status_code=409, detail="Scoring changed since you loaded it. Reload the saved settings before trying again.")
    else:
        config_doc["_id"] = ObjectId(input.league_id)
        try:
            await db.scoring_configs.insert_one(config_doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Scoring changed since you loaded it. Reload the saved settings before trying again.")
    return {"message": "Scoring config saved", "revision": config_doc["revision"]}


@router.get("/scoring/config")
async def get_scoring_config(league_id: str, request: Request):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await require_league_member(db, user, league_id)
    config = await db.scoring_configs.find_one({"league_id": league_id})
    if not config:
        return {
            "league_id": league_id,
            "revision": 0,
            "skater_scoring": DEFAULT_SKATER_SCORING,
            "goalie_scoring": DEFAULT_GOALIE_SCORING,
            "roto_categories": ["goals", "assists", "plus_minus", "power_play_points", "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts"]
        }
    config["_id"] = str(config["_id"])
    return config


@router.get("/scoring/calculate/{league_id}")
async def calculate_league_scoring(league_id: str, request: Request, week: Optional[int] = None):
    """Calculate fantasy points for all teams in a league.

    Uses game-level ownership allocation: each game's stats are credited
    only to the team that owned the player at puck-drop, and only if the
    player was in an active lineup position at that time.

    Accepts optional `?week=N` to compute for a specific week.
    """
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await require_league_member(db, user, league_id)
    config = await db.scoring_configs.find_one({"league_id": league_id})
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if week is None:
        week = int(league.get("current_week") or 1)

    from utils.scoring_roster import week_to_time_range
    from utils.game_allocation import allocate_team_period_fpts

    period_start, period_end = week_to_time_range(league, week)
    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    results = []
    for team in teams:
        tid = str(team["_id"])
        if period_start and period_end:
            alloc = await allocate_team_period_fpts(
                db, tid, league_id, period_start, period_end, config,
            )
            total_fpts = alloc["total_fpts"]
            game_count = alloc["game_count"]
        else:
            # No season_start_date → fall back to aggregate scoring
            calculate_fantasy_points = _deps["calculate_fantasy_points"]
            total_fpts = 0.0
            game_count = 0
            for pid in (team.get("roster") or []):
                player = await db.players.find_one({"_id": ObjectId(pid)})
                if player:
                    total_fpts += calculate_fantasy_points(player, config)

        results.append({
            "team_id": tid,
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "roster_size": len(team.get("roster") or []),
            "total_fantasy_points": round(total_fpts, 1),
            "game_count": game_count,
        })

    results.sort(key=lambda t: -t["total_fantasy_points"])
    return results


@router.get("/scoring/roto/{league_id}")
async def calculate_roto_standings(league_id: str, request: Request, week: Optional[int] = None):
    """Calculate rotisserie standings across selected categories.

    Uses game-level ownership allocation for each category stat.
    Accepts optional `?week=N` for historical recomputation.
    """
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await require_league_member(db, user, league_id)
    config = await db.scoring_configs.find_one({"league_id": league_id})
    categories = (config or {}).get("roto_categories", [
        "goals", "assists", "plus_minus", "power_play_points",
        "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts"
    ])
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if week is None:
        week = int(league.get("current_week") or 1)

    from utils.scoring_roster import week_to_time_range
    from utils.game_allocation import allocate_team_period_roto_stats

    period_start, period_end = week_to_time_range(league, week)
    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    team_stats = []
    for team in teams:
        tid = str(team["_id"])
        if period_start and period_end:
            stats = await allocate_team_period_roto_stats(
                db, tid, league_id, period_start, period_end, categories,
            )
        else:
            stats = {cat: 0 for cat in categories}
            for pid in (team.get("roster") or []):
                player = await db.players.find_one({"_id": ObjectId(pid)})
                if player:
                    for cat in categories:
                        stats[cat] += player.get(cat, 0)

        team_stats.append({
            "team_id": tid,
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "stats": stats,
            "roto_points": 0,
        })

    num_teams = len(team_stats)
    for cat in categories:
        reverse = cat not in ["goals_against_avg", "penalty_minutes"]
        sorted_teams = sorted(team_stats, key=lambda t: t["stats"][cat], reverse=reverse)
        for rank, ts in enumerate(sorted_teams):
            ts["roto_points"] += num_teams - rank

    team_stats.sort(key=lambda t: -t["roto_points"])

    return {"categories": categories, "standings": team_stats}

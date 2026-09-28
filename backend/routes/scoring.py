"""Scoring config + calculate + ROTO standings. Extracted from server.py
during Iter 108 server-extraction sweep. Endpoints/payloads/auth identical
to the pre-extraction implementation.
"""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routes.league_guards import require_league_member


DEFAULT_SKATER_SCORING = {
    "goals": 3, "assists": 2, "plus_minus": 1, "penalty_minutes": -0.5,
    "power_play_goals": 1, "power_play_points": 0.5,
    "short_handed_goals": 2, "short_handed_points": 1,
    "game_winning_goals": 1, "shots": 0.5,
}

DEFAULT_GOALIE_SCORING = {
    "wins": 5, "losses": -2, "saves": 0.2, "goals_against": -1,
    "shutouts": 3, "overtime_losses": 0,
}

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class ScoringConfigCreate(BaseModel):
    league_id: str
    skater_scoring: dict
    goalie_scoring: dict
    roto_categories: list = []


@router.post("/scoring/config")
async def save_scoring_config(input: ScoringConfigCreate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can update scoring")

    config_doc = {
        "league_id": input.league_id,
        "skater_scoring": input.skater_scoring,
        "goalie_scoring": input.goalie_scoring,
        "roto_categories": input.roto_categories,
        "updated_by": user["_id"],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.scoring_configs.update_one(
        {"league_id": input.league_id},
        {"$set": config_doc},
        upsert=True
    )

    return {"message": "Scoring config saved"}


@router.get("/scoring/config")
async def get_scoring_config(league_id: str, request: Request):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await require_league_member(db, user, league_id)
    config = await db.scoring_configs.find_one({"league_id": league_id})
    if not config:
        return {
            "league_id": league_id,
            "skater_scoring": DEFAULT_SKATER_SCORING,
            "goalie_scoring": DEFAULT_GOALIE_SCORING,
            "roto_categories": ["goals", "assists", "plus_minus", "power_play_points", "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts"]
        }
    config["_id"] = str(config["_id"])
    return config


@router.get("/scoring/calculate/{league_id}")
async def calculate_league_scoring(league_id: str, request: Request):
    """Calculate fantasy points for all teams in a league."""
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await require_league_member(db, user, league_id)
    calculate_fantasy_points = _deps["calculate_fantasy_points"]
    config = await db.scoring_configs.find_one({"league_id": league_id})
    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    # Use historical scoring roster when a current_week is known.
    from utils.scoring_roster import get_scoring_roster, ensure_scoring_roster
    league = await db.leagues.find_one({"_id": ObjectId(league_id)}, {"current_week": 1})
    week = int((league or {}).get("current_week") or 0) or None

    results = []
    for team in teams:
        total_fpts = 0.0
        tid = str(team["_id"])
        roster = await get_scoring_roster(db, tid, league_id, week)
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total_fpts += calculate_fantasy_points(player, config)

        results.append({
            "team_id": tid,
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "roster_size": len(roster),
            "total_fantasy_points": round(total_fpts, 1)
        })

    results.sort(key=lambda t: -t["total_fantasy_points"])

    return results


@router.get("/scoring/roto/{league_id}")
async def calculate_roto_standings(league_id: str, request: Request):
    """Calculate rotisserie standings across selected categories."""
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await require_league_member(db, user, league_id)
    config = await db.scoring_configs.find_one({"league_id": league_id})
    categories = (config or {}).get("roto_categories", [
        "goals", "assists", "plus_minus", "power_play_points",
        "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts"
    ])

    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    from utils.scoring_roster import get_scoring_roster
    league = await db.leagues.find_one({"_id": ObjectId(league_id)}, {"current_week": 1})
    week = int((league or {}).get("current_week") or 0) or None

    team_stats = []
    for team in teams:
        stats = {cat: 0 for cat in categories}
        tid = str(team["_id"])
        roster = await get_scoring_roster(db, tid, league_id, week)
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                for cat in categories:
                    stats[cat] += player.get(cat, 0)

        team_stats.append({
            "team_id": tid,
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "stats": stats,
            "roto_points": 0
        })

    num_teams = len(team_stats)
    for cat in categories:
        reverse = cat not in ["goals_against_avg", "penalty_minutes"]
        sorted_teams = sorted(team_stats, key=lambda t: t["stats"][cat], reverse=reverse)
        for rank, ts in enumerate(sorted_teams):
            ts["roto_points"] += num_teams - rank

    team_stats.sort(key=lambda t: -t["roto_points"])

    return {"categories": categories, "standings": team_stats}

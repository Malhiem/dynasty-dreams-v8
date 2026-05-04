"""Users router: /users/me/week-at-a-glance, /users/me/level, /u/{username}."""
import re
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}

LEVEL_TITLES = [
    (1, 5, "Bench Warmer"),
    (6, 15, "Rink Regular"),
    (16, 30, "Line Captain"),
    (31, 50, "Hat Trick Hero"),
    (51, 75, "Playoff Contender"),
    (76, 999, "Stanley Cup Dynasty"),
]


def _title_for_level(level: int) -> str:
    for lo, hi, title in LEVEL_TITLES:
        if lo <= level <= hi:
            return title
    return "Rookie"


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/users/me/week-at-a-glance")
async def get_my_week_at_a_glance(request: Request):
    """Week-at-a-glance for every team owned by the current user."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    get_team_week_summary = _deps["get_team_week_summary"]

    user = await get_current_user(request)
    teams = await db.teams.find(
        {"owner_id": user["_id"]},
        {"_id": 1, "league_id": 1, "name": 1},
    ).to_list(50)
    if not teams:
        return {"summaries": []}
    summaries = []
    for t in teams:
        try:
            res = await get_team_week_summary(str(t["_id"]), request)
            summaries.append(res)
        except HTTPException:
            continue
    return {"summaries": summaries}


@router.get("/users/me/level")
async def get_my_level(request: Request):
    """Yahoo-style fantasy level based on career activity."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]

    user = await get_current_user(request)
    user_id = user["_id"]

    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    total_team_count = len(teams)
    total_wins = sum(t.get("wins", 0) or 0 for t in teams)
    total_points_for = sum(t.get("points_for", 0.0) or 0.0 for t in teams)
    total_live_points = sum(t.get("live_points", 0.0) or 0.0 for t in teams)

    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": [str(t["_id"]) for t in teams]},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": [str(t["_id"]) for t in teams]},
    }) if teams else 0

    xp = int(
        total_team_count * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + (total_points_for + total_live_points) / 5
    )

    level = 1
    xp_remaining = xp
    while True:
        cost = 100 + level * 50
        if xp_remaining < cost:
            break
        xp_remaining -= cost
        level += 1
    xp_to_next = (100 + level * 50) - xp_remaining

    return {
        "user_id": str(user_id),
        "level": level,
        "title": _title_for_level(level),
        "xp_total": xp,
        "xp_in_level": xp_remaining,
        "xp_to_next_level": xp_to_next,
        "xp_required_for_next": 100 + level * 50,
        "progress_pct": round((xp_remaining / (100 + level * 50)) * 100, 1),
        "stats": {
            "teams_managed": total_team_count,
            "total_wins": total_wins,
            "trades_accepted": trades_executed,
            "drafts_completed": drafts_completed,
            "waiver_claims": waiver_claims,
            "total_points_for": round(total_points_for + total_live_points, 2),
        },
    }


@router.get("/u/{username}")
async def get_public_profile(username: str):
    """Shareable public profile snapshot."""
    db = _deps["db"]
    username = username.strip()
    user = await db.users.find_one(
        {"username": {"$regex": f"^{re.escape(username)}$", "$options": "i"}},
        {"password_hash": 0},
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = str(user["_id"])

    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    league_ids = list({t["league_id"] for t in teams})
    leagues = await db.leagues.find(
        {"_id": {"$in": [ObjectId(lid) for lid in league_ids]}}
    ).to_list(100)
    leagues_by_id = {str(l["_id"]): l for l in leagues}

    team_cards = []
    trophies = []
    championships_won = 0
    division_titles = 0
    conference_titles = 0
    consolations_won = 0
    playoff_appearances = 0
    total_wins = total_losses = total_ties = 0
    total_points_for = 0.0

    for t in teams:
        lg = leagues_by_id.get(t["league_id"]) or {}
        league_teams = await db.teams.find(
            {"league_id": t["league_id"]},
            {"_id": 1, "points_for": 1, "live_points": 1},
        ).to_list(100)
        ranked = sorted(
            league_teams,
            key=lambda x: (x.get("points_for", 0.0) or 0.0) + (x.get("live_points", 0.0) or 0.0),
            reverse=True,
        )
        rank = next((i + 1 for i, x in enumerate(ranked) if x["_id"] == t["_id"]), None)

        total_wins += t.get("wins", 0) or 0
        total_losses += t.get("losses", 0) or 0
        total_ties += t.get("ties", 0) or 0
        total_points_for += (t.get("points_for", 0.0) or 0.0) + (t.get("live_points", 0.0) or 0.0)

        champ_at = t.get("championship_won_at")
        div_at = t.get("division_winner_at")
        conf_at = t.get("conference_winner_at")
        cons_at = t.get("consolation_won_at")
        playoffs_at = t.get("playoffs_reached_at")
        if champ_at: championships_won += 1
        if div_at: division_titles += 1
        if conf_at: conference_titles += 1
        if cons_at: consolations_won += 1
        if playoffs_at: playoff_appearances += 1

        team_cards.append({
            "team_id": str(t["_id"]),
            "team_name": t["name"],
            "league_id": t["league_id"],
            "league_name": lg.get("name", "Unknown league"),
            "league_format": lg.get("format"),
            "league_sport": lg.get("sport", "nhl"),
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": round((t.get("points_for", 0.0) or 0.0) + (t.get("live_points", 0.0) or 0.0), 2),
            "rank": rank,
            "total_teams": len(league_teams),
            "live_points": round(t.get("live_points", 0.0) or 0.0, 2),
            "championship_won_at": champ_at,
            "division_winner_at": div_at,
            "conference_winner_at": conf_at,
            "consolation_won_at": cons_at,
            "playoffs_reached_at": playoffs_at,
        })

        if champ_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "League Champion",
                "type": "championship", "earned_at": champ_at,
            })
        if conf_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "Conference Champion",
                "type": "conference", "earned_at": conf_at,
            })
        if div_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "Division Champion",
                "type": "division", "earned_at": div_at,
            })
        if cons_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "Consolation Winner",
                "type": "consolation", "earned_at": cons_at,
            })

        if rank == 1:
            trophies.append({
                "league_id": t["league_id"],
                "league_name": lg.get("name"),
                "team_name": t["name"],
                "label": "1st Place (current)",
                "type": "lead",
            })
        elif rank and rank <= 3:
            trophies.append({
                "league_id": t["league_id"],
                "league_name": lg.get("name"),
                "team_name": t["name"],
                "label": f"Top 3 (#{rank})",
                "type": "top3",
            })

    lifetime_best: Optional[dict] = None
    if teams:
        from live_scoring_worker import _fantasy_points_from_live
        roster_ids = set()
        for t in teams:
            roster_ids.update(t.get("roster") or [])
        if roster_ids:
            players = await db.players.find(
                {"_id": {"$in": [ObjectId(p) for p in list(roster_ids)[:500]]}},
                {"name": 1, "team": 1, "position": 1, "player_type": 1, "live_stats": 1},
            ).to_list(500)
            for p in players:
                is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
                for _gid, ls in (p.get("live_stats") or {}).items():
                    fpts = _fantasy_points_from_live(ls, is_g)
                    if not lifetime_best or fpts > lifetime_best["fpts"]:
                        lifetime_best = {
                            "id": str(p["_id"]),
                            "name": p.get("name"),
                            "team": p.get("team"),
                            "position": p.get("position"),
                            "is_goalie": is_g,
                            "goals": ls.get("goals", 0) or 0,
                            "assists": ls.get("assists", 0) or 0,
                            "shots": ls.get("shots", 0) or 0,
                            "saves": ls.get("saves", 0) or 0,
                            "goals_against": ls.get("goals_against", 0) or 0,
                            "fpts": round(fpts, 2),
                        }

    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": [str(t["_id"]) for t in teams]},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": [str(t["_id"]) for t in teams]},
    }) if teams else 0

    xp = int(
        len(teams) * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + total_points_for / 5
        + championships_won * 500
        + conference_titles * 250
        + division_titles * 150
        + consolations_won * 100
        + playoff_appearances * 75
    )
    level = 1
    xp_rem = xp
    while True:
        cost = 100 + level * 50
        if xp_rem < cost:
            break
        xp_rem -= cost
        level += 1

    return {
        "username": user.get("username"),
        "display_name": user.get("name") or user.get("username"),
        "member_since": user.get("created_at"),
        "level": level,
        "title": _title_for_level(level),
        "xp_in_level": xp_rem,
        "xp_required_for_next": 100 + level * 50,
        "progress_pct": round((xp_rem / (100 + level * 50)) * 100, 1),
        "stats": {
            "leagues_joined": len(teams),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_ties": total_ties,
            "total_points": round(total_points_for, 2),
            "trades_accepted": trades_executed,
            "drafts_completed": drafts_completed,
            "waiver_claims": waiver_claims,
            "championships_won": championships_won,
            "conference_titles": conference_titles,
            "division_titles": division_titles,
            "consolations_won": consolations_won,
            "playoff_appearances": playoff_appearances,
        },
        "teams": team_cards,
        "trophies": trophies,
        "lifetime_top_performer": lifetime_best,
    }

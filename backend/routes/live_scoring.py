"""Live scoring: poll summary, manual refresh, per-team + per-league live points,
weekly summary card. Extracted from server.py during Iter 108 server-extraction
sweep — all endpoints/payloads/auth identical to the pre-extraction implementation.
"""
from datetime import datetime, timezone, timedelta

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from routes.league_guards import require_league_member, verify_team_in_league

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/live-scoring")
async def get_live_scoring(request: Request):
    """Return latest live-scoring summary (today's games + poll timestamp)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    await get_current_user(request)
    state = await db.system_state.find_one({"_id": "live_scoring"}, {"_id": 0})
    if not state or not state.get("latest"):
        return {"date": None, "games": [], "games_processed": 0, "playoff_games": 0, "players_updated": 0, "polled_at": None}
    return state["latest"]


@router.post("/live-scoring/refresh")
async def refresh_live_scoring(request: Request):
    """Trigger an immediate live-scoring poll (manual refresh button).
    Rate-limited to 1 request per user per 20 seconds to avoid NHL API abuse."""
    db = _deps["db"]
    sio = _deps["sio"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)

    # Per-user 20s cooldown
    last = await db.rate_limits.find_one({"_id": f"live_refresh:{user['_id']}"})
    if last and last.get("at"):
        last_at = last["at"]
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        elapsed = (now - last_at).total_seconds()
        if elapsed < 20:
            raise HTTPException(
                status_code=429,
                detail=f"Too many refreshes. Try again in {max(1, 20 - int(elapsed))}s.",
            )

    await db.rate_limits.update_one(
        {"_id": f"live_refresh:{user['_id']}"},
        {"$set": {"at": now}},
        upsert=True,
    )

    from live_scoring_worker import run_once
    summary = await run_once(db, sio)
    return summary


@router.get("/live-scoring/team/{team_id}")
async def get_team_live_scoring(team_id: str, request: Request):
    """Per-team live fantasy points + per-player playoff stat lines."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    await require_league_member(db, user, team["league_id"])

    # Use historical scoring roster for consistency
    from utils.scoring_roster import get_scoring_roster
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])}, {"current_week": 1})
    week = int((league or {}).get("current_week") or 0) or None
    roster_ids = await get_scoring_roster(db, team_id, team["league_id"], week)
    if not roster_ids:
        return {"team_id": team_id, "team_name": team["name"], "live_points": 0.0, "players": []}

    players = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
        {"nhl_id": 1, "name": 1, "team": 1, "position": 1, "player_type": 1, "live_stats": 1},
    ).to_list(100)

    from live_scoring_worker import _fantasy_points_from_live

    def aggregate(p):
        is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
        live = p.get("live_stats") or {}
        agg = {"goals": 0, "assists": 0, "shots": 0, "points": 0,
               "saves": 0, "goals_against": 0, "wins": 0, "games": 0,
               "fpts": 0.0, "last_game_state": None}
        for gid, ls in live.items():
            agg["games"] += 1
            agg["goals"] += ls.get("goals", 0) or 0
            agg["assists"] += ls.get("assists", 0) or 0
            agg["shots"] += ls.get("shots", 0) or 0
            agg["saves"] += ls.get("saves", 0) or 0
            agg["goals_against"] += ls.get("goals_against", 0) or 0
            agg["wins"] += ls.get("wins", 0) or 0
            agg["fpts"] += _fantasy_points_from_live(ls, is_g)
            agg["last_game_state"] = ls.get("game_state")
        agg["points"] = agg["goals"] + agg["assists"]
        agg["fpts"] = round(agg["fpts"], 2)
        return agg

    player_rows = []
    for p in players:
        agg = aggregate(p)
        player_rows.append({
            "id": str(p["_id"]),
            "nhl_id": p.get("nhl_id"),
            "name": p.get("name"),
            "team": p.get("team"),
            "position": p.get("position"),
            "is_goalie": p.get("player_type") == "goalie" or p.get("position") == "G",
            **agg,
        })
    player_rows.sort(key=lambda r: r["fpts"], reverse=True)
    total = round(sum(r["fpts"] for r in player_rows), 2)

    return {
        "team_id": team_id,
        "team_name": team["name"],
        "league_id": team.get("league_id"),
        "live_points": total,
        "players": player_rows,
    }


@router.get("/live-scoring/league/{league_id}")
async def get_league_live_scoring(league_id: str, request: Request):
    """League-wide leaderboard of team live points.

    Enriched with `preweek_projection` / `projection_delta` / `matchup_id` /
    `projected_rank_change` so the /live page can render the variance arrows
    and projected-rank movement chips. See server.py git history for the full
    rationale.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    await require_league_member(db, user, league_id)
    _ = _safe_object_id(league_id, "league_id")

    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "owner_name": 1, "live_points": 1, "roster": 1,
         "points_for": 1, "wins": 1, "losses": 1, "ties": 1,
         "preweek_projections": 1},
    ).to_list(200)

    tid_to_live = {str(t["_id"]): float(t.get("live_points", 0.0) or 0.0) for t in teams}

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    cur_week = int((league or {}).get("current_week", 1) or 1)
    matchups = await db.matchups.find({"league_id": league_id, "week": cur_week}).to_list(50)
    opp_map: dict = {}
    matchup_map: dict = {}
    for m in matchups:
        hid = m.get("home_team_id"); aid = m.get("away_team_id")
        mid = str(m.get("_id"))
        if hid and aid:
            opp_map[hid] = aid
            opp_map[aid] = hid
            matchup_map[hid] = mid
            matchup_map[aid] = mid

    async def preweek_proj(t: dict) -> float:
        cache_key = f"week_{cur_week}"
        cached = (t.get("preweek_projections") or {}).get(cache_key)
        if cached is not None:
            return float(cached)
        games_played = int(t.get("wins", 0) or 0) + int(t.get("losses", 0) or 0) + int(t.get("ties", 0) or 0)
        pf = float(t.get("points_for") or 0.0)
        if games_played >= 1 and pf > 0:
            avg = pf / games_played
            if avg > 400.0:
                avg = 120.0
        else:
            avg = 120.0
        proj = max(60.0, min(300.0, round(avg, 1)))
        await db.teams.update_one(
            {"_id": t["_id"]},
            {"$set": {f"preweek_projections.{cache_key}": proj}},
        )
        return proj

    pre_rank = {
        r["team_id"]: idx + 1 for idx, r in enumerate(
            sorted(
                [{"team_id": str(t["_id"]), "pre": float(t.get("points_for", 0) or 0)} for t in teams],
                key=lambda x: x["pre"], reverse=True,
            )
        )
    }
    proj_rank = {
        r["team_id"]: idx + 1 for idx, r in enumerate(
            sorted(
                [
                    {
                        "team_id": str(t["_id"]),
                        "post": float(t.get("points_for", 0) or 0) + float(t.get("live_points", 0) or 0),
                    }
                    for t in teams
                ],
                key=lambda x: x["post"], reverse=True,
            )
        )
    }

    rows = []
    for t in teams:
        tid = str(t["_id"])
        opp_id = opp_map.get(tid)
        lp_against = round(tid_to_live.get(opp_id, 0.0), 2) if opp_id else None
        pre = pre_rank.get(tid, 0)
        post = proj_rank.get(tid, 0)
        delta = (pre - post) if (pre and post) else 0
        projection = await preweek_proj(t)
        live_pts = round(t.get("live_points", 0.0) or 0.0, 2)
        rows.append({
            "team_id": tid,
            "team_name": t["name"],
            "owner_name": t.get("owner_name"),
            "live_points": live_pts,
            "live_points_against": lp_against,
            "preweek_projection": projection,
            "projection_delta": round(live_pts - projection, 2),
            "opponent_team_id": opp_id,
            "matchup_id": matchup_map.get(tid),
            "roster_count": len(t.get("roster", [])),
            "pre_rank": pre,
            "projected_rank": post,
            "projected_rank_change": delta,
        })
    rows.sort(key=lambda r: r["live_points"], reverse=True)
    return {"league_id": league_id, "leaderboard": rows}


@router.get("/live-scoring/team/{team_id}/week")
async def get_team_week_summary(team_id: str, request: Request):
    """Return weekly/daily/top-performer/rank-delta summary for a team."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    await require_league_member(db, user, team["league_id"])

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])}, {"name": 1, "scoring_format": 1})

    roster_ids = team.get("roster") or []
    if not roster_ids:
        return {
            "team_id": team_id,
            "team_name": team["name"],
            "league_id": team["league_id"],
            "league_name": league.get("name") if league else None,
            "daily_fpts": 0.0,
            "weekly_fpts": 0.0,
            "top_performer": None,
            "rank": None,
            "rank_delta": 0,
        }

    from live_scoring_worker import _fantasy_points_from_live
    players = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
        {"name": 1, "position": 1, "player_type": 1, "team": 1, "live_stats": 1},
    ).to_list(100)

    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=24)
    week_start = now - timedelta(days=7)

    daily_total = 0.0
    weekly_total = 0.0
    top_today = None

    for p in players:
        is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
        for _gid, ls in (p.get("live_stats") or {}).items():
            updated = ls.get("updated_at")
            if not updated:
                continue
            if isinstance(updated, str):
                try:
                    updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                except Exception:
                    continue
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            fpts = _fantasy_points_from_live(ls, is_g)

            if updated >= week_start:
                weekly_total += fpts
            if updated >= day_start:
                daily_total += fpts
                if not top_today or fpts > top_today["fpts"]:
                    top_today = {
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
                        "shutouts": ls.get("shutouts", 0) or 0,
                        "decision": ls.get("decision"),
                        "fpts": round(fpts, 2),
                    }

    all_teams = await db.teams.find(
        {"league_id": team["league_id"]},
        {"_id": 1, "live_points": 1},
    ).to_list(100)
    ranked = sorted(all_teams, key=lambda t: t.get("live_points", 0.0) or 0.0, reverse=True)
    current_rank = next((i + 1 for i, t in enumerate(ranked) if str(t["_id"]) == team_id), None)

    snapshot = await db.team_rank_snapshots.find_one({
        "league_id": team["league_id"],
        "team_id": team_id,
    })
    rank_delta = 0
    if snapshot and current_rank:
        prev_rank = snapshot.get("rank")
        if prev_rank:
            rank_delta = prev_rank - current_rank

    needs_update = not snapshot
    if snapshot and snapshot.get("updated_at"):
        last = snapshot["updated_at"]
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        needs_update = (now - last).total_seconds() > 86400
    if needs_update:
        await db.team_rank_snapshots.update_one(
            {"league_id": team["league_id"], "team_id": team_id},
            {"$set": {
                "league_id": team["league_id"],
                "team_id": team_id,
                "rank": current_rank,
                "updated_at": now,
            }},
            upsert=True,
        )

    opponent_info = None
    scoring_format = (league or {}).get("scoring_format", "") or ""
    if "head_to_head" in scoring_format or scoring_format == "h2h":
        cur = await db.matchups.find_one(
            {"league_id": team["league_id"], "status": {"$in": ["scheduled", "in_progress"]}},
            sort=[("week", 1)],
        )
        week_num = cur.get("week") if cur else 1
        pair = await db.matchups.find_one({
            "league_id": team["league_id"],
            "week": week_num,
            "$or": [{"home_team_id": team_id}, {"away_team_id": team_id}],
        })
        if pair:
            opp_id = pair["away_team_id"] if pair["home_team_id"] == team_id else pair["home_team_id"]
            opp_name = pair["away_team_name"] if pair["home_team_id"] == team_id else pair["home_team_name"]
            opp_team = await db.teams.find_one({"_id": ObjectId(opp_id)}) if opp_id else None
            opp_weekly = 0.0
            if opp_team:
                for pid in (opp_team.get("roster", []) or [])[:50]:
                    try:
                        pp = await db.players.find_one({"_id": ObjectId(pid)})
                        if not pp: continue
                        is_g = pp.get("player_type") == "goalie" or pp.get("position") == "G"
                        for gid, gls in (pp.get("live_stats") or {}).items():
                            opp_weekly += _fantasy_points_from_live(gls, is_g)
                    except Exception:
                        pass
            opponent_info = {
                "opponent_team_id": opp_id,
                "opponent_team_name": opp_name,
                "opponent_weekly_fpts": round(opp_weekly, 2),
                "week": week_num,
            }

    return {
        "team_id": team_id,
        "team_name": team["name"],
        "league_id": team["league_id"],
        "league_name": league.get("name") if league else None,
        "scoring_format": scoring_format,
        "daily_fpts": round(daily_total, 2),
        "weekly_fpts": round(weekly_total, 2),
        "top_performer": top_today,
        "rank": current_rank,
        "total_teams": len(ranked),
        "rank_delta": rank_delta,
        "opponent": opponent_info,
    }

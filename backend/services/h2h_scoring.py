"""Dated, ownership-aware live matchup totals and category outcomes."""
from utils.game_allocation import allocate_team_period_fpts, allocate_team_period_roto_stats
from utils.scoring_roster import week_to_time_range
from services.schedule_store import season_query, season as schedule_season


async def live_scores(db, league, matchups):
    """Derive only the current open week's scores; preserve closed/future rows."""
    lid = str(league["_id"])
    earliest = await db.matchups.find_one({**season_query(lid, schedule_season(league)), "status": {"$in": ["scheduled", "in_progress"]}}, sort=[("week", 1)])
    if not earliest:
        return matchups
    week = earliest["week"]
    start, end = week_to_time_range(league, week)
    if not start or not end:
        return matchups
    from services.profile_competition import capture_week
    await capture_week(db, lid, [m for m in matchups if m.get('week') == week])
    config = await db.scoring_configs.find_one({"league_id": lid})
    totals = {}
    for matchup in matchups:
        if matchup.get("week") != week or matchup.get("status") not in ("scheduled", "in_progress"):
            continue
        for side in ("home", "away"):
            tid = matchup.get(side + "_team_id")
            if not tid or tid.startswith("open_slot_"):
                continue
            if tid not in totals:
                totals[tid] = (await allocate_team_period_fpts(db, tid, lid, start, end, config))["total_fpts"]
            matchup[side + "_score"] = round(totals[tid], 1)
    return matchups


async def category_result(db, league, home_id, away_id, week):
    from routes.roto import CATEGORY_BY_KEY, DEFAULT_ROTO_CATEGORIES
    start, end = week_to_time_range(league, week)
    categories = league.get("roto_categories") or DEFAULT_ROTO_CATEGORIES
    if start and end:
        home = await allocate_team_period_roto_stats(db, home_id, str(league["_id"]), start, end, categories)
        away = await allocate_team_period_roto_stats(db, away_id, str(league["_id"]), start, end, categories)
    else:
        from routes.roto import _team_stat_totals
        totals = await _team_stat_totals(db, str(league["_id"]), week)
        home = totals.get(home_id, {}).get("stats", {})
        away = totals.get(away_id, {}).get("stats", {})
    results, wins = [], {home_id: 0, away_id: 0}
    for key in categories:
        a, b = home.get(key, 0), away.get(key, 0)
        higher = CATEGORY_BY_KEY.get(key, {}).get("higher_is_better", True)
        winner = None if a == b else home_id if (a > b) == higher else away_id
        if winner:
            wins[winner] += 1
        results.append({"category": key, "home": a, "away": b, "winner": winner})
    winner = None if wins[home_id] == wins[away_id] else max(wins, key=wins.get)
    return {"winner": winner, "home_category_stats": home, "away_category_stats": away,
            "category_results": results, "home_categories_won": wins[home_id],
            "away_categories_won": wins[away_id]}

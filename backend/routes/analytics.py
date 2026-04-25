"""League Analytics: weekly performance + season summary rollups."""
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _current_season() -> str:
    """Default season label following NHL convention: Oct-Dec belongs to that year's season,
    Jan-Sep belongs to the season that started the previous October.
    e.g. Apr 2026 → '2025-26', Nov 2026 → '2026-27'.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.month >= 10:
        return f"{now.year}-{str(now.year + 1)[-2:]}"
    return f"{now.year - 1}-{str(now.year)[-2:]}"


@router.get("/leagues/{league_id}/weekly-analytics")
async def get_weekly_analytics(
    league_id: str,
    team_id: Optional[str] = None,
    season: Optional[str] = None,
):
    """
    Returns per-week + season-aggregate analytics for a league.

    Response:
      {
        "league_id": "...",
        "season": "2025-26",
        "team_id": "...",         # only present when team_id was provided
        "weeks": [{week, pointsFor, pointsAgainst, leagueAvg, wins, losses, ties}],
        "season_summary": {pointsFor, pointsAgainst, leagueAvg, wins, losses, ties, weeks_played},
        "year_over_year": [{season, pointsFor, pointsAgainst, leagueAvg, wins, losses}],
      }
    """
    db = _deps["db"]
    season = season or _current_season()

    league_query: dict = {"league_id": league_id, "season": season}
    if team_id:
        league_query["team_id"] = team_id

    rows = await db.week_summaries.find(league_query).sort("week", 1).to_list(500)

    # Compute league-wide weekly average from ALL teams (independent of team filter)
    league_rows = await db.week_summaries.find(
        {"league_id": league_id, "season": season}
    ).to_list(2000)
    league_avg_by_week: dict = {}
    counts: dict = {}
    for r in league_rows:
        w = r["week"]
        league_avg_by_week[w] = league_avg_by_week.get(w, 0.0) + (r.get("points_for", 0.0) or 0.0)
        counts[w] = counts.get(w, 0) + 1
    for w in league_avg_by_week:
        if counts[w]:
            league_avg_by_week[w] = round(league_avg_by_week[w] / counts[w], 1)

    weeks = []
    if team_id:
        for r in rows:
            weeks.append({
                "week": f"W{r['week']}",
                "weekNum": r["week"],
                "pointsFor": round(r.get("points_for", 0.0), 1),
                "pointsAgainst": round(r.get("points_against", 0.0), 1),
                "leagueAvg": league_avg_by_week.get(r["week"], 0.0),
                "win": bool(r.get("win", False)),
                "loss": bool(r.get("loss", False)),
                "tie": bool(r.get("tie", False)),
            })
    else:
        # When no team filter, return per-week league average + total games played
        seen_weeks = sorted(league_avg_by_week.keys())
        for w in seen_weeks:
            wk_rows = [r for r in league_rows if r["week"] == w]
            total_pf = sum(r.get("points_for", 0.0) or 0.0 for r in wk_rows)
            weeks.append({
                "week": f"W{w}",
                "weekNum": w,
                "pointsFor": round(total_pf, 1),
                "pointsAgainst": round(total_pf, 1),  # league sum mirrors itself
                "leagueAvg": league_avg_by_week.get(w, 0.0),
                "matchups_played": len(wk_rows) // 2,
            })

    # Season summary
    pf = sum(r.get("points_for", 0.0) or 0.0 for r in rows)
    pa = sum(r.get("points_against", 0.0) or 0.0 for r in rows)
    wins = sum(1 for r in rows if r.get("win"))
    losses = sum(1 for r in rows if r.get("loss"))
    ties = sum(1 for r in rows if r.get("tie"))
    league_avg_total = (sum(league_avg_by_week.values()) or 0.0)

    season_summary = {
        "pointsFor": round(pf, 1),
        "pointsAgainst": round(pa, 1),
        "leagueAvg": round(league_avg_total, 1),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "weeks_played": len(rows),
    }

    # Year-over-year — group by season for the same team_id (or league-wide if no team)
    yoy_match: dict = {"league_id": league_id}
    if team_id:
        yoy_match["team_id"] = team_id
    yoy_pipeline = [
        {"$match": yoy_match},
        {"$group": {
            "_id": "$season",
            "pointsFor": {"$sum": "$points_for"},
            "pointsAgainst": {"$sum": "$points_against"},
            "wins": {"$sum": {"$cond": ["$win", 1, 0]}},
            "losses": {"$sum": {"$cond": ["$loss", 1, 0]}},
            "ties": {"$sum": {"$cond": ["$tie", 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    yoy_rows = await db.week_summaries.aggregate(yoy_pipeline).to_list(50)
    year_over_year = [
        {
            "season": r["_id"],
            "pointsFor": round(r.get("pointsFor", 0.0), 1),
            "pointsAgainst": round(r.get("pointsAgainst", 0.0), 1),
            "leagueAvg": 0,  # filled below
            "wins": r.get("wins", 0),
            "losses": r.get("losses", 0),
        }
        for r in yoy_rows
    ]
    # leagueAvg per season = avg points across all teams
    if year_over_year:
        season_avg_pipeline = [
            {"$match": {"league_id": league_id}},
            {"$group": {
                "_id": "$season",
                "league_total": {"$sum": "$points_for"},
                "team_count": {"$addToSet": "$team_id"},
            }},
        ]
        season_avgs = {r["_id"]: r for r in await db.week_summaries.aggregate(season_avg_pipeline).to_list(50)}
        for entry in year_over_year:
            sa = season_avgs.get(entry["season"])
            if sa and sa["team_count"]:
                entry["leagueAvg"] = round(sa["league_total"] / len(sa["team_count"]), 1)

    return {
        "league_id": league_id,
        "season": season,
        "team_id": team_id,
        "weeks": weeks,
        "season_summary": season_summary,
        "year_over_year": year_over_year,
    }


@router.post("/leagues/{league_id}/backfill-week-summaries")
async def backfill_week_summaries(league_id: str, season: Optional[str] = None):
    """Idempotent: scan completed matchups and emit week_summaries rows.
    Used to populate analytics for matchups simulated before the rollup was added.
    """
    db = _deps["db"]
    target_season = season or _current_season()

    matchups = await db.matchups.find({
        "league_id": league_id,
        "status": "completed",
    }).to_list(5000)
    if not matchups:
        raise HTTPException(status_code=404, detail="No completed matchups to backfill")

    written = 0
    inserted = 0
    for m in matchups:
        winner = m.get("winner")
        for side in ("home", "away"):
            team_id = m.get(f"{side}_team_id")
            opp_id = m.get(f"{'away' if side == 'home' else 'home'}_team_id")
            pf = m.get(f"{side}_score", 0.0) or 0.0
            pa = m.get(f"{'away' if side == 'home' else 'home'}_score", 0.0) or 0.0
            if not team_id:
                continue
            doc = {
                "league_id": league_id,
                "season": target_season,
                "week": m["week"],
                "team_id": team_id,
                "team_name": m.get(f"{side}_team_name"),
                "opponent_team_id": opp_id,
                "points_for": float(pf),
                "points_against": float(pa),
                "win": winner == team_id,
                "loss": bool(winner) and winner != team_id,
                "tie": winner is None,
                "matchup_id": str(m["_id"]),
            }
            res = await db.week_summaries.update_one(
                {"league_id": league_id, "season": target_season,
                 "week": m["week"], "team_id": team_id},
                {"$set": doc},
                upsert=True,
            )
            written += 1
            if res.upserted_id is not None:
                inserted += 1
    return {
        "league_id": league_id, "season": target_season,
        "rows_upserted": written, "rows_inserted": inserted,
        "rows_updated": written - inserted,
    }

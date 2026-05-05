"""Season lifecycle + League Health Score.

Tracks per-season snapshots (records, awards, rosters, points) when a
commissioner marks a season complete and renews. Also computes a 0-100
"health score" reflecting how well the league is configured for the year.

Data:
  - league_seasons: { league_id, season_year, status, snapshot_at, completed_by,
                      teams: [...], awards: [...], divisions, schedule_config,
                      salary_cap_config, playoff_config, regular_season_weeks,
                      playoff_weeks }
  - leagues.current_season_year (int, e.g. 2026)
  - leagues.current_season_status: "in_progress" | "complete" | "renewed"
"""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pydantic ────────────────────────────────────────────────
class CompleteSeasonInput(BaseModel):
    season_year: Optional[int] = None  # default = league.current_season_year


class RenewSeasonInput(BaseModel):
    new_season_year: int
    carry_over_settings: bool = True   # copy cap, divisions, schedule_config, playoff_config
    reset_records: bool = True         # zero W/L/T, points_for/points_against


# ─── Helpers ─────────────────────────────────────────────────
async def _league_or_404(league_id: str):
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league


async def _ensure_commish(request: Request, league: dict):
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner only")
    return user


# ─── Health Score ────────────────────────────────────────────
def _compute_health_score(league: dict, teams: list, matchups_by_status: dict) -> dict:
    """Compute a 0-100 score across 6 weighted sections."""
    sections = []

    # 1. Basics — name + format + max_teams configured
    basics_ok = bool(league.get("name")) and bool(league.get("format")) and (league.get("max_teams") or 0) >= 2
    sections.append({
        "key": "basics",
        "label": "Basics",
        "complete": basics_ok,
        "weight": 16,
        "detail": "League name, format, and team count" if basics_ok else "Set name, format, and max teams",
    })

    # 2. Salary Cap — explicitly disabled is OK
    cap_explicit = ("salary_cap_enabled" in league)
    cap_ok = cap_explicit and (
        not league.get("salary_cap_enabled")
        or (league.get("salary_cap") and league.get("salary_cap") > 0)
    )
    sections.append({
        "key": "cap",
        "label": "Salary Cap",
        "complete": cap_ok,
        "weight": 16,
        "detail": (
            "Cap disabled" if cap_explicit and not league.get("salary_cap_enabled")
            else f"Cap ${(league.get('salary_cap') or 0):,.0f}" if cap_ok
            else "Configure cap (or explicitly disable it)"
        ),
    })

    # 3. Divisions — at least 2
    divisions = list({t.get("division") for t in teams if t.get("division")})
    div_ok = len(divisions) >= 2
    sections.append({
        "key": "divisions",
        "label": "Divisions",
        "complete": div_ok,
        "weight": 16,
        "detail": f"{len(divisions)} divisions configured" if div_ok else "Assign teams to ≥ 2 divisions",
    })

    # 4. Schedule generated — at least one matchup exists
    sched_ok = matchups_by_status.get("total", 0) > 0
    sections.append({
        "key": "schedule",
        "label": "Schedule",
        "complete": sched_ok,
        "weight": 17,
        "detail": (
            f"{matchups_by_status.get('total', 0)} matchups generated"
            if sched_ok else "Generate the regular-season schedule"
        ),
    })

    # 5. Playoff configured — playoff_teams set
    playoff_ok = (league.get("playoff_teams") or 0) >= 2
    sections.append({
        "key": "playoffs",
        "label": "Playoffs",
        "complete": playoff_ok,
        "weight": 17,
        "detail": (
            f"{league.get('playoff_teams')}-team bracket"
            if playoff_ok else "Set playoff team count"
        ),
    })

    # 6. Draft scheduled — at least one draft exists
    draft_ok = matchups_by_status.get("draft_count", 0) > 0
    sections.append({
        "key": "draft",
        "label": "Draft",
        "complete": draft_ok,
        "weight": 18,
        "detail": (
            f"{matchups_by_status.get('draft_count', 0)} draft(s) scheduled"
            if draft_ok else "Schedule a draft"
        ),
    })

    score = sum(s["weight"] for s in sections if s["complete"])
    return {
        "score": score,
        "sections": sections,
        "missing": [s["key"] for s in sections if not s["complete"]],
    }


# ─── Endpoints ───────────────────────────────────────────────
@router.get("/leagues/{league_id}/health-score")
async def get_health_score(league_id: str):
    """Return league setup completeness for the current season."""
    db = _deps["db"]
    league = await _league_or_404(league_id)
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    total_matchups = await db.matchups.count_documents({"league_id": league_id})
    drafts = await db.drafts.count_documents({"league_id": league_id})
    health = _compute_health_score(
        league, teams,
        {"total": total_matchups, "draft_count": drafts},
    )
    return {
        "league_id": league_id,
        "current_season_year": league.get("current_season_year") or datetime.now(timezone.utc).year,
        "current_season_status": league.get("current_season_status") or "in_progress",
        **health,
    }


@router.get("/leagues/{league_id}/seasons")
async def list_seasons(league_id: str):
    """List all completed seasons for a league (for History/Trophy Room)."""
    db = _deps["db"]
    await _league_or_404(league_id)
    cursor = db.league_seasons.find(
        {"league_id": league_id},
        {"_id": 1, "season_year": 1, "status": 1, "snapshot_at": 1,
         "champion_team_name": 1, "completed_by": 1},
    ).sort("season_year", -1)
    seasons = []
    async for s in cursor:
        s["id"] = str(s.pop("_id"))
        seasons.append(s)
    return {"seasons": seasons}


@router.get("/leagues/{league_id}/seasons/{season_year}")
async def get_season(league_id: str, season_year: int):
    """Full snapshot of a specific past season."""
    db = _deps["db"]
    await _league_or_404(league_id)
    season = await db.league_seasons.find_one({
        "league_id": league_id, "season_year": season_year,
    })
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    season["id"] = str(season.pop("_id"))
    return season


@router.post("/leagues/{league_id}/complete-season")
async def complete_season(league_id: str, payload: CompleteSeasonInput, request: Request):
    """Snapshot the current season's records, awards, rosters → league_seasons.

    The snapshot becomes the source-of-truth for past performance shown in
    Analytics, League History, Trophy Room, and per-player career stats.

    Idempotent within a season_year: re-running overwrites the existing snapshot
    (useful if commissioner needs to correct it before renewing).
    """
    db = _deps["db"]
    league = await _league_or_404(league_id)
    user = await _ensure_commish(request, league)

    season_year = payload.season_year or league.get("current_season_year") or datetime.now(timezone.utc).year
    now = datetime.now(timezone.utc)

    teams = await db.teams.find({"league_id": league_id}).to_list(200)

    # Snapshot teams' end-of-season records + roster + awards
    teams_snapshot = []
    champion = None
    for t in teams:
        owner = await db.users.find_one(
            {"_id": t.get("owner_id")},
            {"username": 1, "name": 1},
        ) if t.get("owner_id") else None
        ts = {
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "logo_abbr": t.get("logo_abbr"),
            "logo_url": t.get("logo_url"),
            "owner_id": t.get("owner_id"),
            "owner_username": (owner or {}).get("username"),
            "owner_name": (owner or {}).get("name"),
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": float(t.get("points_for", 0.0) or 0.0),
            "points_against": float(t.get("points_against", 0.0) or 0.0),
            "live_points": float(t.get("live_points", 0.0) or 0.0),
            "division": t.get("division"),
            "conference": t.get("conference"),
            "salary_used": float(t.get("salary_used", 0.0) or 0.0),
            "roster": list(t.get("roster") or []),
            "awards": {
                "championship_won_at": t.get("championship_won_at"),
                "consolation_won_at": t.get("consolation_won_at"),
                "division_winner_at": t.get("division_winner_at"),
                "conference_winner_at": t.get("conference_winner_at"),
                "playoffs_reached_at": t.get("playoffs_reached_at"),
            },
        }
        if t.get("championship_won_at"):
            champion = ts["team_name"]
        teams_snapshot.append(ts)

    # Awards / activity_feed entries from this season
    activity_cursor = db.activity_feed.find({
        "league_id": league_id,
        "event_type": {"$in": [
            "championship_awarded", "division_awarded",
            "conference_awarded", "consolation_awarded",
        ]},
    }).sort("created_at", -1)
    awards = []
    async for a in activity_cursor:
        awards.append({
            "event_type": a.get("event_type"),
            "description": a.get("description"),
            "created_at": a.get("created_at"),
        })

    # Player ownership snapshot (so player profiles can show "X% owned by Y team in 2026")
    player_ids = list({pid for t in teams for pid in (t.get("roster") or [])})
    player_snapshot = []
    if player_ids:
        try:
            oids = [ObjectId(p) for p in player_ids if ObjectId.is_valid(p)]
            async for p in db.players.find(
                {"_id": {"$in": oids}},
                {"name": 1, "position": 1, "team": 1, "season_stats": 1},
            ):
                player_snapshot.append({
                    "player_id": str(p["_id"]),
                    "name": p.get("name"),
                    "team": p.get("team"),
                    "position": p.get("position"),
                    "season_stats": p.get("season_stats"),
                })
        except Exception:
            pass

    # Capture league config for "use last year's settings" pre-fill
    snapshot_doc = {
        "league_id": league_id,
        "season_year": season_year,
        "status": "complete",
        "snapshot_at": now,
        "completed_by": user.get("email"),
        "completed_by_name": user.get("name"),
        "champion_team_name": champion,
        "salary_cap_config": {
            "enabled": bool(league.get("salary_cap_enabled")),
            "amount": league.get("salary_cap"),
            "retention_slots": league.get("salary_retention_slots", 3),
        },
        "schedule_config": league.get("schedule_config"),
        "playoff_config": {
            "playoff_teams": league.get("playoff_teams"),
            "playoff_weeks": league.get("playoff_weeks"),
        },
        "regular_season_weeks": league.get("regular_season_weeks"),
        "scoring_format": league.get("scoring_format"),
        "format": league.get("format"),
        "teams": teams_snapshot,
        "awards": awards,
        "players": player_snapshot,
    }

    # Upsert — replay-safe
    await db.league_seasons.update_one(
        {"league_id": league_id, "season_year": season_year},
        {"$set": snapshot_doc},
        upsert=True,
    )

    # Mark league
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "current_season_year": season_year,
            "current_season_status": "complete",
            "season_completed_at": now,
        }, "$push": {"audit_log": {
            "action": "season_completed",
            "by": user.get("email"),
            "season_year": season_year,
            "champion": champion,
        }}},
    )

    return {
        "season_year": season_year,
        "champion": champion,
        "teams_snapshotted": len(teams_snapshot),
        "awards_snapshotted": len(awards),
        "players_snapshotted": len(player_snapshot),
    }


@router.post("/leagues/{league_id}/renew-season")
async def renew_season(league_id: str, payload: RenewSeasonInput, request: Request):
    """Start a new season after the previous one has been marked complete.

    - Optionally carries over cap/divisions/schedule/playoff configs.
    - Optionally resets team W/L/T + points (keeps rosters intact).
    - Bumps `current_season_year` and resets status to "in_progress".
    - Does NOT delete past-season snapshots (those live forever in `league_seasons`).
    """
    db = _deps["db"]
    league = await _league_or_404(league_id)
    user = await _ensure_commish(request, league)

    now = datetime.now(timezone.utc)
    prev_year = league.get("current_season_year") or (datetime.now(timezone.utc).year - 1)
    new_year = payload.new_season_year
    if new_year <= prev_year:
        raise HTTPException(
            status_code=400,
            detail=f"new_season_year ({new_year}) must be greater than current ({prev_year})",
        )

    # Reset team records (keeps rosters)
    if payload.reset_records:
        await db.teams.update_many(
            {"league_id": league_id},
            {"$set": {
                "wins": 0, "losses": 0, "ties": 0,
                "points_for": 0.0, "points_against": 0.0,
                "live_points": 0.0,
            }, "$unset": {
                "championship_won_at": "",
                "division_winner_at": "",
                "conference_winner_at": "",
                "consolation_won_at": "",
                "playoffs_reached_at": "",
                "previous_rank": "",
            }},
        )

    # Wipe matchups for the new season — fresh slate
    await db.matchups.delete_many({"league_id": league_id})

    # Bump league
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "current_season_year": new_year,
            "current_season_status": "in_progress",
            "setup_wizard_complete": False,  # encourage re-running wizard with prefilled values
            "season_renewed_at": now,
        }, "$push": {"audit_log": {
            "action": "season_renewed",
            "by": user.get("email"),
            "from_year": prev_year,
            "to_year": new_year,
            "carry_over_settings": payload.carry_over_settings,
            "reset_records": payload.reset_records,
        }}},
    )

    # Build prefill suggestion
    prev_snapshot = await db.league_seasons.find_one(
        {"league_id": league_id, "season_year": prev_year},
        {"_id": 0},
    )
    suggestions = None
    if prev_snapshot and payload.carry_over_settings:
        suggestions = {
            "salary_cap_config": prev_snapshot.get("salary_cap_config"),
            "schedule_config": prev_snapshot.get("schedule_config"),
            "playoff_config": prev_snapshot.get("playoff_config"),
            "scoring_format": prev_snapshot.get("scoring_format"),
        }

    return {
        "from_year": prev_year,
        "to_year": new_year,
        "reset_records": payload.reset_records,
        "carry_over_settings": payload.carry_over_settings,
        "previous_season_suggestions": suggestions,
    }


@router.get("/leagues/{league_id}/setup-suggestions")
async def get_setup_suggestions(league_id: str):
    """Suggest setup-wizard values based on the most recent completed season.
    Setup wizard pre-fills its inputs from this endpoint (returns null fields
    when no prior season exists).
    """
    db = _deps["db"]
    league = await _league_or_404(league_id)
    cur_year = league.get("current_season_year") or datetime.now(timezone.utc).year
    snap = await db.league_seasons.find_one(
        {"league_id": league_id, "season_year": {"$lt": cur_year}},
        sort=[("season_year", -1)],
    )
    if not snap:
        return {"has_previous_season": False}
    return {
        "has_previous_season": True,
        "previous_season_year": snap.get("season_year"),
        "salary_cap_config": snap.get("salary_cap_config"),
        "schedule_config": snap.get("schedule_config"),
        "playoff_config": snap.get("playoff_config"),
        "scoring_format": snap.get("scoring_format"),
        "champion": snap.get("champion_team_name"),
    }

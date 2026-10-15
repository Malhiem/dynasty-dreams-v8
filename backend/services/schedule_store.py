"""Preview snapshots and transactional activation of validated season schedules."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import OperationFailure, PyMongoError

from services.combined_scheduler import Settings, defaults, protected, validate
from services.scheduler_calendar import can_edit

LEAGUE_FIELDS = ["season", "current_season_year", "season_start_date", "season_end_date", "regular_season_weeks",
                 "matchup_length_days", "matchups_per_week", "opponents_per_matchup_period", "schedule_config",
                 "combined_schedule_settings", "schedule_version", "max_teams", "scoring_format", "commissioner_id",
                 "co_commissioners", "admin_ids", "playoffs_enabled", "playoff_format", "playoff_teams", "playoff_rounds",
                 "playoff_start_week", "playoff_end_week", "playoff_seeding_method", "playoff_custom_matchups",
                 "consolation_enabled", "consolation_teams", "consolation_start_week", "consolation_end_week",
                 "consolation_seeding_method", "consolation_custom_matchups"]
GAME_FIELDS = ["_id", "week", "home_team_id", "away_team_id", "status", "home_score", "away_score", "winner",
               "is_playoff", "is_consolation", "locked", "is_locked", "season"]


def season(league):
    # Keep the existing live matchup season contract, including legacy fallbacks.
    if league.get("season"):
        return str(league["season"])
    if league.get("current_season_year"):
        year = int(league["current_season_year"])
        return f"{year - 1}-{str(year)[-2:]}"
    from routes.analytics import _current_season
    return _current_season()


def season_query(league_id, label):
    return {"league_id": league_id, "$or": [{"season": label}, {"season": None}, {"season": ""}]}


async def context(db, league_id, user, session=None):
    from routes.league_guards import require_league_member
    if session is None:
        league = await require_league_member(db, user, league_id)
    else:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)}, session=session)
        if not league: raise HTTPException(404, "League not found")
    if not can_edit(league, user): raise HTTPException(403, "Only league administrators can generate or apply schedules")
    if league.get("scoring_format") not in ("head_to_head", "h2h-points", "h2h-categories"):
        raise HTTPException(400, "Opponent scheduling requires Head-to-Head scoring")
    teams = await db.teams.find({"league_id": league_id}, session=session).sort("_id", 1).to_list(101)
    if len(teams) > 100:
        raise HTTPException(413, "The scheduler supports at most 100 teams")
    # Synthetic slots retain stable IDs and require explicit structure when group rules apply.
    for slot in range(len(teams) + 1, int(league.get("max_teams") or len(teams)) + 1):
        teams.append({"_id": f"open_slot_{slot}", "name": f"Open Slot {slot}", "is_open_slot": True})
    games = await db.matchups.find(season_query(league_id, season(league)), session=session).sort("_id", 1).to_list(15001)
    if len(games) > 15000:
        raise HTTPException(413, "Too many existing season matchups to safely regenerate")
    regular = [g for g in games if not g.get("is_playoff") and not g.get("is_consolation")]
    locked = [g for g in regular if protected(g)]
    data = {"league": {k: league.get(k) for k in LEAGUE_FIELDS},
            "teams": [{k: t.get(k) for k in ["_id", "name", "division", "conference"]} for t in teams],
            "games": [{k: g.get(k) for k in GAME_FIELDS} for g in games]}
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    return {"league": league, "teams": teams, "games": games, "locked": locked, "fingerprint": fingerprint}


async def preview_document(db, league_id, user, ctx, settings, solved):
    now = datetime.now(timezone.utc)
    doc = {"league_id": league_id, "season": season(ctx["league"]), "created_by": str(user["_id"]),
           "created_at": now, "expires_at": now + timedelta(minutes=30), "fingerprint": ctx["fingerprint"],
           "settings": settings.model_dump(), "games": solved["games"], "validation": solved["validation"], "state": "ready"}
    await db.scheduler_previews.create_index("expires_at", expireAfterSeconds=0)
    saved = await db.scheduler_previews.insert_one(doc)
    return str(saved.inserted_id)


async def apply_preview(db, league_id, preview_id, user):
    try: oid = ObjectId(preview_id)
    except Exception: raise HTTPException(400, "Invalid preview ID")
    # Refuse before any write on standalone Mongo; rollback requires transactions.
    hello = await db.command("hello")
    if not hello.get("setName") and hello.get("msg") != "isdbgrid":
        raise HTTPException(503, "Applying schedules requires MongoDB transaction support (a replica set). Your existing schedule is unchanged.")

    async def activate(session):
        candidate = await db.scheduler_previews.find_one({"_id": oid, "league_id": league_id}, session=session)
        if not candidate: raise HTTPException(404, "Schedule preview not found")
        expires = candidate["expires_at"].replace(tzinfo=timezone.utc)
        if candidate.get("state") != "ready" or expires <= datetime.now(timezone.utc):
            raise HTTPException(409, "This preview was already applied or expired. Generate a fresh preview.")
        ctx = await context(db, league_id, user, session)
        if candidate["fingerprint"] != ctx["fingerprint"]:
            raise HTTPException(409, "League settings, teams, or matchups changed. Generate a fresh preview.")
        settings = Settings.model_validate(candidate["settings"])
        validation = validate(ctx["teams"], settings, candidate["games"], ctx["locked"])
        if not validation["valid"]: raise HTTPException(409, "Preview validation failed; generate a fresh preview")
        # Share write-conflict detection with concurrent settings, team and scoring changes.
        for team in ctx["teams"]:
            if isinstance(team["_id"], ObjectId):
                await db.teams.update_one({"_id": team["_id"]}, {"$inc": {"schedule_context_revision": 1}}, session=session)
        league = ctx["league"]
        version = int(league.get("schedule_version") or 0) + 1
        protected_ids = [g["_id"] for g in ctx["games"] if protected(g)]
        if protected_ids:
            await db.matchups.update_many({"_id": {"$in": protected_ids}}, {"$inc": {"schedule_context_revision": 1}}, session=session)
        bracket_locked = any((g.get("is_playoff") or g.get("is_consolation")) and protected(g) for g in ctx["games"])
        if bracket_locked:
            protected_ids += [g["_id"] for g in ctx["games"] if g.get("is_playoff") or g.get("is_consolation")]
        query = {**season_query(league_id, season(league)), "_id": {"$nin": protected_ids}}
        await db.matchups.delete_many(query, session=session)
        rows = []
        for game in candidate["games"]:
            if game.get("preserved_id"): continue
            rows.append({**game, "league_id": league_id, "season": season(league), "schedule_version": version,
                         "status": "scheduled", "home_score": 0, "away_score": 0, "winner": None,
                         "scoring_format": league.get("scoring_format", "head_to_head")})
        if not bracket_locked:
            from routes.matchups import _build_playoff_bracket
            brackets = _build_playoff_bracket(league, ctx["teams"], is_consolation=False)
            if league.get("consolation_enabled"):
                brackets += _build_playoff_bracket(league, ctx["teams"], is_consolation=True)
            names = {str(t["_id"]): t["name"] for t in ctx["teams"]}
            for row in brackets:
                row.update(league_id=league_id, season=season(league), schedule_version=version,
                           status="scheduled", home_score=0, away_score=0, winner=None,
                           home_team_name=names.get(row.get("home_team_id"), "TBD"),
                           away_team_name=names.get(row.get("away_team_id"), "TBD"), scoring_format=league.get("scoring_format"))
            rows += brackets
        if rows: await db.matchups.insert_many(rows, session=session)
        now = datetime.now(timezone.utc)
        await db.schedule_versions.insert_one({"league_id": league_id, "season": season(league), "version": version,
            "preview_id": preview_id, "settings": settings.model_dump(), "games": candidate["games"],
            "applied_at": now, "applied_by": str(user["_id"])}, session=session)
        await db.leagues.update_one({"_id": league["_id"]}, {"$set": {"schedule_version": version,
            "combined_schedule_settings": settings.model_dump(), "regular_season_weeks": settings.weeks,
            "matchups_per_week": settings.games_per_week, "opponents_per_matchup_period": settings.games_per_week},
            "$push": {"audit_log": {"action": "combined_schedule_applied", "version": version, "by": str(user["_id"]), "at": now.isoformat()}}}, session=session)
        await db.scheduler_previews.update_one({"_id": oid}, {"$set": {"state": "applied", "version": version}}, session=session)
        return {"status": "applied", "version": version, "games": len(candidate["games"]), "preserved_games": len(ctx["locked"])}

    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(activate)
    except HTTPException: raise
    except PyMongoError as exc:
        raise HTTPException(503, "Schedule could not be applied atomically. Existing games are unchanged; retry the preview.") from exc

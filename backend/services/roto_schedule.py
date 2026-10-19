"""Season-scoped Rotisserie calendars and atomic scored elimination rounds."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError
from routes.league_guards import require_league_member
from services.scheduler_calendar import can_edit, season_year
from services.schedule_store import season, season_query


async def transaction(db, commit):
    hello = await db.command("hello")
    if not hello.get("setName") and hello.get("msg") != "isdbgrid":
        raise HTTPException(503, "Rotisserie generation and finalization require MongoDB transaction support")
    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(commit)
    except PyMongoError as exc:
        raise HTTPException(503, "The operation could not be confirmed. Reload and retry; finalized results are safe to repeat.") from exc


class SessionDB:
    """Keep existing scoring helpers in the caller's Motor snapshot transaction."""
    def __init__(self, db, session):
        self.db, self.session = db, session

    def __getattr__(self, name):
        collection = getattr(self.db, name)
        session = self.session
        class Collection:
            def __getattr__(self, method):
                def call(*args, **kwargs):
                    return getattr(collection, method)(*args, **{**kwargs, "session": session})
                return call
        return Collection()


async def authorized(db, league_id, user, session=None):
    league = await require_league_member(db, user, league_id)
    if not can_edit(league, user):
        raise HTTPException(403, "Only league administrators can generate or finalize Rotisserie periods")
    if league.get("scoring_format") != "rotisserie":
        raise HTTPException(400, "This workflow requires Rotisserie scoring")
    return league


def calendar(league, weeks=None):
    """Use saved dates when present; otherwise use explicitly configured league dates."""
    enabled = bool(league.get("playoffs_enabled") and league.get("roto_playoffs_enabled"))
    saved = (league.get("scheduler_calendars") or {}).get(str(season_year(league)))
    if saved:
        regular = [{"id": i + 1, "startDate": p["startDate"], "endDate": p["endDate"], "type": "regular"}
                   for i, p in enumerate(saved.get("regularPeriods") or [])]
        playoff = [{"id": len(regular) + i + 1, "startDate": p["startDate"], "endDate": p["endDate"], "type": "playoff"}
                   for i, p in enumerate(saved.get("playoffPeriods") or [])] if enabled else []
    else:
        try:
            start = date.fromisoformat(str(league.get("season_start_date") or league.get("stats_count_start_date"))[:10])
            count = int(weeks or league.get("regular_season_weeks") or 0)
            length = int(league.get("matchup_length_days") or 7)
            if not 1 <= count <= 52 or not 1 <= length <= 31: raise ValueError()
            cadence = int(league.get("roto_period_length_weeks", 1))
            if not 0 <= cadence <= 52: raise ValueError()
            step = cadence or count
            regular = [{"id": first, "startDate": (start + timedelta(days=(first-1)*length)).isoformat(),
                        "endDate": (start + timedelta(days=min(count, first+step-1)*length-1)).isoformat(), "type": "regular"}
                       for first in range(1, count+1, step)]
            playoff = []
            if enabled:
                first, last = int(league.get("playoff_start_week") or 0), int(league.get("playoff_end_week") or 0)
                if first <= count or not first <= last <= 52: raise ValueError()
                playoff = [{"id": w, "startDate": (start+timedelta(days=(w-1)*length)).isoformat(),
                            "endDate": (start+timedelta(days=w*length-1)).isoformat(), "type": "playoff"} for w in range(first,last+1)]
        except (ValueError, TypeError):
            raise HTTPException(400, "Configure valid season dates, regular periods and a non-overlapping playoff window first")
    if not regular:
        raise HTTPException(400, "Generate and save regular scoring periods first")
    rows = regular + playoff
    if len(rows) > 366: raise HTTPException(400, "A season supports at most 366 scoring periods")
    previous = None
    for p in rows:
        try: start, end = date.fromisoformat(p["startDate"]), date.fromisoformat(p["endDate"])
        except (ValueError, TypeError): raise HTTPException(400, "Scoring period dates are invalid")
        if end < start or (previous and start <= previous):
            raise HTTPException(400, "Scoring periods must be ordered without overlaps")
        previous = end
    limit = league.get("season_end_date") or league.get("stats_count_end_date")
    if limit and rows[-1]["endDate"] > str(limit)[:10]:
        raise HTTPException(400, "Scoring periods extend beyond the configured season end")
    return rows


async def generate(db, league_id, user, weeks=None):
    await authorized(db, league_id, user)
    async def commit(session):
        tx = SessionDB(db, session)
        league = await authorized(tx, league_id, user)
        periods = calendar(league, weeks)
        label = season(league)
        key = f"{league_id}:{label}"
        teams = await tx.teams.find({"league_id": league_id}).sort("_id", 1).to_list(101)
        if not 2 <= len(teams) <= 100: raise HTTPException(400, "A Rotisserie season requires 2–100 actual teams")
        config = {k: league.get(k) for k in ("roto_categories", "roto_tiebreak", "playoff_format", "playoff_teams", "playoff_seeding_method", "playoff_roto_seed_bonuses", "playoff_roto_fresh_totals")}
        signature = hashlib.sha256(json.dumps({"periods": periods, "teams": [str(t["_id"]) for t in teams], "config": config}, sort_keys=True).encode()).hexdigest()
        prior = await tx.roto_schedules.find_one({"_id": key})
        if prior and prior["signature"] == signature:
            return {**prior["response"], "reused": True}
        from services.combined_scheduler import protected
        existing_games = await tx.matchups.find(season_query(league_id,label)).to_list(15001)
        if any(protected(g) for g in existing_games): raise HTTPException(409, "Locked or scored matchups cannot be replaced")
        if await tx.roto_period_results.find_one({**season_query(league_id,label), "closed": True}) or await tx.matchups.find_one({**season_query(league_id,label), "status": {"$in": ["completed", "final", "live", "in_progress"]}}):
            raise HTTPException(409, "Scoring has started; finalized season dates and brackets cannot be replaced")
        if league.get("current_season_status") == "complete": raise HTTPException(409, "Renew the completed season before generating another calendar")
        await tx.leagues.update_one({"_id": league["_id"]}, {"$set": {"roto_scoring_periods": periods, "roto_generated_history": True}, "$inc": {"roto_schedule_version": 1}})
        # Generation creates dated templates, not live results. Seeds are established
        # from finalized regular Roto points when round one is finalized.
        ranked = teams
        seeds = {str(t["_id"]): i+1 for i,t in enumerate(ranked)}
        playoff = [p for p in periods if p["type"] == "playoff"]
        if playoff and league.get("consolation_enabled"):
            raise HTTPException(400, "Disable consolation before generating Rotisserie playoffs; a separate consolation bracket is not supported")
        games = []
        fmt = league.get("playoff_format") or "condensed_roto"
        if playoff and fmt == "playoff_tree":
            count = int(league.get("playoff_teams") or len(teams))
            rounds = (count-1).bit_length()
            if count < 2 or count & (count-1) or count > len(teams) or len(playoff) != rounds:
                raise HTTPException(400, "Elimination playoffs need a power-of-two field and exactly one scoring period per round")
            method = league.get("playoff_seeding_method") or "high_vs_low"
            if method not in ("high_vs_low", "adjacent"):
                raise HTTPException(400, "Rotisserie elimination supports high-versus-low or adjacent seeding")
            from routes.matchups import _seed_pairings
            pairs = _seed_pairings([str(t["_id"]) for t in ranked[:count]], method)
            for rnd,p in enumerate(playoff,1):
                for slot in range(count // (2**rnd)):
                    home,away = None,None
                    games.append({"league_id": league_id,"season":label,"week":p["id"],"bracket_round":rnd,"bracket_slot":slot,
                        "home_team_id":home,"away_team_id":away,"home_team_name":next((t["name"] for t in teams if str(t["_id"])==home),"TBD"),
                        "away_team_name":next((t["name"] for t in teams if str(t["_id"])==away),"TBD"),"home_team_tbd":home is None,"away_team_tbd":away is None,
                        "is_playoff":True,"is_consolation":False,"is_final":rnd==rounds,"bracket":"championship","status":"scheduled",
                        "home_score":0,"away_score":0,"winner":None,"scoring_format":"rotisserie"})
        elif playoff and fmt != "condensed_roto":
            raise HTTPException(400, "Unsupported Rotisserie playoff format")
        await tx.matchups.delete_many(season_query(league_id,label))
        if games: await tx.matchups.insert_many(games)
        response = {"status":"applied","mode":"rotisserie","periods":periods,"games":0,"playoff_matchups":len(games),"weeks":sum(p["type"] == "regular" for p in periods),"warnings":[],"message":"Rotisserie scoring calendar and enabled playoffs generated"}
        await tx.roto_schedules.replace_one({"_id":key},{"_id":key,"league_id":league_id,"season":label,"signature":signature,"scoring_config":config,"seeds":seeds,"response":response,"by":str(user["_id"])},upsert=True)
        await tx.audit_log.insert_one({"league_id":league_id,"actor_id":str(user["_id"]),"action":"roto_schedule_generated","created_at":datetime.now(timezone.utc)})
        return response
    return await transaction(db, commit)


async def finalize(db, league_id, period, user):
    """Finalize a generated period once; derive and advance winners in the same transaction."""
    await authorized(db, league_id, user)
    async def commit(session):
        tx = SessionDB(db, session)
        league = await authorized(tx, league_id, user)
        label = season(league)
        schedule = await tx.roto_schedules.find_one({"_id":f"{league_id}:{label}"})
        if not schedule: raise HTTPException(409, "Generate the Rotisserie scoring calendar first")
        p = next((p for p in league.get("roto_scoring_periods",[]) if p["id"] == period),None)
        if not p: raise HTTPException(400, "Unknown scoring period")
        if date.fromisoformat(p["endDate"]) >= datetime.now(timezone.utc).date():
            raise HTTPException(409, "This scoring period has not ended yet")
        prior = await tx.roto_period_results.find_one({"league_id":league_id,"season":label,"period":period,"closed":True})
        if prior: return {"ok":True,"period":period,"closed":True,"reused":True}
        if any(league.get(k) != value for k,value in schedule.get("scoring_config",{}).items()):
            raise HTTPException(409,"Rotisserie scoring or playoff settings changed; restore the generated rules before finalizing")
        if p["type"] == "playoff":
            regular = [x["id"] for x in league["roto_scoring_periods"] if x["type"] == "regular"]
            closed_regular = await tx.roto_period_results.count_documents({"league_id":league_id,"season":label,"period":{"$in":regular},"closed":True})
            if closed_regular != len(regular): raise HTTPException(409,"Finalize all regular scoring periods before starting playoffs")
            earlier = [x["id"] for x in league["roto_scoring_periods"] if x["type"] == "playoff" and x["id"] < period]
            if earlier and await tx.roto_period_results.count_documents({"league_id":league_id,"season":label,"period":{"$in":earlier},"closed":True}) != len(earlier):
                raise HTTPException(409,"Finalize the previous playoff round first")
        from routes.roto import compute_period
        result = await compute_period(tx,league_id,period=period)
        games = await tx.matchups.find({**season_query(league_id,label),"week":period,"is_playoff":True}).sort("bracket_slot",1).to_list(100)
        seeds = schedule["seeds"]
        if games and not schedule.get("playoff_seeded"):
            if any(g["bracket_round"] != 1 for g in games): raise HTTPException(409, "Finalize the previous playoff round first")
            regular = [p["id"] for p in league["roto_scoring_periods"] if p["type"] == "regular"]
            closed = await tx.roto_period_results.find({"league_id": league_id, "season": label, "closed": True, "period": {"$in": regular}}).to_list(366)
            if len(closed) != len(regular): raise HTTPException(409, "Finalize all regular scoring periods before starting playoffs")
            accumulated = {}
            for row in closed:
                for tid,t in row["totals"].items(): accumulated[tid] = accumulated.get(tid,0)+t["total_points"]
            ordered = sorted(accumulated,key=lambda tid:(-accumulated[tid],tid))
            seeds = {tid:i+1 for i,tid in enumerate(ordered)}
            from routes.matchups import _seed_pairings
            pairs = _seed_pairings(ordered[:int(league.get("playoff_teams") or len(ordered))],league.get("playoff_seeding_method") or "high_vs_low")
            for g,(home,away) in zip(games,pairs):
                g.update(home_team_id=home,away_team_id=away)
                await tx.matchups.update_one({"_id":g["_id"]},{"$set":{"home_team_id":home,"away_team_id":away,"home_team_name":result["totals"][home]["team_name"],"away_team_name":result["totals"][away]["team_name"]}})
            await tx.roto_schedules.update_one({"_id":schedule["_id"]},{"$set":{"seeds":seeds,"playoff_seeded":True}})
        for g in games:
            home,away = g.get("home_team_id"),g.get("away_team_id")
            if not home or not away: raise HTTPException(409,"Finalize the previous playoff round first")
            hs,aws = result["totals"][home]["total_points"],result["totals"][away]["total_points"]
            winner = home if hs > aws or (hs == aws and seeds[home] < seeds[away]) else away
            await tx.matchups.update_one({"_id":g["_id"]},{"$set":{"home_score":hs,"away_score":aws,"winner":winner,"status":"completed","tie_break":"higher_regular_seed" if hs==aws else None}})
            side = "home" if g["bracket_slot"]%2==0 else "away"
            name = result["totals"][winner]["team_name"]
            await tx.matchups.update_one({**season_query(league_id,label),"bracket_round":g["bracket_round"]+1,"bracket_slot":g["bracket_slot"]//2,"is_playoff":True},
                {"$set":{f"{side}_team_id":winner,f"{side}_team_name":name,f"{side}_team_tbd":False}})
            if g.get("is_final"):
                from services.profile_competition import award_fields
                now = datetime.now(timezone.utc).isoformat()
                await tx.teams.update_one({"_id":ObjectId(winner)},{"$set":await award_fields(tx,winner,{"championship_won_at":now})})
                loser = away if winner==home else home
                await tx.teams.update_one({"_id":ObjectId(loser)},{"$set":{"playoff_runner_up_at":now}})
                await tx.leagues.update_one({"_id":league["_id"]},{"$set":{"roto_champion_team_id":winner}})
                await tx.activity_feed.insert_one({"league_id":league_id,"event_type":"championship_awarded","description":f"{name} won the Rotisserie playoffs","created_at":now})
        # Serialize even two regular-period finalizations against the league document.
        await tx.leagues.update_one({"_id":league["_id"]},{"$inc":{"roto_scoring_revision":1}})
        await tx.roto_period_results.update_one({"league_id":league_id,"season":label,"period":period}, {"$set":{**result,"league_id":league_id,"season":label,"period":period,"closed":True,"period_type":p["type"],"recomputed_by":str(user["_id"])}},upsert=True)
        if p["type"] == "playoff" and not games and period == max(x["id"] for x in league["roto_scoring_periods"]):
            from routes.roto import compute_season
            final = await compute_season(tx, league_id)
            best = max(t["total_points"] for t in final["totals"].values())
            champions = [tid for tid,t in final["totals"].items() if t["total_points"] == best]
            from services.profile_competition import award_fields
            now = datetime.now(timezone.utc).isoformat()
            for tid in champions:
                await tx.teams.update_one({"_id":ObjectId(tid)},{"$set":await award_fields(tx,tid,{"championship_won_at":now})})
            await tx.leagues.update_one({"_id":league["_id"]},{"$set":{"roto_champion_team_ids":champions}})
        return {"ok":True,"period":period,"closed":True,"num_teams":result["num_teams"],"playoff_games":len(games)}
    return await transaction(db, commit)

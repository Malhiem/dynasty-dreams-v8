"""Shared league Player Pool eligibility and acquisition guard."""
from bson import ObjectId
from fastapi import HTTPException

DIVISIONS = {
    "Atlantic": ["TBL", "FLA", "BUF", "DET", "MTL", "BOS", "OTT", "TOR"],
    "Metropolitan": ["NYR", "PHI", "WSH", "NJD", "CAR", "NYI", "PIT", "CBJ"],
    "Central": ["COL", "MIN", "NSH", "CHI", "DAL", "UTA", "WPG", "STL"],
    "Pacific": ["CGY", "VGK", "SEA", "VAN", "ANA", "EDM", "SJS", "LAK"],
}
ALL_TEAMS = sum(DIVISIONS.values(), [])
EAST = DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]
WEST = DIVISIONS["Central"] + DIVISIONS["Pacific"]
ALIASES = dict(zip(["Tampa Bay Lightning","Florida Panthers","Buffalo Sabres","Detroit Red Wings","Montreal Canadiens","Boston Bruins","Ottawa Senators","Toronto Maple Leafs","New York Rangers","Philadelphia Flyers","Washington Capitals","New Jersey Devils","Carolina Hurricanes","New York Islanders","Pittsburgh Penguins","Columbus Blue Jackets","Colorado Avalanche","Minnesota Wild","Nashville Predators","Chicago Blackhawks","Dallas Stars","Utah Mammoth","Winnipeg Jets","St. Louis Blues","Calgary Flames","Vegas Golden Knights","Seattle Kraken","Vancouver Canucks","Anaheim Ducks","Edmonton Oilers","San Jose Sharks","Los Angeles Kings"], ALL_TEAMS))
ALIASES.update({"Arizona Coyotes":"UTA","Utah Hockey Club":"UTA","ARI":"UTA","UTAH":"UTA"})

def selected_clubs(config):
    if config.get("selection_mode") == "custom" or ("selection_mode" not in config and not config.get("include_entire_nhl", True)):
        return [ALIASES.get(x, x) for x in config.get("teams", [])]
    if config.get("selection_mode") == "conference" or not config.get("eastern", True) or not config.get("western", True):
        return (EAST if config.get("eastern", True) else []) + (WEST if config.get("western", True) else [])
    return ALL_TEAMS

def live_query(config):
    """Build a Mongo predicate, also used when a pool is finalized."""
    minor = {"$or": [{"player_type":"prospect"},{"player_status":{"$in":["amateur","minor","minors"]}},{"amateur_league":{"$nin":[None,"", "NHL"],"$exists":True}}]}
    drafted = {"$or":[{"draft_year":{"$gt":0}},{"draft_pick_overall":{"$gt":0}},{"drafted_by_team":{"$nin":[None,""],"$exists":True}}]}
    unsigned = {"$or":[{"is_unsigned":True},{"contract_status":{"$in":["unsigned","non-signed"]}},{"player_status":"unsigned"}]}
    clauses=[]
    if config.get("include_minors", True):
        clauses.append({"$or":[{"$nor":[minor]}, {"$and":[minor,drafted]}]})
    else:
        clauses.append({"$nor":[minor]})
    if not config.get("include_unsigned", False):
        clauses.append({"$nor":[unsigned]})
    clubs=selected_clubs(config)
    if set(clubs) != set(ALL_TEAMS):
        # Explicit current rights override historical draft club; missing rights fail closed.
        rights={"$ifNull":["$nhl_rights_team",{"$ifNull":["$rights_team",{"$cond":[{"$in":["$team",ALL_TEAMS+list(ALIASES)]},"$team","$drafted_by_team"]}]}]}
        names=[name for name,code in ALIASES.items() if code in clubs]
        clauses.append({"$expr":{"$in":[rights,clubs+names]}})
    return {"$and":clauses}

def pool_query(league):
    config=league.get("player_pool_config")
    if not config:
        return {}
    if config.get("locked"):
        ids=league.get("player_pool_locked_ids")
        if ids is None:
            return {"_id":{"$in":[]}}  # Legacy lock must be re-finalized explicitly.
        return {"_id":{"$in":[ObjectId(x) for x in ids]}}
    return live_query(config)

async def require_pool_player(db, league, player_id):
    if not league or not league.get("player_pool_config"):
        return
    q=pool_query(league)
    if not await db.players.find_one({"$and":[{"_id":ObjectId(str(player_id))},q]}, {"_id":1}):
        raise HTTPException(400, "Player is outside this league's eligible player pool")

async def apply_pool_settings(db, league, config, update):
    old=league.get("player_pool_config") or {}
    if old.get("locked") and config.get("locked") and config != old:
        raise HTTPException(409, "Unlock the player pool before changing its restrictions")
    if config.get("locked") and (not old.get("locked") or "player_pool_locked_ids" not in league):
        players=await db.players.find(live_query(config),{"_id":1}).to_list(None)
        update["player_pool_locked_ids"]=[str(p["_id"]) for p in players]
    elif not config.get("locked"):
        update["player_pool_locked_ids"]=None

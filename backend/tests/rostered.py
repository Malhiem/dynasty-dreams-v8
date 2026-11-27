"""Find a team whose first rostered player exists in `players`.

Several tests need "any rostered player". A bare `teams.find_one({"roster": ...})`
can land on a fixture team from another test whose roster ids are placeholders,
so the player lookup comes back empty. This skips those teams."""
from bson import ObjectId
from bson.errors import InvalidId


async def rostered_team(db, league_id=None):
    query = {"roster": {"$exists": True, "$ne": []}}
    if league_id:
        query["league_id"] = league_id
    async for team in db.teams.find(query):
        if await db.players.find_one({"_id": _oid(team["roster"][0])}, {"_id": 1}):
            return team
    return None


def _oid(value):
    try:
        return ObjectId(str(value))
    except InvalidId:
        return ObjectId("0" * 24)


def rostered_team_sync(db, league_id=None):
    query = {"roster": {"$exists": True, "$ne": []}}
    if league_id:
        query["league_id"] = league_id
    for team in db.teams.find(query):
        if db.players.find_one({"_id": _oid(team["roster"][0])}, {"_id": 1}):
            return team
    return None

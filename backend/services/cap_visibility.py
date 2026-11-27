"""No cap, no salaries.

League views must not expose player salary figures when the league's salary
cap is disabled. The player card is the one exception and is fed by the roster
detail endpoint, which keeps contract data.
"""
from bson import ObjectId


async def league_cap_enabled(db, league_id) -> bool:
    """True only when the league exists and has its salary cap enabled."""
    try:
        oid = ObjectId(str(league_id))
    except Exception:
        return False
    league = await db.leagues.find_one({"_id": oid}, {"salary_cap_enabled": 1})
    return bool(league and league.get("salary_cap_enabled"))

"""Access control for draft routes.

Draft and league data is private to the league's members (commissioner,
co-commissioners, team owners/co-owners) and platform admins — the same rule as
`league_guards.require_league_member`. These FastAPI dependencies enforce it
before a handler (or its body validation) runs:

    router = APIRouter()
    _deps: dict = {}
    @router.get("/drafts/{draft_id}/board", dependencies=[Depends(draft_member(_deps))])

`deps` is the module's live `_deps` dict, filled in by `setup()` at startup, so
the dependency looks up `db` and `get_current_user` lazily.
"""
from bson import ObjectId
from fastapi import HTTPException, Request

from routes.league_guards import is_league_manager, require_league_member


async def load_draft_for_member(deps: dict, request: Request, draft_id: str):
    """Return (user, draft_league_id) or raise 401 / 400 / 404 / 403."""
    user = await deps["get_current_user"](request)
    try:
        oid = ObjectId(draft_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft id")
    draft = await deps["db"].drafts.find_one({"_id": oid}, {"league_id": 1})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await require_league_member(deps["db"], user, draft.get("league_id") or "")
    return user, draft


def draft_member(deps: dict):
    async def dependency(request: Request, draft_id: str):
        await load_draft_for_member(deps, request, draft_id)
    return dependency


def league_member(deps: dict, param: str = "league_id"):
    async def dependency(request: Request):
        user = await deps["get_current_user"](request)
        await require_league_member(deps["db"], user, request.path_params.get(param) or "")
    return dependency


async def member_league_ids(db, user: dict) -> list[str]:
    """Ids of every league the user belongs to (for unscoped listings)."""
    uid = user["_id"]
    ids = set()
    async for t in db.teams.find(
        {"$or": [{"owner_id": uid}, {"owner_id": str(uid)}, {"co_owner_ids": uid}, {"co_owner_ids": str(uid)}]},
        {"league_id": 1},
    ):
        if t.get("league_id"):
            ids.add(str(t["league_id"]))
    async for lg in db.leagues.find(
        {"$or": [{"commissioner_id": uid}, {"commissioner_id": str(uid)}, {"co_commissioners": {"$in": [uid, str(uid)]}},
                 {"admin_ids": {"$in": [uid, str(uid)]}}]},
        {"_id": 1},
    ):
        ids.add(str(lg["_id"]))
    return sorted(ids)


__all__ = ["draft_member", "league_member", "load_draft_for_member", "member_league_ids", "is_league_manager"]

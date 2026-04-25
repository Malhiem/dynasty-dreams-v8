"""Draft Picks routes."""
from typing import Optional

from fastapi import APIRouter

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/drafts/{league_id}/picks")
async def get_draft_picks(league_id: str, year: Optional[int] = None):
    db = _deps["db"]
    query = {"league_id": league_id}
    if year:
        query["year"] = int(year)
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(1000)
    for p in picks:
        p["_id"] = str(p["_id"])
    return {"league_id": league_id, "year": year, "picks": picks}

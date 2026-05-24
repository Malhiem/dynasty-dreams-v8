"""League Constitution + Audit-log routes — extracted from server.py (iter 108).

Endpoints:
  GET  /api/leagues/{league_id}/constitution
  PUT  /api/leagues/{league_id}/constitution
  GET  /api/leagues/{league_id}/audit-log

Wired into server.py via `routes.constitution_audit.init(_router_deps).include_in(app)`.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class ConstitutionUpdate(BaseModel):
    content: str = Field(..., max_length=5000)


@router.get("/leagues/{league_id}/constitution")
async def get_constitution(league_id: str):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    league = await db.leagues.find_one(
        {"_id": _safe_object_id(league_id, "league_id")},
        {"constitution": 1, "constitution_updated_at": 1, "constitution_updated_by": 1},
    )
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {
        "league_id": league_id,
        "content": league.get("constitution", ""),
        "updated_at": league.get("constitution_updated_at"),
        "updated_by": league.get("constitution_updated_by"),
    }


@router.put("/leagues/{league_id}/constitution")
async def update_constitution(league_id: str, payload: ConstitutionUpdate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    is_co_comm = user["_id"] in co_comms
    if not (is_comm or is_co_comm):
        raise HTTPException(
            status_code=403,
            detail="Only commissioners and co-commissioners can edit the constitution",
        )

    now = datetime.now(timezone.utc)
    previous = league.get("constitution", "")
    await db.leagues.update_one(
        {"_id": league["_id"]},
        {"$set": {
            "constitution": payload.content,
            "constitution_updated_at": now,
            "constitution_updated_by": user["_id"],
        }},
    )

    audit_event = {
        "league_id": league_id,
        "actor_id": user["_id"],
        "actor_name": user.get("name", user.get("email", "Unknown")),
        "action": "constitution_updated",
        "role": "commissioner" if is_comm else "co_commissioner",
        "diff": {
            "previous_length": len(previous or ""),
            "new_length": len(payload.content or ""),
            "preview": (payload.content or "")[:180],
        },
        "created_at": now,
    }
    await db.audit_log.insert_one(audit_event)

    try:
        await db.activity_feed.insert_one({
            "league_id": league_id,
            "event_type": "constitution_updated",
            "description": f"{user.get('name', 'A commissioner')} updated the League Constitution",
            "message": f"{user.get('name', 'A commissioner')} updated the League Constitution",
            "actor_id": user["_id"],
            "actor_name": user.get("name"),
            "created_at": now,
        })
    except Exception:
        pass

    return {
        "league_id": league_id,
        "content": payload.content,
        "updated_at": now,
        "updated_by": user["_id"],
    }


@router.get("/leagues/{league_id}/audit-log")
async def get_audit_log(league_id: str, request: Request, limit: int = 100):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    is_co_comm = user["_id"] in co_comms
    if not (is_comm or is_co_comm):
        raise HTTPException(
            status_code=403,
            detail="Only commissioners and co-commissioners can view the audit log",
        )
    events = await db.audit_log.find({"league_id": league_id}).sort("created_at", -1).limit(
        max(1, min(limit, 500))
    ).to_list(500)
    for e in events:
        e["id"] = str(e.pop("_id"))
    return {"league_id": league_id, "events": events}

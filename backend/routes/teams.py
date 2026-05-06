"""Team management routes — edit name, abbreviation, and logo.

Currently provides:
  - PUT /teams/{team_id} — update name and/or logo_abbr and/or logo_url (URL mode)

Logo file upload + delete still live in server.py (`/teams/{id}/logo` POST/DELETE)
and use Pillow for image processing.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class TeamUpdateInput(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    logo_abbr: Optional[str] = Field(None, max_length=3)
    # URL-mode logo — accepts http(s) URLs. File uploads use POST /teams/{id}/logo.
    logo_url: Optional[str] = Field(None, max_length=4096)

    @field_validator("logo_abbr")
    @classmethod
    def _upper_abbr(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if not v.isalnum():
            raise ValueError("Abbreviation must be alphanumeric (A-Z, 0-9)")
        return v[:3]

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("logo_url")
    @classmethod
    def _validate_url(cls, v):
        if v is None or v == "":
            return None
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("data:image/")):
            raise ValueError("logo_url must be an http(s) URL or data:image/ URL")
        return v


@router.put("/teams/{team_id}")
async def update_team(team_id: str, payload: TeamUpdateInput, request: Request):
    """Update team name, abbreviation, and/or logo (URL mode).

    Only the team owner or league commissioner may edit.
    Abbreviation max length = 3 chars. When provided, it overrides the
    auto-derived abbreviation from the team name.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_commish = bool(
        league and (
            league.get("commissioner_id") == user["_id"]
            or user["_id"] in (league.get("co_commissioners") or [])
        )
    )
    if team.get("owner_id") != user["_id"] and not is_commish:
        raise HTTPException(status_code=403, detail="Not authorized to edit this team")

    updates: dict = {}
    changes: dict = {}
    if payload.name is not None and payload.name != team.get("name"):
        updates["name"] = payload.name
        changes["name"] = {"from": team.get("name"), "to": payload.name}
    if payload.logo_abbr is not None and payload.logo_abbr != (team.get("logo_abbr_override") or None):
        updates["logo_abbr_override"] = payload.logo_abbr
        changes["logo_abbr"] = {"from": team.get("logo_abbr_override"), "to": payload.logo_abbr}
    if payload.logo_url is not None and payload.logo_url != team.get("logo_url"):
        updates["logo_url"] = payload.logo_url
        changes["logo_url"] = {"from": bool(team.get("logo_url")), "to": bool(payload.logo_url)}

    if not updates:
        return {"team_id": team_id, "updated": False, "changes": {}}

    updates["updated_at"] = datetime.now(timezone.utc)
    await db.teams.update_one({"_id": team["_id"]}, {"$set": updates})

    # Audit log
    if league:
        await db.leagues.update_one(
            {"_id": league["_id"]},
            {"$push": {"audit_log": {
                "action": "team_updated",
                "by": user.get("email"),
                "team_id": team_id,
                "changes": changes,
                "at": datetime.now(timezone.utc),
            }}},
        )

    return {"team_id": team_id, "updated": True, "changes": changes}

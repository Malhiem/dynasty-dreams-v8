"""Team management routes — edit name, abbreviation, and logo.

Provides:
  - PUT /teams/{team_id} — update name and/or logo_abbr and/or logo_url (URL mode)
  - POST /teams/{team_id}/logo — file upload (multipart, 1 MB cap, PNG/JPEG/WEBP/GIF
    → resized to 256x256 PNG, stored as base64 data URL)
  - DELETE /teams/{team_id}/logo — clear logo
"""
import base64
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter()
_deps: dict = {}

MAX_LOGO_BYTES = 1 * 1024 * 1024  # 1 MB raw upload
ALLOWED_LOGO_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
LOGO_OUTPUT_SIZE = (256, 256)


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



# ─── Logo upload + delete ───────────────────────────────────────────────────
@router.post("/teams/{team_id}/logo")
async def upload_team_logo(team_id: str, request: Request, file: UploadFile = File(...)):
    """Upload (or replace) a team logo.

    - Max raw upload size: 1 MB
    - Allowed types: PNG, JPEG, WEBP, GIF
    - Server resizes to 256x256 PNG and stores as base64 data URL.
    - Only the team owner (or commissioner / co-commissioner) may upload.
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

    if file.content_type not in ALLOWED_LOGO_MIME:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use PNG, JPEG, WEBP, or GIF.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Image too large. Max size is 1 MB.")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.load()
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.thumbnail(LOGO_OUTPUT_SIZE, Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        encoded = base64.b64encode(out.getvalue()).decode("ascii")
        data_url = f"data:image/png;base64,{encoded}"
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("logo processing failed")
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}")

    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {
            "logo_url": data_url,
            "logo_updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"team_id": team_id, "logo_url": data_url}


@router.delete("/teams/{team_id}/logo")
async def delete_team_logo(team_id: str, request: Request):
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
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$unset": {"logo_url": "", "logo_updated_at": ""}},
    )
    return {"team_id": team_id, "logo_url": None}

"""Team management routes — edit name, abbreviation, and logo.

Provides:
  - POST /teams — create a team (iter 108 extraction)
  - GET /teams — list teams (filterable by league_id) (iter 108 extraction)
  - GET /teams/{team_id} — read a single team (iter 108 extraction)
  - PUT /teams/{team_id} — update name and/or logo_abbr and/or logo_url (URL mode)
  - POST /teams/{team_id}/logo — file upload (multipart, 1 MB cap, PNG/JPEG/WEBP/GIF
    → resized to 256x256 PNG, stored as base64 data URL)
  - DELETE /teams/{team_id}/logo — clear logo
"""
import base64
import io
import logging
from datetime import datetime, timezone
from typing import List, Optional

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


# ─── Pydantic models (extracted from server.py iter 108) ─────────────
class TeamCreate(BaseModel):
    name: str
    league_id: str


class TeamResponse(BaseModel):
    id: str
    name: str
    league_id: str
    owner_id: str
    owner_name: str
    salary_used: float
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    created_at: datetime
    roster: List[str] = []
    live_points: float = 0.0
    logo_abbr: Optional[str] = None
    logo_url: Optional[str] = None
    championship_won_at: Optional[datetime] = None
    division_winner_at: Optional[datetime] = None
    conference_winner_at: Optional[datetime] = None
    playoffs_reached_at: Optional[datetime] = None
    consolation_won_at: Optional[datetime] = None


def team_to_response(team: dict) -> TeamResponse:
    """Convert a raw Mongo team document to a TeamResponse.

    Honors `logo_abbr_override` (set via PUT /teams/{id}) before falling back
    to deriving from the team name (first letters of significant words).
    """
    name = team.get("name", "")
    override = (team.get("logo_abbr_override") or "").strip().upper()
    if override:
        abbr = override[:3]
    else:
        words = [w for w in name.replace("-", " ").split() if w and w[0].isalnum()]
        if len(words) >= 2:
            abbr = (words[0][0] + words[1][0] + (words[2][0] if len(words) > 2 else "")).upper()[:3]
        else:
            abbr = name[:3].upper() if name else "TBD"
    return TeamResponse(
        id=str(team["_id"]),
        name=name,
        league_id=team["league_id"],
        owner_id=team["owner_id"],
        owner_name=team["owner_name"],
        salary_used=team.get("salary_used", 0.0),
        wins=team.get("wins", 0),
        losses=team.get("losses", 0),
        ties=team.get("ties", 0),
        points_for=team.get("points_for", 0.0),
        points_against=team.get("points_against", 0.0),
        created_at=team["created_at"],
        roster=team.get("roster", []),
        live_points=round(team.get("live_points", 0.0) or 0.0, 2),
        logo_abbr=abbr,
        logo_url=team.get("logo_url"),
        championship_won_at=team.get("championship_won_at"),
        division_winner_at=team.get("division_winner_at"),
        conference_winner_at=team.get("conference_winner_at"),
        playoffs_reached_at=team.get("playoffs_reached_at"),
        consolation_won_at=team.get("consolation_won_at"),
    )


@router.post("/teams", response_model=TeamResponse)
async def create_team(input: TeamCreate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league["current_teams"] >= league["max_teams"]:
        raise HTTPException(status_code=400, detail="League is full")

    existing = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="You already have a team in this league")

    team_doc = {
        "name": input.name,
        "league_id": input.league_id,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "roster": [],
        "salary_used": 0.0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "points_for": 0.0,
        "points_against": 0.0,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.teams.insert_one(team_doc)

    await db.leagues.update_one({"_id": ObjectId(input.league_id)}, {"$inc": {"current_teams": 1}})

    return TeamResponse(
        id=str(result.inserted_id),
        name=team_doc["name"],
        league_id=team_doc["league_id"],
        owner_id=team_doc["owner_id"],
        owner_name=team_doc["owner_name"],
        salary_used=team_doc["salary_used"],
        wins=team_doc["wins"],
        losses=team_doc["losses"],
        ties=team_doc["ties"],
        points_for=team_doc["points_for"],
        points_against=team_doc["points_against"],
        created_at=team_doc["created_at"],
    )


@router.get("/teams", response_model=List[TeamResponse])
async def get_teams(league_id: Optional[str] = None, request: Request = None):
    db = _deps["db"]
    query = {}
    if league_id:
        query["league_id"] = league_id
    teams = await db.teams.find(query).to_list(200)
    return [team_to_response(team) for team in teams]


@router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team_to_response(team)


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

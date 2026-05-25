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


# ─── Iter 112: Contract buyouts + Depth-Chart server-side persistence ─────


class BuyoutInput(BaseModel):
    """Initiates a contract buyout for a player on this team.

    The buyout schedule defaults to NHL CBA convention: the team pays roughly
    2/3 of remaining salary spread evenly over (2 × yearsRemaining) future
    seasons as dead cap. Callers may override `buyout_rate` (0.0..1.0) and
    `years_span` (defaults to 2 × yearsRemaining).
    """
    buyout_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    years_span: Optional[int] = Field(None, ge=1, le=10)


@router.post("/teams/{team_id}/players/{player_id}/buyout")
async def buy_out_contract(team_id: str, player_id: str, payload: BuyoutInput, request: Request):
    """Commissioner/Owner action — remove a player from the roster and stamp
    a multi-year dead-cap schedule on the team document.

    Requires `league.contract_buyouts_enabled = True`. Idempotent only for
    different players — buying out the same player twice is rejected.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("contract_buyouts_enabled"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Contract buyouts are not enabled for this league. "
                "Ask the commissioner to enable them under Transactions."
            ),
        )

    is_owner = team.get("owner_id") == user["_id"]
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or (user.get("role") == "admin")
    )
    if not (is_owner or is_commish):
        raise HTTPException(status_code=403, detail="Only the team owner or commissioner may initiate buyouts")

    if player_id not in (team.get("roster") or []):
        raise HTTPException(status_code=400, detail="Player not on this team's roster")

    # Pull the synthesized contract so the buyout math has years_remaining +
    # salary even when no explicit row is stored.
    from routes.roster import _synthesize_contract
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    fpts_season = float(player.get("fantasy_points") or 0.0)
    points = int(player.get("points") or 0)
    is_g = player.get("player_type") == "goalie" or player.get("position") == "G"
    contract = (player.get("contract") or {})
    if not contract:
        contract = _synthesize_contract(
            is_g=is_g, fpts_season=fpts_season, points=points,
            nhl_id=player.get("nhl_id"), age=int(player.get("age") or 27),
        )

    salary = int(contract.get("salary") or 0)
    years_remaining = int(contract.get("yearsRemaining") or 1)
    if salary <= 0 or years_remaining <= 0:
        raise HTTPException(status_code=400, detail="Player has no remaining contract to buy out")

    # Idempotency — reject double buyout
    existing_schedule = team.get("dead_cap_schedule") or []
    if any(entry.get("player_id") == player_id for entry in existing_schedule):
        raise HTTPException(status_code=400, detail="This player has already been bought out")

    # NHL CBA-inspired defaults: 2/3 of remaining salary over 2× term.
    rate = float(payload.buyout_rate) if payload.buyout_rate is not None else 2.0 / 3.0
    span = int(payload.years_span) if payload.years_span else max(2, 2 * years_remaining)
    total_dead = int(round(salary * years_remaining * rate))
    annual_dead = int(round(total_dead / span))
    from datetime import datetime as _dt
    cur_year = _dt.now(timezone.utc).year
    schedule_entries = []
    for i in range(span):
        schedule_entries.append({
            "year": cur_year + i,
            "amount": annual_dead,
            "source": "buyout",
            "player_id": player_id,
            "player_name": player.get("name", "Unknown"),
            "original_salary": salary,
            "original_years_remaining": years_remaining,
            "created_at": _dt.now(timezone.utc),
        })

    # Apply: remove player from roster, append schedule.
    new_roster = [pid for pid in (team.get("roster") or []) if pid != player_id]
    await db.teams.update_one(
        {"_id": team["_id"]},
        {
            "$set": {"roster": new_roster},
            "$push": {"dead_cap_schedule": {"$each": schedule_entries}},
        },
    )

    return {
        "team_id": team_id,
        "player_id": player_id,
        "player_name": player.get("name"),
        "dead_cap_total": total_dead,
        "annual_dead_cap": annual_dead,
        "span_years": span,
        "schedule": [{**e, "created_at": e["created_at"].isoformat()} for e in schedule_entries],
    }


@router.get("/teams/{team_id}/dead-cap-schedule")
async def get_dead_cap_schedule(team_id: str, request: Request):
    """Return the team's full dead-cap schedule (buyouts + retention).

    Iter 112 — Salary-cap and depth-chart pages consume this to render the
    correct multi-year dead-cap charge per season.
    """
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    schedule = team.get("dead_cap_schedule") or []
    # Aggregate per year
    by_year: dict = {}
    for e in schedule:
        y = int(e.get("year") or 0)
        by_year.setdefault(y, {"year": y, "total": 0, "entries": []})
        by_year[y]["total"] += int(e.get("amount") or 0)
        by_year[y]["entries"].append({
            "amount": int(e.get("amount") or 0),
            "source": e.get("source", "buyout"),
            "player_name": e.get("player_name"),
            "player_id": e.get("player_id"),
        })
    rows = sorted(by_year.values(), key=lambda r: r["year"])
    return {
        "team_id": team_id,
        "schedule": rows,
        "total_dead_cap": sum(r["total"] for r in rows),
    }


class DepthProjectionsInput(BaseModel):
    """{ projections: { "<player_id>": [y0, y1, y2] } }"""
    projections: dict


@router.put("/teams/{team_id}/depth-projections")
async def save_depth_projections(team_id: str, payload: DepthProjectionsInput, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("owner_id") != user["_id"] and user.get("role") != "admin":
        league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
        if not league or (
            league.get("commissioner_id") != user["_id"]
            and user["_id"] not in (league.get("co_commissioners") or [])
        ):
            raise HTTPException(status_code=403, detail="Only the team owner may edit projections")
    # Clamp values defensively (max 1500 PF/season; keep keys as strings).
    cleaned: dict = {}
    for pid, arr in (payload.projections or {}).items():
        if not isinstance(arr, list):
            continue
        cleaned[str(pid)] = [
            max(0, min(1500, int(v) if isinstance(v, (int, float)) else 0)) for v in arr[:3]
        ]
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {"depth_projections": cleaned}},
    )
    return {"team_id": team_id, "saved": True, "count": len(cleaned)}


@router.get("/teams/{team_id}/depth-projections")
async def get_depth_projections(team_id: str, request: Request):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "projections": team.get("depth_projections") or {}}


class DepthLineupInput(BaseModel):
    """{ lineups: { "y0": { "L1-LW": "<player_id>", ... }, "y1": {...}, "y2": {...} } }"""
    lineups: dict


@router.put("/teams/{team_id}/depth-lineup")
async def save_depth_lineup(team_id: str, payload: DepthLineupInput, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("owner_id") != user["_id"] and user.get("role") != "admin":
        league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
        if not league or (
            league.get("commissioner_id") != user["_id"]
            and user["_id"] not in (league.get("co_commissioners") or [])
        ):
            raise HTTPException(status_code=403, detail="Only the team owner may edit lineup")
    cleaned: dict = {}
    for ykey, slots in (payload.lineups or {}).items():
        if ykey not in ("y0", "y1", "y2"):
            continue
        if not isinstance(slots, dict):
            continue
        cleaned[ykey] = {str(slot): str(pid) for slot, pid in slots.items() if pid}
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {"depth_lineup": cleaned}},
    )
    return {"team_id": team_id, "saved": True}


@router.get("/teams/{team_id}/depth-lineup")
async def get_depth_lineup(team_id: str, request: Request):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "lineups": team.get("depth_lineup") or {}}

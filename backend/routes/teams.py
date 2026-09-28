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


# ─── SEC-002: auth + league-membership helpers ───────────────────────
async def _require_user(request: Request) -> dict:
    """Resolves the caller via the shared `get_current_user` dependency
    injected by server.py. Raises 401 when unauthenticated."""
    get_current_user = _deps["get_current_user"]
    return await get_current_user(request)


async def _require_league_member(request: Request, league_id: str) -> dict:
    """Returns the authenticated user iff they belong to `league_id`
    (own/co-own a team, or are the commissioner / a league admin /
    a platform admin). Raises 403 otherwise."""
    user = await _require_user(request)
    # Iter 232N.38 — Accept both `role='admin'` (singular string) and
    # `roles=['admin']` (list) so platform admins consistently bypass
    # per-league membership checks. Previous check missed the singular
    # form, blocking admins from `/teams?league_id=X` calls used by
    # the WebSocket-driven presence bar and other read-only surfaces.
    _role = user.get("role")
    _roles = user.get("roles") or []
    if _role == "admin" or "admin" in _roles:
        return user  # platform admins bypass per-league checks
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    uid = str(user["_id"])
    league_oid = None
    try:
        league_oid = _safe_object_id(league_id, "league_id")
    except HTTPException:
        league_oid = None
    if league_oid is not None:
        lg = await db.leagues.find_one(
            {"_id": league_oid},
            {"commissioner_id": 1, "admin_ids": 1, "owner_id": 1},
        )
        if lg:
            if str(lg.get("commissioner_id") or "") == uid:
                return user
            if str(lg.get("owner_id") or "") == uid:
                return user
            if uid in [str(a) for a in (lg.get("admin_ids") or [])]:
                return user
    team = await db.teams.find_one(
        {
            "league_id": str(league_id),
            "$or": [{"owner_id": uid}, {"co_owner_ids": uid}],
        },
        {"_id": 1},
    )
    if team:
        return user
    raise HTTPException(status_code=403, detail="Not a member of this league")


# ─── Pydantic models (extracted from server.py iter 108) ─────────────
class TeamCreate(BaseModel):
    name: str
    league_id: str


class TeamResponse(BaseModel):
    id: str
    name: str
    league_id: str
    # Iter 194 — Owner fields are now Optional so the dropdown +
    # League detail page work for pending-invite teams (e.g. 32-team
    # entry-draft leagues created via iter192 where every team is
    # awaiting an owner to claim it).
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    # Iter 232N.38 — Expose co-owner ids so the Draft Presence Bar can
    # light up a team's dot when either the primary owner OR any co-owner
    # is in the war room.
    co_owner_ids: List[str] = []
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
    # Iter 229i — Optional preset theme color, hex e.g. "#0ea5e9".
    theme_color: Optional[str] = None
    championship_won_at: Optional[datetime] = None
    division_winner_at: Optional[datetime] = None
    conference_winner_at: Optional[datetime] = None
    playoffs_reached_at: Optional[datetime] = None
    consolation_won_at: Optional[datetime] = None
    is_pending: bool = False
    division: Optional[str] = None
    conference: Optional[str] = None


def team_to_response(team: dict) -> TeamResponse:
    """Convert a raw Mongo team document to a TeamResponse.

    Honors `logo_abbr_override` (set via PUT /teams/{id}) before falling back
    to deriving from the team name (first letters of significant words).
    """
    name = team.get("name") or ""
    # Iter 229b — Auto-seeded "Open Slot" stubs have `name=None`. Surface
    # a stable placeholder so downstream consumers (TeamResponse + UI)
    # don't break on `.replace`/length operations.
    if not name:
        slot_n = team.get("draft_position")
        name = f"Open Slot {slot_n}" if slot_n else "Open Slot"
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
        owner_id=team.get("owner_id"),
        owner_name=team.get("owner_name"),
        co_owner_ids=[str(c) for c in (team.get("co_owner_ids") or [])],
        salary_used=team.get("salary_used", 0.0),
        wins=team.get("wins", 0),
        losses=team.get("losses", 0),
        ties=team.get("ties", 0),
        points_for=team.get("points_for", 0.0),
        points_against=team.get("points_against", 0.0),
        created_at=team.get("created_at") or datetime.now(timezone.utc),
        roster=team.get("roster", []),
        live_points=round(team.get("live_points", 0.0) or 0.0, 2),
        logo_abbr=abbr,
        logo_url=team.get("logo_url"),
        theme_color=team.get("theme_color"),
        championship_won_at=team.get("championship_won_at"),
        division_winner_at=team.get("division_winner_at"),
        conference_winner_at=team.get("conference_winner_at"),
        playoffs_reached_at=team.get("playoffs_reached_at"),
        consolation_won_at=team.get("consolation_won_at"),
        is_pending=bool(team.get("is_pending")),
        division=team.get("division"),
        conference=team.get("conference"),
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

    # Iter 232N.37 — Auto-backfill draft_picks for any scheduled/active
    # drafts in this league so the newly-added team appears on the
    # Draft Board with a full column of picks.
    try:
        from routes.draft_helpers import backfill_missing_pick_rows_for_league
        await backfill_missing_pick_rows_for_league(input.league_id)
    except Exception:
        pass  # best-effort — don't block team creation on pick seeding

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
async def get_teams(request: Request, league_id: Optional[str] = None):
    # SEC-002 — list-teams is a per-league read; require league
    # membership when scoped to one league, and require any
    # authenticated user otherwise (used by the user dashboard).
    if league_id:
        await _require_league_member(request, league_id)
    else:
        await _require_user(request)
    db = _deps["db"]
    query = {}
    if league_id:
        query["league_id"] = league_id
    teams = await db.teams.find(query).to_list(200)
    return [team_to_response(team) for team in teams]


@router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str, request: Request):
    # SEC-002 — require auth BEFORE the team lookup so attackers can't
    # probe team-id existence via the 404-vs-401 difference.
    await _require_user(request)
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # ...and then enforce league membership.
    await _require_league_member(request, str(team.get("league_id") or ""))
    return team_to_response(team)


class TeamUpdateInput(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    logo_abbr: Optional[str] = Field(None, max_length=3)
    # URL-mode logo — accepts http(s) URLs. File uploads use POST /teams/{id}/logo.
    logo_url: Optional[str] = Field(None, max_length=4096)
    # Iter 229i — Optional preset theme color (e.g. "#0ea5e9"). The
    # frontend offers a 4-swatch picker so new owners can brand their
    # franchise on claim. Stored on the team doc as `theme_color` and
    # surfaced everywhere the team chip renders (standings, trade
    # block, draft board).
    theme_color: Optional[str] = Field(None, max_length=16)

    @field_validator("theme_color")
    @classmethod
    def _validate_color(cls, v):
        if v is None or v == "":
            return None
        v = v.strip().lower()
        # Accept 3-char (#fff) or 6-char (#ffffff) hex.
        import re as _re
        if not _re.match(r"^#([0-9a-f]{3}|[0-9a-f]{6})$", v):
            raise ValueError("theme_color must be a hex string like #0ea5e9")
        return v

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
    # Iter 229i — Preset theme color.
    # Iter 229L — Allow explicit clearing by sending `theme_color: null` (or
    # empty string, normalized to None by the validator). Detect "field was
    # explicitly provided" via Pydantic's model_fields_set so we don't
    # confuse "omitted" with "set to null".
    if "theme_color" in payload.model_fields_set and payload.theme_color != team.get("theme_color"):
        updates["theme_color"] = payload.theme_color
        changes["theme_color"] = {"from": team.get("theme_color"), "to": payload.theme_color}

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


# ─── Iter 232N.26 — Auto-pick preference (per team) ────────────────────────
class AutoPickPreferenceInput(BaseModel):
    """Manager-set fallback strategy when the pick timer expires.

    - `queue_then_best` (default) — walk the team's `draft_queue` first,
      fall back to top-eligible by points. Mirrors existing behaviour so
      current drafts don't change once this feature ships.
    - `best_available` — skip the queue entirely and always take the
      top-eligible player. For managers who forget to maintain a queue
      but want the auto-picker to just grab the safe pick.
    """
    auto_pick_preference: str = Field(..., pattern="^(queue_then_best|best_available)$")


@router.patch("/teams/{team_id}/auto-pick-preference")
async def set_auto_pick_preference(team_id: str, payload: AutoPickPreferenceInput, request: Request):
    """Owner (or commissioner) sets how the auto-picker should fall back
    for this team when a pick clock (main or personal) expires.
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
    is_owner_or_co = (
        team.get("owner_id") == user["_id"]
        or user["_id"] in (team.get("co_owner_ids") or [])
    )
    if not (is_owner_or_co or is_commish):
        raise HTTPException(status_code=403, detail="Not authorized to edit this team")

    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {
            "auto_pick_preference": payload.auto_pick_preference,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {
        "team_id": team_id,
        "auto_pick_preference": payload.auto_pick_preference,
    }



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
    seasons as dead cap. Iter 113: a `length_option` shortcut maps to common
    presets, callers may also override `buyout_rate` / `years_span` directly.

    `length_option` values:
      - "full"     — 100% of remaining salary spread over 2× term
      - "two_thirds" / "default" — 2/3 spread over 2× term (CBA default)
      - "half"     — 50% of remaining salary spread over 2× term
      - "one_year" — full remaining salary as a single dead-cap year
      - "minimum"  — 1/3 spread over yearsRemaining
    """
    buyout_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    years_span: Optional[int] = Field(None, ge=1, le=10)
    length_option: Optional[str] = Field(None, max_length=24)


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
    # Iter 113 — `length_option` presets short-circuit the rate/span pair.
    LENGTH_PRESETS = {
        "full":       (1.0, max(2, 2 * years_remaining)),
        "two_thirds": (2.0 / 3.0, max(2, 2 * years_remaining)),
        "default":    (2.0 / 3.0, max(2, 2 * years_remaining)),
        "half":       (0.5, max(2, 2 * years_remaining)),
        "one_year":   (1.0, 1),
        "minimum":    (1.0 / 3.0, max(1, years_remaining)),
    }
    if payload.length_option and payload.length_option in LENGTH_PRESETS:
        preset_rate, preset_span = LENGTH_PRESETS[payload.length_option]
        rate = float(payload.buyout_rate) if payload.buyout_rate is not None else preset_rate
        span = int(payload.years_span) if payload.years_span else preset_span
    else:
        rate = float(payload.buyout_rate) if payload.buyout_rate is not None else 2.0 / 3.0
        span = int(payload.years_span) if payload.years_span else max(2, 2 * years_remaining)
    total_dead = int(round(salary * years_remaining * rate))
    annual_dead = int(round(total_dead / span))
    from datetime import datetime as _dt
    cur_year = _dt.now(timezone.utc).year
    schedule_entries = []
    created_at = _dt.now(timezone.utc)
    for i in range(span):
        schedule_entries.append({
            "year": cur_year + i,
            "amount": annual_dead,
            "source": "buyout",
            "player_id": player_id,
            "player_name": player.get("name", "Unknown"),
            "original_salary": salary,
            "original_years_remaining": years_remaining,
            "length_option": payload.length_option or "default",
            "buyout_rate": round(rate, 4),
            "created_at": created_at,
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

    # ── Ownership tracking (buyout) ──────────────────────────────
    try:
        from utils.scoring_roster import log_roster_change
        await log_roster_change(db, team_id=team_id, league_id=team.get("league_id", ""),
            player_id=player_id, action="remove", source="buyout",
            metadata={"dead_cap_total": total_dead})
    except Exception:
        pass

    return {
        "team_id": team_id,
        "player_id": player_id,
        "player_name": player.get("name"),
        "dead_cap_total": total_dead,
        "annual_dead_cap": annual_dead,
        "span_years": span,
        "schedule": [{**e, "created_at": e["created_at"].isoformat()} for e in schedule_entries],
    }


@router.delete("/teams/{team_id}/buyouts/{player_id}")
async def reverse_buyout(team_id: str, player_id: str, request: Request):
    """Commissioner-only — undo a buyout. Removes every schedule entry whose
    source is "buyout" and player_id matches, and re-adds the player to the
    team's roster. Use this when a new owner takes over a team and the league
    decides to forgive prior buyout penalties.
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
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or (user.get("role") == "admin")
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only the commissioner may reverse buyouts")

    schedule = team.get("dead_cap_schedule") or []
    matching = [e for e in schedule if e.get("source") == "buyout" and e.get("player_id") == player_id]
    if not matching:
        raise HTTPException(status_code=404, detail="No active buyout found for this player")
    kept = [e for e in schedule if not (e.get("source") == "buyout" and e.get("player_id") == player_id)]
    roster = list(team.get("roster") or [])
    if player_id not in roster:
        roster.append(player_id)
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {"dead_cap_schedule": kept, "roster": roster}},
    )

    # ── Ownership tracking (buyout reversal) ─────────────────────
    try:
        from utils.scoring_roster import log_roster_change
        await log_roster_change(db, team_id=team_id, league_id=team.get("league_id", ""),
            player_id=player_id, action="add", source="admin",
            metadata={"reason": "buyout_reversal"})
    except Exception:
        pass
    return {
        "team_id": team_id,
        "player_id": player_id,
        "removed_entries": len(matching),
        "removed_total": sum(int(e.get("amount") or 0) for e in matching),
        "reversed": True,
    }


@router.delete("/teams/{team_id}/dead-cap/retention/{player_id}")
async def cancel_retention_charge(team_id: str, player_id: str, request: Request):
    """Commissioner-only — forgive a salary-retention charge against this team.

    Deletes the matching row from `db.salary_retentions` (so the schedule
    endpoint no longer flattens it back in). Intended for "new owner takeover"
    situations where the league waives prior commitments.
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
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or (user.get("role") == "admin")
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only the commissioner may cancel retention charges")
    result = await db.salary_retentions.delete_many({
        "league_id": team["league_id"],
        "retainer_team_id": team_id,
        "player_id": player_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No active retention found for this player")
    return {"team_id": team_id, "player_id": player_id,
            "deleted_count": result.deleted_count, "reversed": True}



@router.get("/teams/{team_id}/dead-cap-schedule")
async def get_dead_cap_schedule(team_id: str, request: Request):
    """Return the team's full dead-cap schedule (buyouts + retention).

    Iter 112 — Salary-cap and depth-chart pages consume this to render the
    correct multi-year dead-cap charge per season.

    Iter 113 — Salary-retention rows from the trade engine
    (`db.salary_retentions` keyed by `retainer_team_id`) are now flattened into
    per-year entries here using each player's `yearsRemaining` so they show up
    on the Dead Cap tile/dropdown and the By-Year bar chart alongside buyouts.
    """
    # SEC-002 — auth first to avoid existence probing.
    await _require_user(request)
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # SEC-002 — dead-cap exposes contract data; gate to league members.
    await _require_league_member(request, str(team.get("league_id") or ""))
    schedule = list(team.get("dead_cap_schedule") or [])

    # ── Iter 113 — Inline salary-retention rows for *legacy* trades that
    # pre-date the schedule write. Skip if the team's dead_cap_schedule
    # already has matching retention entries for this player (to avoid
    # double-counting after the trade-engine fix in iter 113).
    league_id = team.get("league_id")
    if league_id:
        from routes.roster import _synthesize_contract
        cur_year = datetime.now(timezone.utc).year
        existing_retention_pids = {
            e.get("player_id") for e in schedule
            if e.get("source") == "retention" and e.get("player_id")
        }
        retentions = await db.salary_retentions.find(
            {"league_id": league_id, "retainer_team_id": team_id},
        ).to_list(200)
        for r in retentions:
            pid = r.get("player_id")
            if pid in existing_retention_pids:
                continue  # Already in the schedule — skip on-the-fly merge.
            amount = float(r.get("amount") or 0)
            if not pid or amount <= 0:
                continue
            try:
                player = await db.players.find_one({"_id": ObjectId(pid)})
            except Exception:
                player = None
            years_rem = 1
            if player:
                contract = player.get("contract") or {}
                if not contract.get("yearsRemaining"):
                    is_g = player.get("player_type") == "goalie" or player.get("position") == "G"
                    contract = _synthesize_contract(
                        is_g=is_g,
                        fpts_season=float(player.get("fantasy_points") or 0.0),
                        points=int(player.get("points") or 0),
                        nhl_id=player.get("nhl_id"),
                        age=int(player.get("age") or 27),
                    )
                years_rem = max(1, int(contract.get("yearsRemaining") or 1))
            player_name = (player or {}).get("name", "Retained player")
            retention_created = r.get("created_at")
            for i in range(years_rem):
                schedule.append({
                    "year": cur_year + i,
                    "amount": int(round(amount)),
                    "source": "retention",
                    "player_id": pid,
                    "player_name": player_name,
                    "created_at": retention_created,
                })

    # ── Aggregate per year + return per-source line items ──
    by_year: dict = {}
    for e in schedule:
        y = int(e.get("year") or 0)
        by_year.setdefault(y, {"year": y, "total": 0, "entries": []})
        by_year[y]["total"] += int(e.get("amount") or 0)
        # Normalize datetime created_at to ISO so JSON serialization works.
        created = e.get("created_at")
        if hasattr(created, "isoformat"):
            created_iso = created.isoformat()
        elif isinstance(created, str):
            created_iso = created
        else:
            created_iso = None
        by_year[y]["entries"].append({
            "amount": int(e.get("amount") or 0),
            "source": e.get("source", "buyout"),
            "player_name": e.get("player_name"),
            "player_id": e.get("player_id"),
            "length_option": e.get("length_option"),
            "buyout_rate": e.get("buyout_rate"),
            "original_salary": e.get("original_salary"),
            "original_years_remaining": e.get("original_years_remaining"),
            "created_at": created_iso,
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
    # SEC-002 — auth first.
    await _require_user(request)
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # SEC-002 — gate to league members.
    await _require_league_member(request, str(team.get("league_id") or ""))
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
    # SEC-002 — auth first.
    await _require_user(request)
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # SEC-002 — gate to league members.
    await _require_league_member(request, str(team.get("league_id") or ""))
    return {"team_id": team_id, "lineups": team.get("depth_lineup") or {}}



# ─── Iter 150 — Truncated roster for Draft Room side panel ──────────────
@router.get("/teams/{team_id}/roster-truncated")
async def get_team_roster_truncated(
    team_id: str,
    request: Request,
    stat_filter: str = "season",
):
    """Returns a compact roster for the Draft Room truncated roster panel.

    Sources roster from `team.roster` (the same field the canonical
    `/api/roster/{team_id}` endpoint reads — keeps the Draft Room panel
    in lock-step with the Rosters page). Falls back to `team.player_ids`
    and finally to the `db.rosters` collection so older leagues still work.

    Each entry: {id, name, position, fantasy_points, fp_per_game, cap_hit,
                 games_played}. The `stat_filter` query param
    (season / regular / playoffs / l30 / l7) selects which stat bucket to
    surface; falls back gracefully to flat fields.
    """
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    calculate_fantasy_points = _deps.get("calculate_fantasy_points")
    # SEC-002 — auth first.
    await _require_user(request)

    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # SEC-002 — gate to league members.
    await _require_league_member(request, str(team.get("league_id") or ""))

    # 1) Canonical: team.roster (list[str ids]) — matches /api/roster/{team_id}
    player_ids = list(team.get("roster") or [])
    # 2) Legacy: team.player_ids
    if not player_ids:
        player_ids = list(team.get("player_ids") or [])
    # 3) Fallback: rosters collection (seed scripts may write here)
    if not player_ids:
        roster_doc = await db.rosters.find_one({"team_id": team_id})
        player_ids = list((roster_doc or {}).get("players") or [])

    if not player_ids:
        return {"team_id": team_id, "stat_filter": stat_filter, "players": []}

    # Fetch players in batch — accept ObjectId or string ids interchangeably.
    obj_ids = []
    str_ids = []
    for pid in player_ids:
        try:
            obj_ids.append(ObjectId(str(pid)))
        except Exception:
            str_ids.append(str(pid))
    or_clauses = []
    if obj_ids:
        or_clauses.append({"_id": {"$in": obj_ids}})
    if str_ids:
        or_clauses.append({"_id": {"$in": str_ids}})
    if not or_clauses:
        return {"team_id": team_id, "stat_filter": stat_filter, "players": []}
    players_docs = await db.players.find({"$or": or_clauses}).to_list(200)

    # Pull league scoring config so fantasy_points matches the Rosters page exactly
    config = await db.scoring_configs.find_one({"league_id": team.get("league_id")})

    def _stat_from_bucket(p: dict, key: str, default: float = 0) -> float:
        if not isinstance(p, dict):
            return default
        stats = p.get("stats") or {}
        bucket = stats.get(stat_filter) if isinstance(stats, dict) else None
        if isinstance(bucket, dict) and key in bucket:
            return float(bucket.get(key) or default)
        return float(p.get(key) or default)

    out = []
    # Helper — pull a stat for the requested bucket with sensible flat fallbacks
    def _bucket_stat(p: dict, key: str) -> float:
        if not isinstance(p, dict):
            return 0
        stats = p.get("stats") or {}
        b = stats.get(stat_filter) if isinstance(stats, dict) else None
        if isinstance(b, dict) and key in b:
            try:
                return float(b.get(key) or 0)
            except (TypeError, ValueError):
                return 0
        try:
            return float(p.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    SKATER_KEYS = [
        "goals", "assists", "points", "plus_minus", "penalty_minutes",
        "power_play_goals", "power_play_points", "short_handed_goals",
        "short_handed_points", "game_winning_goals", "shots",
    ]
    GOALIE_KEYS = [
        "wins", "losses", "overtime_losses", "saves", "goals_against",
        "shots_against", "shutouts", "save_pct", "goals_against_avg",
    ]

    for p in players_docs:
        pos = (p.get("position") or p.get("primary_position") or "").split(",")[0].strip() or "—"
        is_goalie = pos == "G"
        # Compute the per-bucket categories first so FP recomputes from the same numbers
        cats = {}
        for k in (GOALIE_KEYS if is_goalie else SKATER_KEYS):
            cats[k] = _bucket_stat(p, k)
        # Bucketed games_played (preferred), with sensible fallbacks
        b = (p.get("stats") or {}).get(stat_filter) if isinstance(p.get("stats"), dict) else None
        gp = int((b or {}).get("games_played") or p.get("games_played") or p.get("gp") or 0)
        # Merge bucket categories + games_played into a player-shaped dict so the
        # canonical FP helper computes the right number for the selected bucket.
        bucket_player = {**p, **cats, "games_played": gp}
        if calculate_fantasy_points:
            try:
                fp = float(calculate_fantasy_points(bucket_player, config) or 0)
            except Exception:
                fp = float(_bucket_stat(p, "fantasy_points"))
        else:
            fp = float(_bucket_stat(p, "fantasy_points"))
        fp_pg = (fp / gp) if gp > 0 else 0

        out.append({
            "id": str(p.get("_id")),
            "name": p.get("name") or p.get("full_name") or "—",
            "position": pos,
            "fantasy_points": round(fp, 1) if fp else 0,
            "fp_per_game": round(fp_pg, 2) if fp_pg else 0,
            "cap_hit": p.get("cap_hit") or p.get("salary") or 0,
            "games_played": gp,
            "nhl_team": p.get("team") or p.get("nhl_team") or "",
            "stats": cats,
        })

    # Default-sort by fantasy_points desc (frontend may re-sort by column).
    out.sort(key=lambda x: x.get("fantasy_points") or 0, reverse=True)

    # Categories the league actually scores — frontend uses these to choose
    # which columns to render in Regular Season / Playoffs / etc. views.
    skater_cfg = (config or {}).get("skater_scoring") or {}
    goalie_cfg = (config or {}).get("goalie_scoring") or {}
    skater_categories = list(skater_cfg.keys()) if isinstance(skater_cfg, dict) else []
    goalie_categories = list(goalie_cfg.keys()) if isinstance(goalie_cfg, dict) else []
    return {
        "team_id": team_id,
        "stat_filter": stat_filter,
        "players": out,
        "scoring": {
            "skater": skater_categories,
            "goalie": goalie_categories,
        },
    }

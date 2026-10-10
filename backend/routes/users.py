"""Users router: /users/me/*, /u/{username}, profile edit + avatar."""
import base64
import io
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter()
_deps: dict = {}

MAX_AVATAR_BYTES = 1 * 1024 * 1024  # 1 MB
ALLOWED_AVATAR_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
AVATAR_OUTPUT_SIZE = (256, 256)
USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class ProfileUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=32)
    email: Optional[EmailStr] = None
    current_password: Optional[str] = None
    favourite_sport: Optional[str] = Field(None, max_length=40)
    favourite_team: Optional[str] = Field(None, max_length=80)
    city: Optional[str] = Field(None, max_length=80)
    province_state: Optional[str] = Field(None, max_length=80)
    country: Optional[str] = Field(None, max_length=80)
    avatar_url: Optional[str] = Field(None, max_length=4096)

    @field_validator("username")
    @classmethod
    def _valid_username(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not USERNAME_REGEX.match(v):
            raise ValueError("Username must be 3-32 chars (letters, numbers, _ . -)")
        return v

    @field_validator("avatar_url")
    @classmethod
    def _avatar(cls, v):
        if v is None or v == "":
            return None
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("data:image/")):
            raise ValueError("avatar_url must be an http(s) URL or data:image/ URL")
        return v

def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/users/me/week-at-a-glance")
async def get_my_week_at_a_glance(request: Request):
    """Week-at-a-glance for every team owned by the current user.

    Iter 230g — Bug fix: filter out teams whose league is archived OR
    whose league name starts with the `TEST_` automated-test prefix so
    stale test artifacts (left behind by integration runs) don't bleed
    into a real user's dashboard. Also include teams where the user is
    a co-owner (`co_owner_ids`) — those belong on the dashboard just
    like primary-owner teams.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    get_team_week_summary = _deps["get_team_week_summary"]

    user = await get_current_user(request)
    teams = await db.teams.find(
        {"$or": [
            {"owner_id": user["_id"]},
            {"co_owner_ids": user["_id"]},
        ]},
        {"_id": 1, "league_id": 1, "name": 1},
    ).to_list(200)
    if not teams:
        return {"summaries": []}

    # Iter 230h — Honour the user's per-league "hide from dashboard"
    # preference. Hidden leagues won't appear here even if real.
    hidden_ids: set = set()
    try:
        from routes.notification_preferences import get_hidden_league_ids
        hidden_ids = set(await get_hidden_league_ids(user["_id"]))
    except Exception:
        hidden_ids = set()

    # Resolve every league referenced and apply the filter in one pass.
    league_ids: set = set()
    for t in teams:
        if t.get("league_id"):
            league_ids.add(t["league_id"])
    real_league_ids: set = set()
    if league_ids:
        oid_list = []
        for lid in league_ids:
            try:
                oid_list.append(ObjectId(lid))
            except Exception:
                continue
        if oid_list:
            async for lg in db.leagues.find(
                {"_id": {"$in": oid_list}},
                {"_id": 1, "archived": 1, "status": 1, "name": 1},
            ):
                if lg.get("archived"):
                    continue
                if (lg.get("status") or "").lower() == "archived":
                    continue
                name = lg.get("name") or ""
                if name.startswith("TEST_"):
                    continue
                real_league_ids.add(str(lg["_id"]))

    summaries = []
    for t in teams:
        if t.get("league_id") not in real_league_ids:
            continue
        if t.get("league_id") in hidden_ids:
            continue
        try:
            res = await get_team_week_summary(str(t["_id"]), request)
            summaries.append(res)
        except HTTPException:
            continue
    return {"summaries": summaries}


@router.get("/users/me/level")
async def get_my_level(request: Request):
    """Yahoo-style fantasy level based on career activity."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]

    user = await get_current_user(request)
    user_id = user["_id"]

    from services.profile_career import career_summary
    from utils.xp import level_from_xp
    summary = await career_summary(db, user_id)
    stats = summary['stats']
    return {
        'user_id': str(user_id), 'xp_total': summary['xp_total'],
        'xp_breakdown': summary['xp_breakdown'],
        **level_from_xp(summary['xp_total']),
        'stats': {**stats, 'teams_managed': stats['leagues_joined'],
                  'total_points_for': stats['total_points']},
    }


@router.get("/u/{username}")
async def get_public_profile(username: str):
    """Shareable public profile snapshot."""
    db = _deps["db"]
    username = username.strip()
    user = await db.users.find_one(
        {"username": {"$regex": f"^{re.escape(username)}$", "$options": "i"}},
        {"password_hash": 0},
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = str(user["_id"])

    teams = await db.teams.find({"$or": [{"owner_id": user_id}, {"co_owner_ids": user_id}]}).to_list(None)
    league_ids = list({t["league_id"] for t in teams})
    leagues = await db.leagues.find(
        {"_id": {"$in": [ObjectId(lid) for lid in league_ids]}}
    ).to_list(None)
    leagues_by_id = {str(l["_id"]): l for l in leagues}

    team_cards = []
    active_leagues = []
    for t in teams:
        lg = leagues_by_id.get(t["league_id"]) or {}
        league_is_private = bool(lg.get("is_private"))
        league_status = (lg.get("current_season_status") or "").lower()
        is_active = league_status != "complete"

        league_teams = await db.teams.find(
            {"league_id": t["league_id"]},
            {"_id": 1, "points_for": 1, "live_points": 1},
        ).to_list(None)
        ranked = sorted(
            league_teams,
            key=lambda x: (x.get("points_for", 0.0) or 0.0) + (x.get("live_points", 0.0) or 0.0),
            reverse=True,
        )
        rank = next((i + 1 for i, x in enumerate(ranked) if x["_id"] == t["_id"]), None)

        champ_at = t.get('championship_won_at')
        div_at = t.get('division_winner_at')
        conf_at = t.get('conference_winner_at')
        cons_at = t.get('consolation_won_at')
        runner_at = t.get('playoff_runner_up_at')
        playoffs_at = t.get('playoffs_reached_at')

        # Hide league name + don't render a link for private leagues
        league_display = lg.get("name") if not league_is_private else "Private League"

        team_card = {
            "team_id": str(t["_id"]),
            "team_name": t["name"],
            "league_id": t["league_id"] if not league_is_private else None,
            "league_name": league_display,
            "league_is_private": league_is_private,
            "league_format": lg.get("format"),
            "league_sport": lg.get("sport", "nhl"),
            "league_status": league_status,
            "is_active": is_active,
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": round((t.get("points_for", 0.0) or 0.0) + (t.get("live_points", 0.0) or 0.0), 2),
            "rank": rank,
            "total_teams": len(league_teams),
            "live_points": round(t.get("live_points", 0.0) or 0.0, 2),
            "championship_won_at": champ_at,
            "division_winner_at": div_at,
            "conference_winner_at": conf_at,
            "consolation_won_at": cons_at,
            "playoff_runner_up_at": runner_at,
            "playoffs_reached_at": playoffs_at,
        }
        team_cards.append(team_card)
        if is_active:
            active_leagues.append(team_card)

    lifetime_best: Optional[dict] = None
    if teams:
        from live_scoring_worker import _fantasy_points_from_live
        roster_ids = set()
        for t in teams:
            roster_ids.update(t.get("roster") or [])
        if roster_ids:
            players = await db.players.find(
                {"_id": {"$in": [ObjectId(p) for p in list(roster_ids)[:500]]}},
                {"name": 1, "team": 1, "position": 1, "player_type": 1, "live_stats": 1},
            ).to_list(500)
            for p in players:
                is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
                for _gid, ls in (p.get("live_stats") or {}).items():
                    fpts = _fantasy_points_from_live(ls, is_g)
                    if not lifetime_best or fpts > lifetime_best["fpts"]:
                        lifetime_best = {
                            "id": str(p["_id"]),
                            "name": p.get("name"),
                            "team": p.get("team"),
                            "position": p.get("position"),
                            "is_goalie": is_g,
                            "goals": ls.get("goals", 0) or 0,
                            "assists": ls.get("assists", 0) or 0,
                            "shots": ls.get("shots", 0) or 0,
                            "saves": ls.get("saves", 0) or 0,
                            "goals_against": ls.get("goals_against", 0) or 0,
                            "fpts": round(fpts, 2),
                        }

    from services.profile_career import career_summary
    from utils.xp import level_from_xp
    summary = await career_summary(db, user_id)
    return {
        'username': user.get('username'),
        'display_name': user.get('name') or user.get('username'),
        'member_since': user.get('created_at'),
        'xp_total': summary['xp_total'], 'xp_breakdown': summary['xp_breakdown'], **level_from_xp(summary['xp_total']),
        'stats': summary['stats'], 'teams': team_cards, 'active_leagues': active_leagues,
        'trophies': summary['trophies'], 'lifetime_top_performer': lifetime_best,
    }


# ─── Profile edit + avatar ────────────────────────────────────────────────
@router.put("/users/me/profile")
async def update_my_profile(payload: ProfileUpdate, request: Request):
    """Update the current user's profile fields.

    Validates uniqueness on `username` (case-insensitive) and `email`. The
    payload is sparse — only provided fields are written. Returns the
    refreshed user document (excluding password_hash).
    """
    db = _deps["db"]
    user = await _deps["get_current_user"](request)

    updates: dict = {}
    if payload.username is not None and payload.username != user.get("username"):
        clash = await db.users.find_one({
            "username": {"$regex": f"^{re.escape(payload.username)}$", "$options": "i"},
            "_id": {"$ne": ObjectId(user["_id"])},
        })
        if clash:
            raise HTTPException(status_code=409, detail="Username already taken")
        updates["username"] = payload.username
        updates["username_key"] = payload.username.lower()
        updates["name"] = payload.username
    if payload.email is not None and payload.email.lower() != (user.get("email") or "").lower():
        clash = await db.users.find_one({
            "email": {"$regex": f"^{re.escape(payload.email)}$", "$options": "i"},
            "_id": {"$ne": ObjectId(user["_id"])},
        })
        if clash:
            raise HTTPException(status_code=409, detail="Email already in use")
        account = await db.users.find_one({"_id": ObjectId(user["_id"])})
        if not payload.current_password or not _deps["verify_password"](payload.current_password, account.get("password_hash", "")):
            raise HTTPException(400, "Current password is required to change email")
        from services.account_verification import issue
        await issue(db, _deps, account, payload.email.lower())
    for field in ("favourite_sport", "favourite_team", "city", "province_state", "country", "avatar_url"):
        value = getattr(payload, field)
        if value is not None and value != user.get(field):
            updates[field] = value or None

    if not updates:
        return {"updated": False, "user": _public_user(user)}

    updates["updated_at"] = datetime.now(timezone.utc)
    from pymongo.errors import DuplicateKeyError
    try:
        await db.users.update_one({"_id": ObjectId(user["_id"])}, {"$set": updates})
    except DuplicateKeyError:
        raise HTTPException(409, "Username already taken")
    if "username" in updates:
        await db.account_history.insert_one({"user_id": user["_id"], "action": "username_change", "before": user.get("username"), "after": updates["username"], "at": datetime.now(timezone.utc)})
    fresh = await db.users.find_one({"_id": ObjectId(user["_id"])})
    return {"updated": True, "user": _public_user(fresh)}


# Iter 232N.19 — Dashboard layout sync (widget order across devices).
# Stored as `dashboard_layout` on the user doc:
#   { widget_order: ["my-leagues", "pending-trades", ...],
#     updated_at: ISO-8601 UTC }
# We keep this deliberately schema-light: any string ids the client
# doesn't recognise are dropped/appended by the client's `loadWidgetOrder`
# helper so we don't have to migrate server-side when new widgets ship.


@router.get("/users/me/dashboard-layout")
async def get_my_dashboard_layout(request: Request):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    fresh = await db.users.find_one(
        {"_id": ObjectId(user["_id"])},
        {"dashboard_layout": 1},
    )
    layout = (fresh or {}).get("dashboard_layout") or {}
    return {
        "widget_order": layout.get("widget_order") or [],
        "updated_at": layout.get("updated_at"),
    }


@router.patch("/users/me/dashboard-layout")
async def patch_my_dashboard_layout(payload: dict, request: Request):
    """Persist the caller's widget order across devices.

    Body: `{ "widget_order": ["my-leagues", "pending-trades", ...] }`.
    Order is stored verbatim — clients drop unknown ids on load. Payload
    is capped to prevent unbounded growth (32 entries, each ≤64 chars).
    """
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    widget_order = payload.get("widget_order")
    if not isinstance(widget_order, list):
        raise HTTPException(
            status_code=400, detail="widget_order must be a list of ids",
        )
    if len(widget_order) > 32:
        raise HTTPException(status_code=400, detail="widget_order is too long")
    cleaned = []
    for wid in widget_order:
        if not isinstance(wid, str):
            continue
        wid = wid.strip()
        if not wid or len(wid) > 64:
            continue
        cleaned.append(wid)
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$set": {
            "dashboard_layout": {"widget_order": cleaned, "updated_at": now},
            "updated_at": now,
        }},
    )
    return {"widget_order": cleaned, "updated_at": now.isoformat()}


# ─── Iter 232N.29 — League Home layout sync ───────────────────────────────
# Per-league widget order + visibility so managers get consistent layouts
# across devices. Stored under `league_home_layouts` on the user doc:
#   { "<league_id>": { widget_order, visibility, updated_at }, ... }
# `visibility` is optional — if missing we treat all widgets as visible.
# Same "schema-light" contract as the dashboard: unknown ids are the
# client's problem to reconcile (see `useLeagueHomeConfig`).


def _validate_league_home_payload(payload: dict) -> tuple[list, dict]:
    widget_order = payload.get("widget_order")
    if widget_order is not None and not isinstance(widget_order, list):
        raise HTTPException(
            status_code=400, detail="widget_order must be a list of ids",
        )
    cleaned_order: list = []
    for wid in (widget_order or []):
        if not isinstance(wid, str):
            continue
        wid = wid.strip()
        if not wid or len(wid) > 64:
            continue
        cleaned_order.append(wid)
    if len(cleaned_order) > 32:
        raise HTTPException(status_code=400, detail="widget_order is too long")
    visibility = payload.get("visibility") or {}
    if not isinstance(visibility, dict):
        raise HTTPException(
            status_code=400, detail="visibility must be an object of {id: bool}",
        )
    cleaned_vis: dict = {}
    for wid, shown in visibility.items():
        if isinstance(wid, str) and len(wid) <= 64 and isinstance(shown, bool):
            cleaned_vis[wid.strip()] = shown
    if len(cleaned_vis) > 32:
        raise HTTPException(status_code=400, detail="visibility is too long")
    return cleaned_order, cleaned_vis


@router.get("/users/me/league-home-layout/{league_id}")
async def get_my_league_home_layout(league_id: str, request: Request):
    """Return the caller's persisted widget order + visibility for one
    league. Empty payload if none saved yet — the client will fall back
    to its LEAGUE_HOME_WIDGETS defaults.
    """
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    fresh = await db.users.find_one(
        {"_id": ObjectId(user["_id"])},
        {"league_home_layouts": 1},
    )
    layouts = (fresh or {}).get("league_home_layouts") or {}
    entry = layouts.get(league_id) or {}
    return {
        "league_id": league_id,
        "widget_order": entry.get("widget_order") or [],
        "visibility": entry.get("visibility") or {},
        # Iter 232N.31 — Sticky flag that gates the first-run smart-order.
        # Once true (either because the user saved a manual layout OR
        # the client auto-arranged on first visit), we never re-run the
        # relevance sort again.
        "first_run_completed": bool(entry.get("first_run_completed", False)),
        "updated_at": entry.get("updated_at"),
    }


@router.patch("/users/me/league-home-layout/{league_id}")
async def patch_my_league_home_layout(league_id: str, payload: dict, request: Request):
    """Persist per-league widget order + visibility across devices."""
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    cleaned_order, cleaned_vis = _validate_league_home_payload(payload)
    now = datetime.now(timezone.utc)
    # Use dotted paths so we only touch the league we're editing;
    # other leagues' saved layouts stay untouched.
    updates: dict = {
        f"league_home_layouts.{league_id}.updated_at": now,
        "updated_at": now,
    }
    if payload.get("widget_order") is not None:
        updates[f"league_home_layouts.{league_id}.widget_order"] = cleaned_order
    if payload.get("visibility") is not None:
        updates[f"league_home_layouts.{league_id}.visibility"] = cleaned_vis
    # Iter 232N.31 — Optional first-run marker. `True` locks in the
    # current order so smart-arrange never touches it again. Once set,
    # only an explicit reset can flip it back.
    if isinstance(payload.get("first_run_completed"), bool):
        updates[f"league_home_layouts.{league_id}.first_run_completed"] = payload["first_run_completed"]
    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$set": updates},
    )
    return {
        "league_id": league_id,
        "widget_order": cleaned_order,
        "visibility": cleaned_vis,
        "first_run_completed": bool(payload.get("first_run_completed", False)),
        "updated_at": now.isoformat(),
    }


@router.post("/users/me/avatar")
async def upload_my_avatar(request: Request, file: UploadFile = File(...)):
    """Upload an avatar image (PNG/JPEG/WEBP/GIF, max 1 MB, resized to 256×256 PNG)."""
    db = _deps["db"]
    user = await _deps["get_current_user"](request)

    if file.content_type not in ALLOWED_AVATAR_MIME:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use PNG, JPEG, WEBP, or GIF.")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image too large. Max size is 1 MB.")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.load()
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.thumbnail(AVATAR_OUTPUT_SIZE, Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        data_url = f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode('ascii')}"
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("avatar processing failed")
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}")

    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$set": {"avatar_url": data_url, "avatar_updated_at": datetime.now(timezone.utc)}},
    )
    return {"avatar_url": data_url}


@router.delete("/users/me/avatar")
async def delete_my_avatar(request: Request):
    db = _deps["db"]
    user = await _deps["get_current_user"](request)
    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$unset": {"avatar_url": "", "avatar_updated_at": ""}},
    )
    return {"avatar_url": None}


def _public_user(user: dict) -> dict:
    """Strip sensitive fields and reshape for API responses."""
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "name": user.get("name") or user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "favourite_sport": user.get("favourite_sport"),
        "favourite_team": user.get("favourite_team"),
        "city": user.get("city"),
        "province_state": user.get("province_state"),
        "country": user.get("country"),
        "avatar_url": user.get("avatar_url"),
        "created_at": user.get("created_at"),
    }

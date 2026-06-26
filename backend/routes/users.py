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

LEVEL_TITLES = [
    (1, 5, "Bench Warmer"),
    (6, 15, "Rink Regular"),
    (16, 30, "Line Captain"),
    (31, 50, "Hat Trick Hero"),
    (51, 75, "Playoff Contender"),
    (76, 999, "Stanley Cup Dynasty"),
]


def _title_for_level(level: int) -> str:
    for lo, hi, title in LEVEL_TITLES:
        if lo <= level <= hi:
            return title
    return "Rookie"


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

    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    total_team_count = len(teams)
    total_wins = sum(t.get("wins", 0) or 0 for t in teams)
    total_points_for = sum(t.get("points_for", 0.0) or 0.0 for t in teams)
    total_live_points = sum(t.get("live_points", 0.0) or 0.0 for t in teams)

    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": [str(t["_id"]) for t in teams]},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": [str(t["_id"]) for t in teams]},
    }) if teams else 0

    xp = int(
        total_team_count * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + (total_points_for + total_live_points) / 5
    )

    level = 1
    xp_remaining = xp
    while True:
        cost = 100 + level * 50
        if xp_remaining < cost:
            break
        xp_remaining -= cost
        level += 1
    xp_to_next = (100 + level * 50) - xp_remaining

    return {
        "user_id": str(user_id),
        "level": level,
        "title": _title_for_level(level),
        "xp_total": xp,
        "xp_in_level": xp_remaining,
        "xp_to_next_level": xp_to_next,
        "xp_required_for_next": 100 + level * 50,
        "progress_pct": round((xp_remaining / (100 + level * 50)) * 100, 1),
        "stats": {
            "teams_managed": total_team_count,
            "total_wins": total_wins,
            "trades_accepted": trades_executed,
            "drafts_completed": drafts_completed,
            "waiver_claims": waiver_claims,
            "total_points_for": round(total_points_for + total_live_points, 2),
        },
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

    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    league_ids = list({t["league_id"] for t in teams})
    leagues = await db.leagues.find(
        {"_id": {"$in": [ObjectId(lid) for lid in league_ids]}}
    ).to_list(100)
    leagues_by_id = {str(l["_id"]): l for l in leagues}

    # Snapshot points-for ranks per (league, season_year) — used for the
    # regular-season top-3 trophies. Map[league_id][season_year] -> [team_id ranked desc by PF].
    rank_index: dict = {}
    async for snap in db.league_seasons.find(
        {"league_id": {"$in": league_ids}},
        {"league_id": 1, "season_year": 1, "teams": 1},
    ):
        lid = snap["league_id"]
        yr = snap.get("season_year")
        ranked = sorted(
            snap.get("teams") or [],
            key=lambda x: float(x.get("points_for") or 0.0),
            reverse=True,
        )
        rank_index.setdefault(lid, {})[yr] = [t.get("team_id") for t in ranked]

    team_cards = []
    trophies = []
    active_leagues = []
    championships_won = 0
    division_titles = 0
    conference_titles = 0
    consolations_won = 0
    runner_ups = 0
    playoff_appearances = 0
    regular_season_top3 = 0
    total_wins = total_losses = total_ties = 0
    total_points_for = 0.0

    for t in teams:
        lg = leagues_by_id.get(t["league_id"]) or {}
        league_is_private = bool(lg.get("is_private"))
        league_status = (lg.get("current_season_status") or "").lower()
        is_active = league_status != "complete"

        league_teams = await db.teams.find(
            {"league_id": t["league_id"]},
            {"_id": 1, "points_for": 1, "live_points": 1},
        ).to_list(100)
        ranked = sorted(
            league_teams,
            key=lambda x: (x.get("points_for", 0.0) or 0.0) + (x.get("live_points", 0.0) or 0.0),
            reverse=True,
        )
        rank = next((i + 1 for i, x in enumerate(ranked) if x["_id"] == t["_id"]), None)

        total_wins += t.get("wins", 0) or 0
        total_losses += t.get("losses", 0) or 0
        total_ties += t.get("ties", 0) or 0
        total_points_for += (t.get("points_for", 0.0) or 0.0) + (t.get("live_points", 0.0) or 0.0)

        champ_at = t.get("championship_won_at")
        div_at = t.get("division_winner_at")
        conf_at = t.get("conference_winner_at")
        cons_at = t.get("consolation_won_at")
        runner_at = t.get("playoff_runner_up_at")
        playoffs_at = t.get("playoffs_reached_at")
        if champ_at: championships_won += 1
        if div_at: division_titles += 1
        if conf_at: conference_titles += 1
        if cons_at: consolations_won += 1
        if runner_at: runner_ups += 1
        if playoffs_at: playoff_appearances += 1

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

        # ─── Trophy case entries: playoff winner + runner-up + regular season top 3 ───
        # Only emit a single playoff trophy per team (winner OR runner-up,
        # not both) so the trophy case is clean.
        _trophy_base = {
            "league_id": team_card["league_id"],
            "league_name": league_display,
            "league_is_private": league_is_private,
            "team_id": str(t["_id"]),
            "team_name": t["name"],
        }
        if champ_at:
            trophies.append({**_trophy_base, "label": "Playoff Champion",
                             "type": "championship", "place": 1, "earned_at": champ_at})
        elif runner_at:
            trophies.append({**_trophy_base, "label": "Playoff Runner-Up",
                             "type": "runner_up", "place": 2, "earned_at": runner_at})
        if conf_at:
            trophies.append({**_trophy_base, "label": "Conference Champion",
                             "type": "conference", "earned_at": conf_at})
        if div_at:
            trophies.append({**_trophy_base, "label": "Division Champion",
                             "type": "division", "earned_at": div_at})
        if cons_at:
            trophies.append({**_trophy_base, "label": "Consolation Winner",
                             "type": "consolation", "earned_at": cons_at})

        # ─── Per-completed-season Regular-Season Top 3 ───
        for yr, team_order in (rank_index.get(t["league_id"]) or {}).items():
            try:
                pos = team_order.index(str(t["_id"]))
            except ValueError:
                continue
            if pos == 0:
                regular_season_top3 += 1
                trophies.append({**_trophy_base, "label": f"Regular Season 1st ({yr})",
                                 "type": "regular_season_first", "place": 1,
                                 "season_year": yr})
            elif pos == 1:
                regular_season_top3 += 1
                trophies.append({**_trophy_base, "label": f"Regular Season 2nd ({yr})",
                                 "type": "regular_season_second", "place": 2,
                                 "season_year": yr})
            elif pos == 2:
                regular_season_top3 += 1
                trophies.append({**_trophy_base, "label": f"Regular Season 3rd ({yr})",
                                 "type": "regular_season_third", "place": 3,
                                 "season_year": yr})

    # Sort trophies by `earned_at` desc (no date trophies go last)
    def _trophy_sort_key(tr):
        dt = tr.get("earned_at") or tr.get("season_year")
        return (0, dt) if dt else (1, "")
    trophies.sort(key=_trophy_sort_key, reverse=True)

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

    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": [str(t["_id"]) for t in teams]},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": [str(t["_id"]) for t in teams]},
    }) if teams else 0

    xp = int(
        len(teams) * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + total_points_for / 5
        + championships_won * 500
        + conference_titles * 250
        + division_titles * 150
        + consolations_won * 100
        + playoff_appearances * 75
    )
    level = 1
    xp_rem = xp
    while True:
        cost = 100 + level * 50
        if xp_rem < cost:
            break
        xp_rem -= cost
        level += 1

    return {
        "username": user.get("username"),
        "display_name": user.get("name") or user.get("username"),
        "member_since": user.get("created_at"),
        "level": level,
        "title": _title_for_level(level),
        "xp_in_level": xp_rem,
        "xp_required_for_next": 100 + level * 50,
        "progress_pct": round((xp_rem / (100 + level * 50)) * 100, 1),
        "stats": {
            "leagues_joined": len(teams),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_ties": total_ties,
            "total_points": round(total_points_for, 2),
            "trades_accepted": trades_executed,
            "drafts_completed": drafts_completed,
            "waiver_claims": waiver_claims,
            "championships_won": championships_won,
            "conference_titles": conference_titles,
            "division_titles": division_titles,
            "consolations_won": consolations_won,
            "runner_ups": runner_ups,
            "regular_season_top3": regular_season_top3,
            "playoff_appearances": playoff_appearances,
        },
        "teams": team_cards,
        "active_leagues": active_leagues,
        "trophies": trophies,
        "lifetime_top_performer": lifetime_best,
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
            "_id": {"$ne": user["_id"]},
        })
        if clash:
            raise HTTPException(status_code=409, detail="Username already taken")
        updates["username"] = payload.username
    if payload.email is not None and payload.email.lower() != (user.get("email") or "").lower():
        clash = await db.users.find_one({
            "email": {"$regex": f"^{re.escape(payload.email)}$", "$options": "i"},
            "_id": {"$ne": user["_id"]},
        })
        if clash:
            raise HTTPException(status_code=409, detail="Email already in use")
        updates["email"] = payload.email.lower()
    for field in ("favourite_sport", "favourite_team", "city", "province_state", "country", "avatar_url"):
        value = getattr(payload, field)
        if value is not None and value != user.get(field):
            updates[field] = value or None

    if not updates:
        return {"updated": False, "user": _public_user(user)}

    updates["updated_at"] = datetime.now(timezone.utc)
    await db.users.update_one({"_id": ObjectId(user["_id"])}, {"$set": updates})
    fresh = await db.users.find_one({"_id": ObjectId(user["_id"])})
    return {"updated": True, "user": _public_user(fresh)}


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

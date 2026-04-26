"""Stat Comparator + Pro paywall.

Pro paywall model
-----------------
Each user has these fields auto-managed:
- `is_pro: bool` — set via the admin toggle. Pro users have unlimited compares.
- `comparisons_used_this_month: int` — increments per non-Pro compare.
- `comparisons_period_start: datetime` — month boundary; resets the counter.

Free tier: **3 comparisons per calendar month**. Once exhausted, a non-Pro
user receives `402 Payment Required` and the frontend shows a paywall modal.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}

FREE_QUOTA_PER_MONTH = 3


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _period_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


async def _scoring_cfg(db, league_id: Optional[str]):
    if not league_id:
        return None
    return await db.scoring_configs.find_one({"league_id": league_id})


async def _ensure_quota(db, user: dict) -> dict:
    """Reset the monthly counter when crossing a month boundary, then return
    the current `is_pro` status + remaining comparisons."""
    now = datetime.now(timezone.utc)
    period = _period_start(now)
    period_key = now.strftime("%Y-%m")  # store as YYYY-MM string to dodge tz nightmares
    is_pro = bool(user.get("is_pro"))
    used = int(user.get("comparisons_used_this_month") or 0)
    user_period_key = user.get("comparisons_period_key")
    user_oid = ObjectId(user["_id"]) if isinstance(user["_id"], str) else user["_id"]
    if user_period_key != period_key:
        used = 0
        await db.users.update_one(
            {"_id": user_oid},
            {"$set": {
                "comparisons_used_this_month": 0,
                "comparisons_period_key": period_key,
                "comparisons_period_start": period,
            }},
        )
    return {"is_pro": is_pro, "used": used, "remaining": max(0, FREE_QUOTA_PER_MONTH - used), "user_oid": user_oid}


@router.get("/users/me/pro-status")
async def get_pro_status(request: Request):
    db = _db()
    user = await _get_user(request)
    q = await _ensure_quota(db, user)
    return {
        "is_pro": q["is_pro"],
        "free_quota_per_month": FREE_QUOTA_PER_MONTH,
        "comparisons_used_this_month": q["used"],
        "comparisons_remaining": (None if q["is_pro"] else q["remaining"]),
    }


@router.post("/admin/users/{user_id}/pro")
async def admin_toggle_pro(user_id: str, payload: dict, request: Request):
    """Site-admin: enable/disable Pro for a user. Useful for testing the
    Stat Comparator paywall before Stripe is wired."""
    import os
    db = _db()
    actor = await _get_user(request)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    if actor.get("email") != admin_email:
        raise HTTPException(status_code=403, detail="Site admin only")
    is_pro = bool(payload.get("is_pro"))
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    res = await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_pro": is_pro}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "is_pro": is_pro}


def _build_stat_row(player: dict, season: Optional[str], history: dict, scoring_cfg: dict, calc_fn):
    """Pick the requested season's stats from the historical-stats payload
    (or use the live current-season stats from the player doc when
    season=None or 'current'). Returns a flat row plus computed FPTS."""
    is_goalie = (player.get("position") == "G")
    if not season or season in ("current", history.get("current_season")):
        # Current season — use the live player doc
        stats = {
            "goals": player.get("goals", 0), "assists": player.get("assists", 0),
            "points": player.get("points", 0), "plus_minus": player.get("plus_minus", 0),
            "shots": player.get("shots", 0),
            "ppg": player.get("power_play_goals", 0),
            "ppp": player.get("power_play_points", 0),
            "shg": player.get("short_handed_goals", 0),
            "pim": player.get("penalty_minutes", 0),
            "saves": player.get("saves", 0),
            "goals_against": player.get("goals_against", 0),
            "wins": player.get("wins", 0),
            "losses": player.get("losses", 0),
            "shutouts": player.get("shutouts", 0),
            "games_played": player.get("games_played", 0),
        }
        season_label = "Current"
    else:
        rec = next((s for s in history.get("seasons") or [] if s.get("season") == season), None)
        if not rec:
            return None
        stats = {
            "goals": rec.get("goals", 0), "assists": rec.get("assists", 0),
            "points": rec.get("points", 0), "plus_minus": rec.get("plus_minus", 0),
            "shots": rec.get("shots", 0),
            "ppg": rec.get("power_play_goals", 0),
            "ppp": rec.get("power_play_points", 0),
            "shg": rec.get("short_handed_goals", 0) or 0,
            "pim": rec.get("pim", 0),
            "saves": rec.get("saves", 0) or 0,
            "goals_against": rec.get("goals_against", 0) or 0,
            "wins": rec.get("wins", 0) or 0,
            "losses": rec.get("losses", 0) or 0,
            "shutouts": rec.get("shutouts", 0) or 0,
            "games_played": rec.get("games_played", 0),
        }
        season_label = season
    fpts_payload = dict(stats)
    fpts_payload["position"] = player.get("position") or "C"
    fpts_payload["player_type"] = "goalie" if is_goalie else "skater"
    fpts = calc_fn(fpts_payload, scoring_cfg)
    return {
        "season": season_label,
        "is_goalie": is_goalie,
        "stats": stats,
        "fantasy_points": round(fpts, 2),
        "fpts_per_game": round(fpts / max(1, stats["games_played"]), 2) if stats["games_played"] else 0.0,
    }


@router.post("/comparisons/compare")
async def compare_players(payload: dict, request: Request):
    """Compare two players' stats side-by-side.

    Request body: {
        "player_a_id": "...",
        "player_b_id": "...",
        "season_a": null | "2023-24" | "current",
        "season_b": null | "2022-23" | "current",
        "league_id": "..."   (optional but strongly recommended — drives FPTS)
    }

    Paywall: non-Pro users get **3 free comparisons per calendar month**.
    The 4th call returns 402 with an "upgrade_required" payload.
    """
    db = _db()
    user = await _get_user(request)

    # Quota check
    q = await _ensure_quota(db, user)
    if not q["is_pro"] and q["remaining"] <= 0:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "upgrade_required",
                "message": "You've used your 3 free comparisons this month. Upgrade to Pro for unlimited.",
                "free_quota_per_month": FREE_QUOTA_PER_MONTH,
                "comparisons_used_this_month": q["used"],
            },
        )

    pa_id = payload.get("player_a_id")
    pb_id = payload.get("player_b_id")
    season_a = payload.get("season_a")
    season_b = payload.get("season_b")
    league_id = payload.get("league_id")
    if not pa_id or not pb_id:
        raise HTTPException(status_code=400, detail="player_a_id and player_b_id are required")

    pa = await db.players.find_one({"_id": ObjectId(pa_id)})
    pb = await db.players.find_one({"_id": ObjectId(pb_id)})
    if not pa or not pb:
        raise HTTPException(status_code=404, detail="One or both players not found")
    pa["_id"] = str(pa["_id"])
    pb["_id"] = str(pb["_id"])

    scoring_cfg = await _scoring_cfg(db, league_id)
    calc_fn = _deps.get("calculate_fantasy_points")
    if not calc_fn:
        raise HTTPException(status_code=500, detail="Scoring calculator unavailable")

    # Fetch each player's career history once so the season picker works.
    # Reuse the helper logic from routes.players via a delegated call.
    from routes.players import get_player_historical_stats
    hist_a = await get_player_historical_stats(pa_id, league_id=league_id)
    hist_b = await get_player_historical_stats(pb_id, league_id=league_id)

    row_a = _build_stat_row(pa, season_a, hist_a, scoring_cfg, calc_fn)
    row_b = _build_stat_row(pb, season_b, hist_b, scoring_cfg, calc_fn)
    if not row_a or not row_b:
        raise HTTPException(status_code=400, detail="Selected season has no data for one of the players")

    # Increment quota AFTER successful build (don't burn quota on errors)
    if not q["is_pro"]:
        await db.users.update_one(
            {"_id": q["user_oid"]},
            {"$inc": {"comparisons_used_this_month": 1}},
        )

    diff_fpts = round(row_a["fantasy_points"] - row_b["fantasy_points"], 2)

    return {
        "player_a": {
            "id": pa["_id"], "name": pa.get("name"),
            "team": pa.get("team"), "position": pa.get("position"),
            **row_a,
        },
        "player_b": {
            "id": pb["_id"], "name": pb.get("name"),
            "team": pb.get("team"), "position": pb.get("position"),
            **row_b,
        },
        "league_id": league_id,
        "fpts_diff": diff_fpts,                    # +N => A leads
        "winner": "a" if diff_fpts > 0 else ("b" if diff_fpts < 0 else "tie"),
        "available_seasons": {
            "a": [s["season"] for s in (hist_a.get("seasons") or [])] + ["Current"],
            "b": [s["season"] for s in (hist_b.get("seasons") or [])] + ["Current"],
        },
        "is_pro": q["is_pro"],
        "comparisons_remaining": None if q["is_pro"] else max(0, FREE_QUOTA_PER_MONTH - q["used"] - 1),
    }

"""Skill rating system (ELO-based) for teams, users, and leagues.

Standard chess defaults: starting rating 1500, K-factor 32.

When a matchup completes, both team ratings are updated using the standard
ELO formula. A win against a higher-rated opponent yields more points than
a win against a lower-rated opponent. The K-factor (32) is fixed.

User rating = simple average of every team rating they have ever had
(across every league, across the team's entire rating history).

League rating = simple average of every team in that league's current rating.

Tier mapping (cross-league, platform-wide percentile):
    Rookie         bottom 20%
    Contender      20-40%
    Veteran        40-60%
    All-Star       60-80%
    Hall of Famer  80-95%
    Elite          95-99%
    Legend         top 1%
"""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}

# ─── Constants ────────────────────────────────────────────────
START_RATING = 1500.0
K_FACTOR = 32.0

# Lowest-to-highest tiers. Each tuple = (min_percentile_inclusive, max_percentile_exclusive, name).
TIERS: List[tuple] = [
    (0.0, 20.0, "Rookie"),
    (20.0, 40.0, "Contender"),
    (40.0, 60.0, "Veteran"),
    (60.0, 80.0, "All-Star"),
    (80.0, 95.0, "Hall of Famer"),
    (95.0, 99.0, "Elite"),
    (99.0, 100.0001, "Legend"),
]


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pure helpers ─────────────────────────────────────────────
def expected_score(rating_a: float, rating_b: float) -> float:
    """Standard ELO expected-score: 1 / (1 + 10^((Rb - Ra) / 400))."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_pair(rating_a: float, rating_b: float, score_a: float, k: float = K_FACTOR) -> tuple:
    """Return (new_a, new_b, delta_a) given score_a ∈ {0, 0.5, 1}."""
    ea = expected_score(rating_a, rating_b)
    delta_a = k * (score_a - ea)
    return rating_a + delta_a, rating_b - delta_a, delta_a


def tier_for_percentile(p: float) -> str:
    """Map a 0-100 percentile to a tier name."""
    if p is None:
        return "Rookie"
    for lo, hi, name in TIERS:
        if lo <= p < hi:
            return name
    return "Legend"


# ─── Matchup ELO application ───────────────────────────────────
async def apply_matchup_elo(league_id: str, matchup: dict) -> Optional[dict]:
    """Update both teams' ratings after a matchup completes.

    Called from `simulate_week()` immediately after a matchup is marked
    completed. Idempotent guard: if matchup.elo_applied is already true,
    skips. Returns the delta dict or None when skipped.
    """
    db = _deps["db"]
    if not matchup or matchup.get("elo_applied"):
        return None
    home_id = matchup.get("home_team_id")
    away_id = matchup.get("away_team_id")
    winner = matchup.get("winner")
    if not home_id or not away_id:
        return None

    home = await db.teams.find_one({"_id": ObjectId(home_id)}, {"rating": 1, "name": 1})
    away = await db.teams.find_one({"_id": ObjectId(away_id)}, {"rating": 1, "name": 1})
    if not home or not away:
        return None
    home_r = float(home.get("rating") or START_RATING)
    away_r = float(away.get("rating") or START_RATING)

    if winner == home_id:
        score_h = 1.0
    elif winner == away_id:
        score_h = 0.0
    else:
        score_h = 0.5  # tie

    new_h, new_a, delta_h = update_pair(home_r, away_r, score_h)
    now = datetime.now(timezone.utc)
    hist_entry_h = {
        "at": now, "matchup_id": str(matchup.get("_id")),
        "league_id": league_id,
        "week": matchup.get("week"),
        "opponent_id": away_id, "opponent_name": away.get("name"),
        "opponent_rating_before": away_r,
        "rating_before": home_r, "rating_after": new_h,
        "delta": delta_h, "score": score_h,
        "result": "W" if score_h == 1.0 else ("L" if score_h == 0.0 else "T"),
    }
    hist_entry_a = {
        "at": now, "matchup_id": str(matchup.get("_id")),
        "league_id": league_id,
        "week": matchup.get("week"),
        "opponent_id": home_id, "opponent_name": home.get("name"),
        "opponent_rating_before": home_r,
        "rating_before": away_r, "rating_after": new_a,
        "delta": -delta_h, "score": 1.0 - score_h,
        "result": "W" if score_h == 0.0 else ("L" if score_h == 1.0 else "T"),
    }
    await db.teams.update_one(
        {"_id": ObjectId(home_id)},
        {"$set": {"rating": round(new_h, 2), "rating_updated_at": now},
         "$push": {"rating_history": hist_entry_h},
         "$max": {"peak_rating": round(new_h, 2)}},
    )
    await db.teams.update_one(
        {"_id": ObjectId(away_id)},
        {"$set": {"rating": round(new_a, 2), "rating_updated_at": now},
         "$push": {"rating_history": hist_entry_a},
         "$max": {"peak_rating": round(new_a, 2)}},
    )
    if matchup.get("_id"):
        await db.matchups.update_one(
            {"_id": matchup["_id"]},
            {"$set": {"elo_applied": True,
                      "elo_home_delta": round(delta_h, 2),
                      "elo_away_delta": round(-delta_h, 2)}},
        )
    return {
        "home_id": home_id, "away_id": away_id,
        "home_before": home_r, "away_before": away_r,
        "home_after": new_h, "away_after": new_a,
        "delta": delta_h,
    }


# ─── Percentile cache ─────────────────────────────────────────
_percentile_cache: dict = {"at": None, "ratings": []}


async def _all_team_ratings() -> List[float]:
    """Pull every non-default rating from the platform.

    Cached for 60s to keep tier lookups cheap.
    """
    db = _deps["db"]
    now = datetime.now(timezone.utc)
    if _percentile_cache["at"] and (now - _percentile_cache["at"]).total_seconds() < 60:
        return _percentile_cache["ratings"]
    ratings = []
    async for t in db.teams.find({"rating": {"$exists": True}}, {"rating": 1}):
        r = t.get("rating")
        if isinstance(r, (int, float)):
            ratings.append(float(r))
    ratings.sort()
    _percentile_cache["at"] = now
    _percentile_cache["ratings"] = ratings
    return ratings


def _percentile_of(rating: float, sorted_ratings: List[float]) -> float:
    """Return the 0-100 percentile of `rating` within `sorted_ratings`."""
    if not sorted_ratings:
        return 50.0
    # Count strictly lower + half of equal (mid-rank for ties)
    lo = 0
    hi = len(sorted_ratings)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_ratings[mid] < rating:
            lo = mid + 1
        else:
            hi = mid
    lower = lo
    # count how many equal
    hi2 = lo
    while hi2 < len(sorted_ratings) and sorted_ratings[hi2] == rating:
        hi2 += 1
    equal = hi2 - lo
    return ((lower + 0.5 * equal) / len(sorted_ratings)) * 100.0


# ─── Endpoints ────────────────────────────────────────────────
@router.get("/teams/{team_id}/rating")
async def team_rating(team_id: str):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one(
        {"_id": _safe_object_id(team_id, "team_id")},
        {"rating": 1, "rating_history": 1, "peak_rating": 1, "name": 1},
    )
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    rating = float(team.get("rating") or START_RATING)
    all_r = await _all_team_ratings()
    pct = _percentile_of(rating, all_r)
    history = team.get("rating_history") or []
    return {
        "team_id": team_id,
        "team_name": team.get("name"),
        "rating": round(rating, 1),
        "peak_rating": round(float(team.get("peak_rating") or rating), 1),
        "percentile": round(pct, 1),
        "tier": tier_for_percentile(pct),
        "history": [
            {**h, "at": h.get("at").isoformat() if h.get("at") else None}
            for h in history[-50:]
        ],
        "matchups_rated": len(history),
    }


@router.get("/users/me/rating")
async def my_rating(request: Request):
    return await _user_rating_payload(await _deps["get_current_user"](request))


@router.get("/users/{user_id}/rating")
async def user_rating(user_id: str):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    user = await db.users.find_one({"_id": _safe_object_id(user_id, "user_id")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _user_rating_payload(user)


@router.get("/u/{username}/rating")
async def user_rating_by_username(username: str):
    """Public rating lookup by username (case-insensitive)."""
    import re
    db = _deps["db"]
    user = await db.users.find_one(
        {"username": {"$regex": f"^{re.escape(username.strip())}$", "$options": "i"}},
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _user_rating_payload(user)


async def _user_rating_payload(user: dict) -> dict:
    """User rating = arithmetic mean of every team rating they have ever had,
    averaged across the team's lifetime (every rating_history entry).

    Falls back to per-team current rating if rating_history is empty.
    """
    db = _deps["db"]
    user_id = user["_id"] if isinstance(user["_id"], str) else str(user["_id"])
    teams = await db.teams.find(
        {"owner_id": user_id},
        {"rating": 1, "rating_history": 1, "peak_rating": 1, "name": 1, "league_id": 1},
    ).to_list(200)

    sample_sum = 0.0
    sample_count = 0
    team_payloads = []
    peak = 0.0
    for t in teams:
        hist = t.get("rating_history") or []
        if hist:
            for h in hist:
                sample_sum += float(h.get("rating_after") or START_RATING)
                sample_count += 1
        else:
            sample_sum += float(t.get("rating") or START_RATING)
            sample_count += 1
        cur = float(t.get("rating") or START_RATING)
        peak = max(peak, float(t.get("peak_rating") or cur))
        team_payloads.append({
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "league_id": t.get("league_id"),
            "rating": round(cur, 1),
            "peak_rating": round(float(t.get("peak_rating") or cur), 1),
            "matchups_rated": len(hist),
        })

    avg = sample_sum / sample_count if sample_count else START_RATING
    all_r = await _all_team_ratings()
    pct = _percentile_of(avg, all_r)
    return {
        "user_id": str(user["_id"]),
        "username": user.get("username"),
        "rating": round(avg, 1),
        "peak_rating": round(peak or avg, 1),
        "percentile": round(pct, 1),
        "tier": tier_for_percentile(pct),
        "teams_count": len(teams),
        "samples": sample_count,
        "teams": team_payloads,
    }


@router.get("/leagues/{league_id}/rating")
async def league_rating(league_id: str):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    teams = await db.teams.find(
        {"league_id": league_id}, {"rating": 1, "name": 1, "peak_rating": 1},
    ).to_list(200)
    if not teams:
        return {
            "league_id": league_id,
            "league_name": league.get("name"),
            "rating": START_RATING, "percentile": 50.0,
            "tier": tier_for_percentile(50.0),
            "teams_count": 0, "team_ratings": [],
        }
    ratings = [float(t.get("rating") or START_RATING) for t in teams]
    avg = sum(ratings) / len(ratings)
    all_r = await _all_team_ratings()
    pct = _percentile_of(avg, all_r)
    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "rating": round(avg, 1),
        "percentile": round(pct, 1),
        "tier": tier_for_percentile(pct),
        "teams_count": len(teams),
        "team_ratings": [
            {"team_id": str(t["_id"]), "team_name": t.get("name"),
             "rating": round(float(t.get("rating") or START_RATING), 1)}
            for t in sorted(teams, key=lambda x: -(x.get("rating") or 0))
        ],
    }


@router.get("/ratings/tiers")
async def tier_definitions():
    """Static tier metadata for the frontend."""
    return {
        "tiers": [
            {"name": name, "min_percentile": lo, "max_percentile": hi}
            for lo, hi, name in TIERS
        ],
        "start_rating": START_RATING,
        "k_factor": K_FACTOR,
    }

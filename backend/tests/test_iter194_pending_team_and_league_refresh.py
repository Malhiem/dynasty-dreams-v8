"""
Iter 194 — Pending-team Pydantic regression + league-list refresh fixes.

Root cause: TeamResponse required `owner_id` + `owner_name` as
non-null strings. The 32-team entry-draft league (iter192) has every
team in pending-invite state with both fields null, so GET /teams
returned a 500 Pydantic ValidationError — and the frontend
interpreted that as "League not found" when navigating into the
league.
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

from routes import teams as teams_routes  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_team_response_accepts_null_owner_fields():
    """Reproduce the 500 by constructing the response from a raw
    pending-team document. The fix makes owner_id / owner_name
    Optional + `is_pending` exposed on the response."""
    raw = {
        "_id": "ffffffffffffffffffffffff",
        "name": "Arctic Wolves",
        "league_id": "6a3785db90689479a24e7ce7",
        "owner_id": None,
        "owner_name": None,
        "is_pending": True,
        # no created_at — should fall back to "now"
    }
    response = teams_routes.team_to_response(raw)
    assert response.owner_id is None
    assert response.owner_name is None
    assert response.is_pending is True
    assert response.name == "Arctic Wolves"


def test_team_response_pre_existing_teams_unaffected():
    raw = {
        "_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "name": "Zarek's Frozen",
        "league_id": "69e46af167999bfb85c39628",
        "owner_id": "69e43c4ddba209f1da22660c",
        "owner_name": "chriszarek",
        "wins": 6, "losses": 1, "ties": 0,
        "points_for": 1200.5,
    }
    response = teams_routes.team_to_response(raw)
    assert response.owner_id == "69e43c4ddba209f1da22660c"
    assert response.owner_name == "chriszarek"
    assert response.is_pending is False
    assert response.wins == 6


def test_league_list_short_ttl_pattern_in_api_js():
    """Frontend regression — the api.js GET cache must apply a 5 s TTL
    to `/leagues?my_leagues=true` so the league dropdown picks up new
    memberships within seconds of joining/creating a league."""
    from pathlib import Path
    src = Path("/app/frontend/src/lib/api.js").read_text()
    assert "SHORT_TTL_PATTERNS" in src
    assert "/leagues\\?my_leagues=true/" in src
    assert "SHORT_TTL_MS = 5_000" in src
    # The cache lookup must consult the short list when matching a key.
    assert "SHORT_TTL_PATTERNS.some((re) => re.test(key))" in src


def test_league_switcher_force_refreshes_on_open():
    """Opening the league switcher must invalidate the cached list so
    a freshly-created league shows up immediately."""
    from pathlib import Path
    src = Path("/app/frontend/src/lovable/components/layout/CurrentLeagueDropdown.tsx").read_text()
    assert "onOpenChange" in src
    assert "reloadMyLeagues" in src
    hook = Path("/app/frontend/src/hooks/use-active-league.js").read_text()
    assert "reloadMyLeagues" in hook
    assert "invalidateApiCache(/leagues\\?my_leagues=true/)" in hook

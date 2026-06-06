"""Iter 131 — Watchlist v2 backend coverage (post Iter-133 widget removal).

Iter 133 removed the standalone `MatchupWatchlistWidget` in favour of
star buttons embedded directly on the existing matchup widgets
(League Home matchup grid + MatchupSideRail "League Live" sidebar).
This test file is the slimmed-down version that only validates the
backend logic that survives — the 8 auto-watch reasons and the H2H
payload on `/api/matchup-stars`.
"""
import os
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", "chriszarek@gmail.com")
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", "Chris2026!")

REPO = Path(__file__).resolve().parents[2]
STARS_ROUTE = REPO / "backend/routes/matchup_stars.py"


def _login(email, password):
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    return r.json().get("access_token") if r.status_code == 200 else None


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def owner_token():
    t = _login(OWNER_EMAIL, OWNER_PW)
    assert t, "Owner login required"
    return t


@pytest.fixture(scope="module")
def owner_league(owner_token):
    leagues = httpx.get(f"{API}/leagues?my_leagues=true", headers=_auth(owner_token), timeout=10).json()
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    for league in leagues:
        if league.get("commissioner_id") == me["id"]:
            return league
    return leagues[0]


def test_new_auto_watch_reasons_in_backend():
    src = STARS_ROUTE.read_text()
    for reason in (
        "rivalry",
        "standings_battle",
        "playoff_clinch",
        "division_lead",
        "conference_lead",
        "last_place_battle",
        "rank_jump",
        "playoff_implications",
    ):
        assert f'"{reason}"' in src, f"Backend missing reason: {reason!r}"
    assert "_leader_lead" in src, "Helper to compute division/conference lead missing"


def test_h2h_returned_in_stars_response(owner_token, owner_league):
    r = httpx.get(
        f"{API}/matchup-stars?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "h2h" in body, "GET /matchup-stars must include h2h section"
    for mid, rec in body["h2h"].items():
        assert "last_season" in rec
        assert "all_time" in rec
        assert "streak_wins" in rec
        assert isinstance(rec["streak_wins"], int)

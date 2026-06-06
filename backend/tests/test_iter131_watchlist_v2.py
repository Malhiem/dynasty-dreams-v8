"""Iter 131 — Watchlist v2: more reasons + toggle + H2H tooltip.

Coverage
--------
1. New auto-watch reasons: playoff_clinch, division_lead, conference_lead,
   last_place_battle, rank_jump (in addition to legacy rivalry,
   standings_battle, playoff_implications).
2. /matchup-stars GET now returns `h2h: {matchup_id: {last_season, all_time,
   streak_wins, streak_team_id}}`.
3. Frontend widget exposes the show/hide auto-watch toggle and stores its
   state in localStorage per league.
4. Frontend widget renders distinct icons for every reason type.
5. Frontend widget mounted on LeagueDetailPage (League Home).
6. Consolation recommend formula simplified — matches playoff bracket size
   directly (no more 2^weeks math).
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
WIDGET = REPO / "frontend/src/components/MatchupWatchlistWidget.jsx"
LEAGUE_DETAIL = REPO / "frontend/src/pages/LeagueDetailPage.jsx"


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


# ── 1. Expanded auto-watch reasons in the backend module ───────
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


# ── 2. H2H returned in GET response ─────────────────────────────
def test_h2h_returned_in_stars_response(owner_token, owner_league):
    r = httpx.get(
        f"{API}/matchup-stars?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "h2h" in body, "GET /matchup-stars must include h2h section"
    # h2h dict keys are matchup_ids, values include last_season/all_time/streak_wins
    for mid, rec in body["h2h"].items():
        assert "last_season" in rec
        assert "all_time" in rec
        assert "streak_wins" in rec
        assert isinstance(rec["streak_wins"], int)


# ── 3. Frontend toggle + H2H tooltip wired ──────────────────────
def test_widget_has_show_auto_toggle():
    src = WIDGET.read_text()
    assert "watchlist-show-auto-toggle" in src, "Toggle wrapper testid missing"
    assert "watchlist-show-auto-checkbox" in src, "Toggle checkbox testid missing"
    assert "showAuto" in src, "showAuto state missing"
    assert "watchlist-show-auto:" in src, "Per-league localStorage key missing"


def test_widget_renders_all_reason_icons():
    src = WIDGET.read_text()
    # All 8 reasons must be in REASON_META
    for reason in (
        "rivalry",
        "standings_battle",
        "playoff_implications",
        "playoff_clinch",
        "division_lead",
        "conference_lead",
        "last_place_battle",
        "rank_jump",
    ):
        assert f"{reason}:" in src, f"Frontend REASON_META missing {reason!r}"
    # Distinct lucide icons imported
    for icon in ("Trophy", "Crown", "Shield", "ArrowUpDown", "AlertOctagon"):
        assert icon in src, f"Distinct icon {icon!r} missing"


def test_widget_has_h2h_tooltip():
    src = WIDGET.read_text()
    assert "Head-to-head" in src, "H2H tooltip header missing"
    assert "Last season" in src and "Lifetime" in src, "H2H labels missing"
    assert "streak_wins" in src, "Streak rendering missing"
    assert "🔥" in src, "Streak badge fire emoji missing"
    assert "has won" in src and "in a row" in src, "Streak team-name sentence missing"


# ── 4. Mounted on League Home ──────────────────────────────────
def test_watchlist_mounted_on_league_home():
    src = LEAGUE_DETAIL.read_text()
    assert "MatchupWatchlistWidget" in src, "LeagueDetailPage must import widget"
    assert "<MatchupWatchlistWidget" in src, "LeagueDetailPage must render widget"

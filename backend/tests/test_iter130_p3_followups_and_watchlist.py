"""Iter 130 — Batched P3 follow-ups + Matchup Watchlist feature.

Coverage
--------
1. **FAAB UI gated on Waivers page**: `Waivers.tsx` now derives
   `isFaabSystem` from `txConfig.waiver.system_type` and conditionally
   renders FAAB tile, bid input, and FAAB-Bid label.

2. **Date+Time picker split into two inputs**: `RulesScheduleTab.tsx`
   adds `rules-schedule-trade-deadline-at-date-input` + `-time-input`
   alongside the legacy combined `datetime-local` (kept hidden for
   back-compat).

3. **More InfoHints on Rosters tab**: 10+ new info-* testids cover
   Prospect Pool, Taxi Squad, Position Limits, Enforce Position,
   Roster Requirements, Min Active, Min Games, Prorate Period,
   Allow Illegal, Prospect Eligibility, IR Eligibility.

4. **Consolation bracket sizing**: PlayoffsScheduleCards computes an
   `idealAlignedSize` based on playoff weeks (≥ 8 when room allows) and
   exposes a "Recommended: N teams" link (`co-teams-recommend` testid).

5. **Matchup Watchlist endpoints**:
   - POST /matchup-stars/{matchup_id} toggles a star.
   - GET /matchup-stars?league_id= returns starred_ids + auto_watch.
   - Auto-watch reasons: rivalry / standings_battle / playoff_implications.
"""
from tests.source_tree import read_source
import os
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"))
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))

REPO = Path(__file__).resolve().parents[2]
WAIVERS_TSX = REPO / "frontend/src/lovable/pages/Waivers.tsx"
RULES_TAB = REPO / "frontend/src/lovable/pages/commissioner/RulesScheduleTab.tsx"
ROSTERS_TAB = REPO / "frontend/src/lovable/pages/commissioner/RostersTab.tsx"
PLAYOFFS_CARDS = REPO / "frontend/src/lovable/pages/commissioner/PlayoffsScheduleCards.tsx"
STARS_ROUTE = REPO / "backend/routes/matchup_stars.py"
WATCHLIST_WIDGET = REPO / "frontend/src/components/MatchupWatchlistWidget.jsx"


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


# ── 1. FAAB UI gated on Waivers page ────────────────────────────
def test_waivers_faab_gated_on_system_type():
    src = read_source(WAIVERS_TSX)
    assert "isFaabSystem" in src, "Waivers.tsx must derive isFaabSystem from txConfig"
    assert "system_type" in src, "Waivers.tsx must read waiver.system_type"
    assert "waiver-faab-tile" in src, "Waivers.tsx must testid the FAAB tile"
    assert "waiver-priority-claim-notice" in src, "Waivers.tsx must show notice for non-FAAB systems"
    # FAAB tile + bid input gated
    assert "isFaabSystem && (" in src or "{isFaabSystem &&" in src, (
        "FAAB tile must be conditional on isFaabSystem"
    )


# ── 2. Date+time picker split ────────────────────────────────────
def test_trade_deadline_picker_has_separate_date_time():
    src = read_source(RULES_TAB)
    assert "rules-schedule-trade-deadline-at-date-input" in src, "Date-only input testid missing"
    assert "rules-schedule-trade-deadline-at-time-input" in src, "Time-only input testid missing"
    # Time input should be disabled until a date is chosen
    assert "disabled={!deadlineAt.slice(0, 10)}" in src or "disabled={!deadlineAt" in src, (
        "Time input should be disabled until date is set"
    )


# ── 3. More InfoHints on Rosters tab ────────────────────────────
def test_rosters_tab_has_full_info_hint_coverage():
    src = read_source(ROSTERS_TAB)
    for tid in (
        "info-prospect-pool",
        "info-taxi-squad",
        "info-position-breakdown",
        "info-enforce-position",
        "info-roster-requirements",
        "info-min-active",
        "info-min-games",
        "info-prorate-period",
        "info-allow-illegal",
        "info-prospect-eligibility",
        "info-ir-eligibility",
    ):
        assert tid in src, f"Missing InfoHint testid {tid!r} on RostersTab"


# ── 4. Consolation bracket sizing improvements ─────────────────
def test_consolation_bracket_recommend_link():
    src = read_source(PLAYOFFS_CARDS)
    assert "idealAlignedSize" in src, "idealAlignedSize derivation missing"
    assert "co-teams-recommend" in src, "Recommended-size link testid missing"
    # Iter 131: now derives from playoffTeams directly (no 2^weeks math)
    assert "Math.min(maxConsolation, playoffTeams)" in src, (
        "Recommend size must match the playoff bracket size"
    )


# ── 5. Matchup Watchlist backend + frontend ────────────────────
def test_matchup_stars_route_present():
    assert STARS_ROUTE.exists()
    src = read_source(STARS_ROUTE)
    assert "@router.post" in src, "POST /matchup-stars route missing"
    assert "@router.get" in src, "GET /matchup-stars route missing"
    assert "_compute_auto_watch_reasons" in src, "Auto-watch computation missing"
    for reason in ("rivalry", "standings_battle", "playoff_implications"):
        assert f'"{reason}"' in src, f"Auto-watch reason {reason!r} not present"


def test_matchup_stars_get_endpoint(owner_token, owner_league):
    r = httpx.get(
        f"{API}/matchup-stars?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["league_id"] == owner_league["id"]
    assert "starred_ids" in body
    assert "auto_watch" in body
    assert isinstance(body["starred_ids"], list)
    assert isinstance(body["auto_watch"], dict)


def test_matchup_stars_toggle(owner_token, owner_league):
    """Toggle a star on the first current-week matchup and verify it round-trips."""
    cw = httpx.get(
        f"{API}/matchups/{owner_league['id']}/current-week",
        headers=_auth(owner_token), timeout=10,
    )
    matchups = (cw.json() or {}).get("matchups", [])
    if not matchups:
        pytest.skip("No current-week matchups to star")
    matchup_id = matchups[0].get("_id") or matchups[0].get("id")
    # Star
    r = httpx.post(
        f"{API}/matchup-stars/{matchup_id}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    starred_state = r.json()["starred"]
    # List should reflect
    listed = httpx.get(
        f"{API}/matchup-stars?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    ).json()
    if starred_state:
        assert matchup_id in listed["starred_ids"]
    # Toggle back to original state
    r2 = httpx.post(
        f"{API}/matchup-stars/{matchup_id}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r2.status_code == 200
    assert r2.json()["starred"] != starred_state


def test_matchup_stars_invalid_id_400(owner_token):
    r = httpx.post(
        f"{API}/matchup-stars/not-a-valid-id",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 400


def test_watchlist_widget_present():
    # Iter 133 — separate widget removed. Matchup star logic is now baked
    # into the MatchupStarButton + the matchup grids themselves.
    star_btn = REPO / "frontend/src/components/MatchupStarButton.jsx"
    assert star_btn.exists(), "MatchupStarButton.jsx must exist"
    src = read_source(star_btn)
    assert "matchup-star-" in src, "Star button testid missing"
    assert "matchup-h2h-info-" in src, "H2H info icon testid missing"

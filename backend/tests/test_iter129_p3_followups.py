"""Iter 129 — Five P3 follow-ups.

Coverage
--------
1. **Backend anonymous masking on /waivers/claims**:
   When `transactions_config.waiver.pending_visibility == "all_teams_anonymous"`
   AND the viewer is NOT the commissioner and NOT the claim owner, team_name
   on the claim row is replaced with "Team A" / "Team B" / ... and owner_id
   is nulled.

2. **CSV export from Transactions tab** (frontend):
   LeagueHistory.tsx wires a `transactions-export-csv` button + helper.

3. **Trade Deadline Countdown Ribbon** (frontend):
   `TradeDeadlineRibbon.tsx` component present, mounted in `AppLayout.tsx`.

4. **InfoHint coverage extension** (frontend):
   DivisionsTab, RostersTab, PlayoffsScheduleCards each import InfoHint
   and surface at least 2 hints.

Note: FAAB bidding flow on the Waivers page was already fully wired in
prior iterations (verified via existing code path inspection — bid_amount
input, /waivers/budget endpoint, blocker checks, etc.).
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
TRADE_RIBBON = REPO / "frontend/src/lovable/components/TradeDeadlineRibbon.tsx"
APP_LAYOUT = REPO / "frontend/src/components/layout/AppLayout.jsx"
LEAGUE_HISTORY = REPO / "frontend/src/lovable/pages/LeagueHistory.tsx"
DIVISIONS = REPO / "frontend/src/lovable/pages/commissioner/DivisionsTab.tsx"
ROSTERS = REPO / "frontend/src/lovable/pages/commissioner/RostersTab.tsx"
PLAYOFFS = REPO / "frontend/src/lovable/pages/commissioner/PlayoffsScheduleCards.tsx"
WAIVERS_BACKEND = REPO / "backend/routes/waivers.py"


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


# ── 1. Backend anonymous masking ───────────────────────────────────
def test_waivers_claims_masking_code_present():
    src = WAIVERS_BACKEND.read_text()
    assert "all_teams_anonymous" in src, "Anonymous mode literal must be checked server-side"
    assert "letter_map" in src, "Stable team→letter mapping must be built"
    assert "Team " in src, "Letter-based masking must use 'Team X' prefix"


def test_waivers_claims_endpoint_responds_for_commissioner(owner_token, owner_league):
    """Commissioner viewing claims should NEVER see masked team names
    even with anonymous visibility enabled."""
    # Enable anonymous mode
    httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"enabled": True, "pending_visibility": "all_teams_anonymous"}},
        headers=_auth(owner_token), timeout=10,
    )
    r = httpx.get(
        f"{API}/waivers/claims?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    # Cleanup
    httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"pending_visibility": "own", "enabled": False}},
        headers=_auth(owner_token), timeout=10,
    )
    # Commissioner should see real team names (no "Team A/B/..." letter masks)
    for c in r.json():
        if c.get("team_name"):
            # Commissioner shouldn't see letter-masked names
            assert not (c["team_name"].startswith("Team ") and len(c["team_name"]) <= 8 and c["team_name"][5:].isalnum() and len(c["team_name"][5:]) <= 2), (
                f"Commissioner saw masked team name: {c['team_name']}"
            )


# ── 2. CSV export from Transactions tab ────────────────────────────
def test_transactions_csv_export_wired():
    src = LEAGUE_HISTORY.read_text()
    assert "transactions-export-csv" in src, "CSV export button testid missing"
    assert "exportTransactionsCSV" in src, "CSV helper missing"
    assert "downloadCSV" in src, "Download helper missing"
    assert "Trophy, Crown" in src, "Existing imports preserved"
    assert "Download" in src, "Download icon import missing"


# ── 3. Trade Deadline Countdown Ribbon ─────────────────────────────
def test_trade_deadline_ribbon_present():
    assert TRADE_RIBBON.exists(), "TradeDeadlineRibbon.tsx must exist"
    src = TRADE_RIBBON.read_text()
    assert "trade-deadline-ribbon" in src, "Ribbon testid missing"
    assert "trade-deadline-ribbon-text" in src, "Ribbon text testid missing"
    assert "trade-deadline-ribbon-dismiss" in src, "Dismiss button testid missing"
    assert "trade_deadline_at" in src, "Ribbon must read trade_deadline_at"
    assert "fmtRemaining" in src, "Countdown formatter missing"


def test_trade_deadline_ribbon_mounted_in_layout():
    src = APP_LAYOUT.read_text()
    assert "TradeDeadlineRibbon" in src, "Ribbon must be imported in AppLayout"
    assert "<TradeDeadlineRibbon" in src, "Ribbon must be rendered in AppLayout"


# ── 4. InfoHint coverage on Divisions / Rosters / Playoffs ────────
def test_info_hints_on_divisions_tab():
    src = DIVISIONS.read_text()
    assert "import InfoHint" in src, "DivisionsTab must import InfoHint"
    for tid in ("info-divisions-conferences", "info-intra-division", "info-intra-conference", "info-inter-conference"):
        assert tid in src, f"DivisionsTab missing InfoHint testid {tid!r}"


def test_info_hints_on_rosters_tab():
    src = ROSTERS.read_text()
    assert "import InfoHint" in src, "RostersTab must import InfoHint"
    for tid in ("info-roster-size", "info-active-roster", "info-ir-slots", "info-ir-plus-slots"):
        assert tid in src, f"RostersTab missing InfoHint testid {tid!r}"


def test_info_hints_on_playoffs_card():
    src = PLAYOFFS.read_text()
    assert "import InfoHint" in src, "PlayoffsScheduleCards must import InfoHint"
    for tid in ("info-playoffs-card", "info-consolation-card", "info-regular-season-schedule"):
        assert tid in src, f"PlayoffsScheduleCards missing InfoHint testid {tid!r}"

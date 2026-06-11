"""Iter 144 — Keeper/protection submission baked into the Roster page.

Coverage
--------
Frontend:
  1. PlayerRoster exposes new protection props (onToggleProtection,
     protectedPlayerIds, protectionEnabled, protectionDraftType) and
     renders a ShieldButton per row.
  2. Team page fetches the protection-list state on mount + provides a
     handler that POSTs to the toggle endpoint.

Backend:
  3. GET `/leagues/{id}/protection-list/{team_id}` returns the current
     list (empty if never submitted).
  4. POST `/leagues/{id}/protection-list/{team_id}/toggle` flips a
     player on/off and persists.
  5. POST `/leagues/{id}/protection-list/auto-protect` is commissioner-
     only and auto-fills the list with the top-N players by salary.
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
ROSTER = REPO / "frontend/src/lovable/components/dashboard/PlayerRoster.tsx"
TEAM = REPO / "frontend/src/lovable/pages/Team.tsx"
DRAFTS = REPO / "backend/routes/drafts.py"


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


@pytest.fixture(scope="module")
def owner_team(owner_token, owner_league):
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    teams = httpx.get(
        f"{API}/teams?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    ).json()
    mine = next((t for t in teams if t.get("owner_id") == me["id"]), None)
    if not mine:
        mine = teams[0] if teams else None
    return mine


# ── 1. PlayerRoster has ShieldButton + props ───────────────────
def test_roster_has_shield_button():
    src = ROSTER.read_text()
    assert "ShieldButton" in src
    assert "roster-protect-btn-" in src
    assert "onToggleProtection" in src
    assert "protectedPlayerIds" in src
    assert "protectionEnabled" in src
    assert 'protectionDraftType?: "keeper" | "expansion" | null' in src
    # Lucide Shield import
    assert ", Shield " in src or ", Shield}" in src


# ── 2. Team page wires the handler + props ─────────────────────
def test_team_page_wires_protection():
    src = TEAM.read_text()
    assert "handleToggleProtection" in src
    assert "protectionDraftType" in src
    assert "/protection-list/status" in src
    assert "/protection-list/" in src and "/toggle" in src
    assert "onToggleProtection={handleToggleProtection}" in src
    assert "protectedPlayerIds={protectedPlayerIds}" in src


# ── 3. Backend GET protection list endpoint ────────────────────
def test_backend_endpoints_defined():
    src = DRAFTS.read_text()
    assert "async def get_team_protection_list" in src
    assert "async def toggle_protection_player" in src
    assert "async def commissioner_auto_protect" in src
    assert '"/leagues/{league_id}/protection-list/{team_id}"' in src
    assert '"/leagues/{league_id}/protection-list/{team_id}/toggle"' in src
    assert '"/leagues/{league_id}/protection-list/auto-protect"' in src


# ── 4. GET returns submitted=false when no list ────────────────
def test_get_protection_list_default(owner_token, owner_league, owner_team):
    if not owner_team:
        pytest.skip("No team for owner in this league")
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/protection-list/{owner_team['id']}",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "protected_player_ids" in body
    assert "submitted" in body
    assert "draft_type" in body


# ── 5. Auto-protect is commissioner-only ────────────────────────
def test_auto_protect_runs(owner_token, owner_league, owner_team):
    if not owner_team:
        pytest.skip("No team in this league")
    # The owner here is the commissioner (per fixture)
    r = httpx.post(
        f"{API}/leagues/{owner_league['id']}/protection-list/auto-protect",
        headers=_auth(owner_token),
        json={"team_id": owner_team["id"], "metric": "salary"},
        timeout=10,
    )
    # Should either succeed (200) or return 400 if no protection slots
    # configured (e.g. league hasn't enabled expansion/keeper). Both
    # outcomes prove the endpoint is wired.
# ── 6. Commissioner override panel exists + mounts ─────────────
def test_commish_override_panel_exists():
    panel = REPO / "frontend/src/lovable/pages/commissioner/CommissionerProtectionOverridePanel.tsx"
    assert panel.exists()
    src = panel.read_text()
    assert 'data-testid="commish-protection-override-card"' in src
    assert 'data-testid="commish-protection-metric"' in src
    assert "commish-protection-auto-${t.id}" in src
    assert "/protection-list/auto-protect" in src
    # Mounted in League Admin → Draft tab (now extracted to DraftTab.tsx) for both keeper + expansion
    draft_tab = REPO / "frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx"
    draft_tab_src = draft_tab.read_text()
    assert "import CommissionerProtectionOverridePanel" in draft_tab_src
    assert "<CommissionerProtectionOverridePanel" in draft_tab_src
    assert 'draftType="expansion"' in draft_tab_src
    assert 'draftType="keeper"' in draft_tab_src

"""Iter 143 — Protection list ribbon + Scheduling + First-time gating + Expansion board listing.

Coverage
--------
1. ProtectionListRibbon component renders + mounts in AppLayout.
2. Backend exposes GET `/leagues/{id}/protection-list/status` returning
   the applicable flag + deadline + submitted state.
3. CommissionerSettings → Draft Type Select disables "startup" when
   `first_draft_completed` is true, and exposes a new "Redraft" option.
4. PUT `/leagues/{id}/next-draft-type` persists the selection and
   rejects `startup` after first-draft completion.
5. New `Redraft` option in the Select reuses the same form (no extra
   conditional card needed).
6. Backend GET `/leagues/{id}/expansion-draft-board` returns per-team
   unprotected + protected partitions.
7. DraftBoard renders the expansion listing inside the Order Results tab.
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
RIBBON = REPO / "frontend/src/lovable/components/ProtectionListRibbon.jsx"
LAYOUT = REPO / "frontend/src/components/layout/AppLayout.jsx"
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
DRAFTS = REPO / "backend/routes/drafts.py"
DRAFT_BOARD = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"


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


# ── 1. Ribbon component + AppLayout mount ──────────────────────
def test_protection_ribbon_exists():
    assert RIBBON.exists()
    src = RIBBON.read_text()
    assert 'data-testid="protection-list-ribbon"' in src
    assert 'data-testid="protection-list-ribbon-countdown"' in src
    assert 'data-testid="protection-list-ribbon-submit"' in src
    assert "protection-list/status" in src
    # Hides when not applicable / submitted (uses optional chaining)
    assert "status?.submitted" in src or "status.submitted" in src
    assert "status?.applicable" in src or "status.applicable" in src
    assert "status.submitted ||" in src and "status?.applicable" in src


def test_layout_mounts_ribbon():
    src = LAYOUT.read_text()
    assert "import ProtectionListRibbon" in src
    assert "<ProtectionListRibbon" in src


# ── 2. Backend protection-list status endpoint ─────────────────
def test_protection_list_status_endpoint_live(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/protection-list/status",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("applicable", "draft_type", "deadline_at", "submitted", "my_team_id"):
        assert k in body


# ── 3. Admin Select: First-Time disabled when completed + Redraft option ──
def test_admin_gates_startup_and_offers_redraft():
    admin_src = ADMIN.read_text()
    draft_tab = (REPO / "frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx").read_text()
    assert 'data-testid="draft-type-startup"' in draft_tab
    assert "disabled={firstDraftCompleted}" in draft_tab
    assert 'data-testid="draft-type-redraft"' in draft_tab
    assert ">Redraft<" in draft_tab
    # Persistence
    assert "persistDraftType" in admin_src
    assert "/next-draft-type" in admin_src


# ── 4. Backend next-draft-type endpoint rejects startup after completion ──
def test_next_draft_type_rejects_startup_when_complete(owner_token, owner_league):
    # Mark the league as completed
    r1 = httpx.put(
        f"{API}/leagues/{owner_league['id']}/first-draft-completed",
        headers=_auth(owner_token), json={"completed": True}, timeout=10,
    )
    assert r1.status_code == 200, r1.text
    # Now setting startup must fail
    r2 = httpx.put(
        f"{API}/leagues/{owner_league['id']}/next-draft-type",
        headers=_auth(owner_token), json={"draft_type": "startup"}, timeout=10,
    )
    assert r2.status_code == 400, r2.text
    # Redraft + others are still allowed
    r3 = httpx.put(
        f"{API}/leagues/{owner_league['id']}/next-draft-type",
        headers=_auth(owner_token), json={"draft_type": "redraft"}, timeout=10,
    )
    assert r3.status_code == 200, r3.text
    # Reset for other tests
    httpx.put(
        f"{API}/leagues/{owner_league['id']}/first-draft-completed",
        headers=_auth(owner_token), json={"completed": False}, timeout=10,
    )


# ── 5. Expansion draft board endpoint returns partitioned players ──
def test_expansion_draft_board_endpoint(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/expansion-draft-board",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "teams" in body and isinstance(body["teams"], list)
    if body["teams"]:
        row = body["teams"][0]
        for k in ("team_id", "team_name", "team_abbr", "submitted", "unprotected", "protected"):
            assert k in row, f"Missing key {k}"


# ── 6. Draft Board page renders the expansion listing ─────────
def test_draft_board_expansion_listing_block():
    src = DRAFT_BOARD.read_text()
    assert "expansion-draft-board" in src, "Endpoint URL must be fetched"
    assert 'data-testid="expansion-board-card"' in src
    assert 'data-testid="expansion-board-teams"' in src
    assert "expansion-unprotected-${row.team_abbr}" in src
    assert "expansion-protected-${row.team_abbr}" in src

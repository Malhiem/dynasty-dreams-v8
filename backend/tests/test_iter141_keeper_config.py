"""Iter 141 — Keeper Draft configuration.

Coverage
--------
Frontend:
  1. KeeperSettingsCard component exists with all required fields,
     conditional offset block, rookie + waiver blocks, and InfoHint
     copy with the user-spec wording.
  2. CommissionerSettings → Draft tab adds the "Keeper Draft" option
     and renders KeeperSettingsCard ONLY when that option is picked.

Backend:
  3. New GET + PUT `/api/leagues/{id}/keeper-config` endpoints.
  4. PUT validates `cost_method` enum and rejects unknown values.
  5. Commissioner can persist + read back the config.
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
KEEPER_CARD = REPO / "frontend/src/lovable/pages/commissioner/KeeperSettingsCard.tsx"
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
DRAFTS_ROUTE = REPO / "backend/routes/drafts.py"


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


# ── 1. Card has all the fields + info copy ─────────────────────
def test_keeper_card_fields_and_info():
    assert KEEPER_CARD.exists(), "KeeperSettingsCard.tsx must exist"
    src = KEEPER_CARD.read_text()
    for tid in (
        "keeper-settings-card",
        "keeper-num-input",
        "keeper-max-seasons-input",
        "keeper-deadline-input",
        "keeper-cost-method-trigger",
        "keeper-cost-method-previous_round_drafted",
        "keeper-cost-method-fixed_round_penalty",
        "keeper-cost-method-salary_cap",
        "keeper-cost-method-none",
        "keeper-offset-input",
        "keeper-rookie-switch",
        "keeper-rookie-round-input",
        "keeper-waiver-switch",
        "keeper-waiver-round-input",
        "keeper-save",
    ):
        assert f'data-testid="{tid}"' in src, f"Missing testid: {tid}"
    # Required InfoHint copy fragments (user-specified)
    assert "Rounds earlier than original pick" in src
    assert "discourages keeping anyone but elite talent" in src
    assert "Allows first-year players to be kept at a fixed late round" in src
    assert "added off the waiver wire mid-season" in src
    # Endpoints used
    assert "/leagues/${leagueId}/keeper-config" in src


# ── 2. League Admin gates the card on draft_type === "keeper" ──
def test_admin_keeper_card_gated_on_draft_type():
    admin_src = ADMIN.read_text()
    draft_tab_src = (REPO / "frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx").read_text()
    # Parent still mounts DraftTab and Keeper option lives in the extracted file
    assert 'import KeeperSettingsCard from "@/lovable/pages/commissioner/KeeperSettingsCard"' in draft_tab_src
    # Keeper Draft option in the Select
    assert 'data-testid="draft-type-keeper"' in draft_tab_src, "Keeper Draft option missing in Draft Type Select"
    assert ">Keeper Draft<" in draft_tab_src, "Keeper Draft label missing"
    # Card mounted under conditional
    assert 'draftType === "keeper"' in draft_tab_src, "Render gate missing on draftType"
    assert "<KeeperSettingsCard" in draft_tab_src, "Card must render inside the gate"
    # Draft Type is now controlled (no defaultValue, uses value/onValueChange)
    assert "value={draftType}" in draft_tab_src
    # setDraftType OR persistDraftType (Iter 143 wraps the setter for persistence)
    assert ("setDraftType" in admin_src) or ("persistDraftType" in admin_src)


# ── 3. Backend exposes GET + PUT keeper-config ─────────────────
def test_backend_routes_defined():
    src = DRAFTS_ROUTE.read_text()
    assert '"/leagues/{league_id}/keeper-config"' in src
    assert "async def get_keeper_config" in src
    assert "async def update_keeper_config" in src
    assert "KEEPER_COST_METHODS" in src


# ── 4. Invalid cost_method rejected ────────────────────────────
def test_put_rejects_bad_cost_method(owner_token, owner_league):
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/keeper-config",
        headers=_auth(owner_token),
        json={"config": {"cost_method": "bogus"}},
        timeout=10,
    )
    assert r.status_code == 400, r.text


# ── 5. Round-trip save + read ──────────────────────────────────
def test_keeper_config_round_trip(owner_token, owner_league):
    payload = {
        "config": {
            "enabled": True,
            "num_keepers": 5,
            "max_seasons": 3,
            "declaration_deadline_days": 21,
            "cost_method": "previous_round_drafted",
            "round_offset": 1,
            "allow_rookie_exception": True,
            "rookie_late_round": 10,
            "waiver_pickups_keepable": True,
            "waiver_default_round": 12,
        }
    }
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/keeper-config",
        headers=_auth(owner_token), json=payload, timeout=10,
    )
    assert r.status_code == 200, r.text
    r2 = httpx.get(
        f"{API}/leagues/{owner_league['id']}/keeper-config",
        headers=_auth(owner_token), timeout=10,
    )
    assert r2.status_code == 200
    cfg = r2.json().get("config") or {}
    assert cfg.get("num_keepers") == 5
    assert cfg.get("cost_method") == "previous_round_drafted"
    assert cfg.get("waiver_pickups_keepable") is True

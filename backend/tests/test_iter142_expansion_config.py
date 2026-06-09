"""Iter 142 — Expansion Draft configuration.

Coverage
--------
Frontend:
  1. ExpansionDraftSettingsCard exists with all the required fields,
     conditional sub-blocks, and the "Add" button + per-row controls
     for additional expansion picks.
  2. CommissionerSettings renders the card ONLY when draftType ==
     "expansion".

Backend:
  3. GET + PUT `/api/leagues/{id}/expansion-config` endpoints exist.
  4. Enum validation rejects bad values across all sub-sections.
  5. Round-trip save + read persists every group + the picks array.
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
CARD = REPO / "frontend/src/lovable/pages/commissioner/ExpansionDraftSettingsCard.tsx"
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
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


def test_card_has_all_fields():
    assert CARD.exists()
    src = CARD.read_text()
    for tid in (
        "expansion-settings-card",
        "expansion-num-keepers-input",
        "expansion-num-teams-input",
        "expansion-protect-max-input",
        "expansion-visibility-trigger",
        "expansion-visibility-public",
        "expansion-visibility-secret",
        "expansion-max-taken-input",
        "expansion-comp-switch",
        "expansion-comp-after-input",
        "expansion-comp-applies-trigger",
        "expansion-comp-threshold-type-trigger",
        "expansion-comp-threshold-value-input",
        "expansion-order-method-trigger",
        "expansion-order-style-trigger",
        "expansion-picks-add",
        "expansion-cap-floor-input",
        "expansion-cap-credit-switch",
        "expansion-save",
    ):
        assert f'data-testid="{tid}"' in src, f"Missing testid: {tid}"
    # Conditional reveal_days input shows only when public
    assert 'list_visibility === "public"' in src
    # Per-pick row testids use template literals
    assert "expansion-pick-row-${idx}" in src
    assert "expansion-pick-placement-${idx}" in src
    assert "expansion-pick-lottery-${idx}" in src
    # Endpoint
    assert "/leagues/${leagueId}/expansion-config" in src


def test_admin_gates_expansion_card():
    src = ADMIN.read_text()
    assert 'import ExpansionDraftSettingsCard from "@/lovable/pages/commissioner/ExpansionDraftSettingsCard"' in src
    draft_tab_idx = src.find('TabsContent value="draft"')
    block = src[draft_tab_idx:draft_tab_idx + 5000]
    assert 'draftType === "expansion"' in block, "Render gate missing"
    assert "<ExpansionDraftSettingsCard" in block, "Card not mounted"


def test_backend_routes_exist():
    src = DRAFTS.read_text()
    assert '"/leagues/{league_id}/expansion-config"' in src
    assert "async def get_expansion_config" in src
    assert "async def update_expansion_config" in src
    # Enum constants
    for name in ("EXPANSION_LIST_VISIBILITY", "EXPANSION_COMP_APPLIES",
                 "EXPANSION_THRESHOLD_TYPES", "EXPANSION_PICK_ORDER_METHODS",
                 "EXPANSION_PICK_ORDER_STYLES", "EXPANSION_PICK_PLACEMENTS"):
        assert name in src, f"Constant {name} missing"


@pytest.mark.parametrize("bad_field, bad_value", [
    ("protection", {"list_visibility": "bogus"}),
    ("compensation_pick", {"applies_to": "weird"}),
    ("compensation_pick", {"threshold_type": "junk"}),
    ("pick_order", {"method": "lol"}),
    ("pick_order", {"style": "diagonal"}),
])
def test_put_rejects_bad_enums(owner_token, owner_league, bad_field, bad_value):
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/expansion-config",
        headers=_auth(owner_token),
        json={"config": {bad_field: bad_value}},
        timeout=10,
    )
    assert r.status_code == 400, r.text


def test_round_trip(owner_token, owner_league):
    body = {"config": {
        "enabled": True,
        "num_keepers": 4,
        "num_expansion_teams": 2,
        "protection": {
            "max_protected": 9,
            "list_visibility": "public",
            "reveal_days_before": 5,
            "max_taken_per_roster": 1,
        },
        "compensation_pick": {
            "enabled": True,
            "after_round": 2,
            "applies_to": "threshold",
            "threshold_type": "aav",
            "threshold_value": 4_500_000,
        },
        "pick_order": {"method": "automatic", "style": "snake"},
        "expansion_picks": [
            {"round": 1, "placement": "top"},
            {"round": 2, "placement": "lottery_odds", "lottery_odds": [25, 18, 12]},
        ],
        "roster_minimums": {
            "salary_cap_floor": 62_500_000,
            "cap_credit_enabled": True,
            "cap_credit_per_player": 1_000_000,
        },
    }}
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/expansion-config",
        headers=_auth(owner_token), json=body, timeout=10,
    )
    assert r.status_code == 200, r.text
    r2 = httpx.get(
        f"{API}/leagues/{owner_league['id']}/expansion-config",
        headers=_auth(owner_token), timeout=10,
    )
    assert r2.status_code == 200
    cfg = r2.json().get("config") or {}
    assert cfg["num_expansion_teams"] == 2
    assert cfg["protection"]["list_visibility"] == "public"
    assert cfg["compensation_pick"]["applies_to"] == "threshold"
    assert cfg["pick_order"]["style"] == "snake"
    assert len(cfg["expansion_picks"]) == 2
    assert cfg["expansion_picks"][1]["placement"] == "lottery_odds"
    assert cfg["expansion_picks"][1]["lottery_odds"] == [25, 18, 12]
    assert cfg["roster_minimums"]["cap_credit_enabled"] is True

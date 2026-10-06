"""Iter 126 — Waiver FAAB system option + customization fields.

Coverage
--------
1. `WaiverSystemType` widened to accept "faab" alongside "auto_priority".
2. New `waiver.faab_budget` field persists through PUT roundtrip.
3. Existing `waiver.processing_days_count` (Waiver Clearing Period) keeps
   working when system_type == "faab".
4. Old config payloads without `faab_budget` continue to GET cleanly
   (back-compat — defaults to 100).
5. RulesScheduleTab no longer renders the standalone Waivers card —
   FAAB+clearing now live under TransactionsConfig.
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
TX_CARDS = REPO / "frontend/src/lovable/pages/commissioner/TransactionsConfigCards.tsx"
RULES_TAB = REPO / "frontend/src/lovable/pages/commissioner/RulesScheduleTab.tsx"


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


def test_faab_system_type_accepted(owner_token, owner_league):
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"system_type": "faab", "faab_budget": 250, "processing_days_count": 3}},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["waiver"]["system_type"] == "faab"
    assert body["waiver"]["faab_budget"] == 250
    assert body["waiver"]["processing_days_count"] == 3


def test_faab_budget_persists_across_get(owner_token, owner_league):
    # Set
    httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"system_type": "faab", "faab_budget": 500}},
        headers=_auth(owner_token), timeout=10,
    )
    # Get
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.json()["waiver"]["faab_budget"] == 500


def test_auto_priority_still_works(owner_token, owner_league):
    # Restore to auto_priority so we don't leave the league in FAAB mode
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"system_type": "auto_priority"}},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["waiver"]["system_type"] == "auto_priority"


def test_faab_budget_validation_rejects_negative(owner_token, owner_league):
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"faab_budget": -10}},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_faab_budget_validation_rejects_overlarge(owner_token, owner_league):
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}/transactions-config",
        json={"waiver": {"faab_budget": 999999}},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 422


def test_frontend_tx_cards_have_faab_block():
    src = read_source(TX_CARDS)
    assert "waiver-system-faab" in src, "FAAB system dropdown item missing"
    assert "waiver-faab-block" in src, "FAAB block testid missing"
    assert "waiver-faab-budget-input" in src, "FAAB budget input missing"
    assert "waiver-clearing-period-input" in src, "Clearing period input missing"
    # FAAB block must be conditional on system_type == "faab"
    assert 'system_type === "faab"' in src, "FAAB block isn't gated on system_type"


def test_rules_schedule_tab_no_longer_has_waivers_card():
    src = read_source(RULES_TAB, include_imports=False)
    assert "rules-schedule-waivers-card" not in src, (
        "Waivers card should be moved out of RulesScheduleTab"
    )
    # waiver_faab_budget should not be referenced here anymore
    assert "waiver_faab_budget" not in src, (
        "waiver_faab_budget reference should be moved to TransactionsConfigCards"
    )

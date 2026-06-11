"""Iter 121 — Five tasks rolled into one iter.

This iter is mostly UI reorganization + new render surfaces. Backend
changes are limited to:
  • Roster Shape card removed from RulesScheduleTab (no API change)
  • Salary Cap, Salary Retention, Contract Buyouts cards moved into a
    new "Salary Cap & Contracts" tab (no API change — same endpoints)
  • Prospect Eligibility added to Rosters tab (reads/writes existing
    `prospect_max_age` and `prospect_max_career_games` league fields)
  • Cap Floor surfaced on Salary Cap page (no API change — reads
    `cap_floor*` from /api/leagues/{id} which iter 120 already exposes)
  • Priority Order card on Waivers page (reads /api/leagues/{id}/
    transactions-config which iter 117/120 already exposes)

So this iter's pytest coverage is wiring/file-presence assertions plus
a regression that the moved cards still work via the existing
`/api/leagues/{id}/admin/cap-settings` endpoint.
"""
import os

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def _login(email, password):
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    return r.json().get("access_token") if r.status_code == 200 else None


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(ADMIN_EMAIL, ADMIN_PW)
    if not tok:
        pytest.skip("admin login unavailable")
    return tok


@pytest.fixture(scope="module")
def league_id(admin_token):
    r = httpx.get(f"{API}/leagues?my_leagues=true", headers=_auth(admin_token), timeout=10)
    if r.status_code != 200 or not (r.json() or []):
        pytest.skip("admin has no leagues")
    return r.json()[0]["id"]


# ────────────────── Frontend wiring assertions ─────────────────


def test_roster_shape_removed_from_transactions_tab():
    """RulesScheduleTab.tsx no longer registers a Roster Shape section."""
    src = open("/app/frontend/src/lovable/pages/commissioner/RulesScheduleTab.tsx").read()
    assert 'title: "Roster Shape"' not in src, "Roster Shape section is still present"
    assert "rules-schedule-roster-card" not in src


def test_salary_cap_contracts_tab_exists():
    src = open("/app/frontend/src/lovable/pages/CommissionerSettings.tsx").read()
    assert 'tab-salary-cap-contracts' in src
    assert 'salary-cap-contracts-tab' in src
    # Iter 158 — three cards now live inside SalaryCapContractsTab.tsx
    tab_src = open("/app/frontend/src/lovable/pages/commissioner/tabs/SalaryCapContractsTab.tsx").read()
    assert "SalaryCapCard" in tab_src
    assert "SalaryRetentionCard" in tab_src
    assert "ContractBuyoutsCard" in tab_src


def test_prospect_eligibility_card_present_on_rosters_tab():
    src = open("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx").read()
    assert "rosters-prospect-eligibility-card" in src
    assert "rosters-prospect-max-age" in src
    assert "rosters-prospect-max-games" in src
    assert "prospect_max_age" in src
    assert "prospect_max_career_games" in src


def test_cap_floor_surfaced_on_salary_cap_page():
    src = open("/app/frontend/src/lovable/pages/SalaryCap.tsx").read()
    assert "cap-floor-compliance-card" in src
    assert "cap_floor_enabled" in src
    assert "cap_floor_year_plus_1" in src
    # By-Year chart uses ComposedChart with a step floor Line
    assert "ComposedChart" in src
    assert "Cap Floor" in src


def test_waiver_priority_order_surface_on_waivers_page():
    src = open("/app/frontend/src/lovable/pages/Waivers.tsx").read()
    assert "WaiverPriorityOrderCard" in src
    comp = open("/app/frontend/src/lovable/components/dashboard/WaiverPriorityOrderCard.tsx").read()
    assert "reverse_standings_serpentine" in comp
    assert "transactions-config" in comp
    assert "waiver-priority-order-card" in comp


# ────────────────── Backend regression ─────────────────────────


def test_cap_settings_endpoint_still_round_trips_floor(admin_token, league_id):
    """The moved cards still hit the same endpoint they always did —
    PUT /api/leagues/{id}/admin/cap-settings."""
    r = httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": True,
            "salary_cap": 88000000,
            "cap_floor_enabled": True,
            "cap_floor": 60000000,
            "cap_floor_year_plus_1": 62000000,
            "cap_floor_year_plus_2": 64000000,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cap_floor"] == 60000000
    assert body["cap_floor_year_plus_1"] == 62000000

    # Reset
    httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={"salary_cap_enabled": False},
        timeout=10,
    )

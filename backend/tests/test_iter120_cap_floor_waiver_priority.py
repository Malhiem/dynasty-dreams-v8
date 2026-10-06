"""Iter 120 — Cap Floor + Waiver Wire System (priority order).

Coverage
--------
1. PUT /api/leagues/{id}/admin/cap-settings:
   * Round-trip: cap_floor_enabled + cap_floor + Year+1/+2 floor values
   * Disabling the ceiling clears the floor too (defensive, mirrors iter 117)
   * Disabling cap_floor_enabled clears all 3 floor amounts + tentative flags

2. transactions_config waiver schema:
   * Round-trip: system_type=auto_priority, each priority_order option
   * Manual priority team_id validation rejects unknown ids
   * Defaults: system_type="auto_priority", priority_order="reverse_standings_serpentine"
"""
import os
import secrets

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"))
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))


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
    lid = r.json()[0]["id"]
    # Snapshot current cap settings so teardown can restore
    snap = httpx.get(f"{API}/leagues/{lid}", headers=_auth(admin_token), timeout=10).json() or {}
    yield lid
    # Restore: enable cap with original values (or disable if it was off)
    httpx.put(
        f"{API}/leagues/{lid}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": bool(snap.get("salary_cap_enabled")),
            "salary_cap": snap.get("salary_cap"),
            "salary_cap_year_plus_1": snap.get("salary_cap_year_plus_1"),
            "salary_cap_year_plus_2": snap.get("salary_cap_year_plus_2"),
            "cap_floor_enabled": bool(snap.get("cap_floor_enabled")),
            "cap_floor": snap.get("cap_floor"),
            "cap_floor_year_plus_1": snap.get("cap_floor_year_plus_1"),
            "cap_floor_year_plus_2": snap.get("cap_floor_year_plus_2"),
        },
        timeout=10,
    )
    httpx.put(f"{API}/leagues/{lid}/transactions-config",
              headers=_auth(admin_token), json={}, timeout=10)


# ────────────────── (1) Cap Floor round-trip ──────────────────


def test_cap_floor_round_trip_with_ceiling_enabled(admin_token, league_id):
    r = httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": True,
            "salary_cap": 88000000,
            "salary_cap_year_plus_1": 90000000,
            "salary_cap_year_plus_2": 92000000,
            "cap_floor_enabled": True,
            "cap_floor": 65000000,
            "cap_floor_year_plus_1": 66000000,
            "cap_floor_year_plus_2": 68000000,
            "cap_floor_year_plus_1_tentative": True,
            "cap_floor_year_plus_2_tentative": False,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cap_floor_enabled"] is True
    assert body["cap_floor"] == 65000000
    assert body["cap_floor_year_plus_1"] == 66000000
    assert body["cap_floor_year_plus_2"] == 68000000
    assert body["cap_floor_year_plus_1_tentative"] is True
    assert body["cap_floor_year_plus_2_tentative"] is False


def test_disabling_cap_floor_clears_future_values(admin_token, league_id):
    # First, set the floor with values
    httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": True,
            "salary_cap": 88000000,
            "cap_floor_enabled": True,
            "cap_floor": 65000000,
            "cap_floor_year_plus_1": 66000000,
            "cap_floor_year_plus_2": 68000000,
        },
        timeout=10,
    )
    # Now disable floor — all values + tentative flags must clear
    r = httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={"cap_floor_enabled": False},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cap_floor_enabled"] is False
    assert body["cap_floor"] is None
    assert body["cap_floor_year_plus_1"] is None
    assert body["cap_floor_year_plus_2"] is None
    assert body["cap_floor_year_plus_1_tentative"] is False
    assert body["cap_floor_year_plus_2_tentative"] is False


def test_disabling_ceiling_also_clears_floor(admin_token, league_id):
    # Set both ceiling and floor
    httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": True,
            "salary_cap": 88000000,
            "cap_floor_enabled": True,
            "cap_floor": 65000000,
        },
        timeout=10,
    )
    # Disable ceiling — floor must follow
    r = httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={"salary_cap_enabled": False},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["salary_cap_enabled"] is False
    assert body["cap_floor_enabled"] is False
    assert body["cap_floor"] is None


# ────────────────── (2) Waiver Wire System & priority ────────


def test_waiver_system_defaults(admin_token, league_id):
    # Reset then read
    httpx.put(f"{API}/leagues/{league_id}/transactions-config",
              headers=_auth(admin_token), json={}, timeout=10)
    r = httpx.get(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    w = r.json()["waiver"]
    assert w["system_type"] == "auto_priority"
    assert w["priority_order"] == "reverse_standings_serpentine"
    assert w["manual_priority_order"] == []


@pytest.mark.parametrize("priority", [
    "reverse_standings_serpentine",
    "reverse_standings",
    "random",
])
def test_waiver_priority_order_round_trip(admin_token, league_id, priority):
    payload = {"waiver": {
        "enabled": True,
        "system_type": "auto_priority",
        "priority_order": priority,
        "manual_priority_order": [],
        "processing_mode": "days", "processing_days_count": 2,
        "processing_schedule": [], "abuse_window_enabled": False,
        "abuse_window_days": 3,
        "claim_limits": {"total": None, "fa": None, "waivers": None},
        "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
        "pending_visibility": "own", "failed_visibility": "own",
        "force_drop_on_claim": False, "force_claim_on_drop": False,
    }}
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["waiver"]["priority_order"] == priority


def test_waiver_manual_priority_validates_team_ids(admin_token, league_id):
    payload = {"waiver": {
        "enabled": True,
        "system_type": "auto_priority",
        "priority_order": "manual",
        "manual_priority_order": ["000000000000000000000000"],  # bogus id
        "processing_mode": "days", "processing_days_count": 2,
        "processing_schedule": [], "abuse_window_enabled": False,
        "abuse_window_days": 3,
        "claim_limits": {"total": None, "fa": None, "waivers": None},
        "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
        "pending_visibility": "own", "failed_visibility": "own",
        "force_drop_on_claim": False, "force_claim_on_drop": False,
    }}
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 400, r.text
    assert "not in this league" in (r.json().get("detail") or "")


def test_waiver_manual_priority_accepts_valid_team_ids(admin_token, league_id):
    teams = httpx.get(f"{API}/teams?league_id={league_id}",
                     headers=_auth(admin_token), timeout=10).json() or []
    if len(teams) < 2:
        pytest.skip("need ≥2 teams")
    ids = [t["id"] for t in teams[:3]]
    payload = {"waiver": {
        "enabled": True,
        "system_type": "auto_priority",
        "priority_order": "manual",
        "manual_priority_order": ids,
        "processing_mode": "days", "processing_days_count": 2,
        "processing_schedule": [], "abuse_window_enabled": False,
        "abuse_window_days": 3,
        "claim_limits": {"total": None, "fa": None, "waivers": None},
        "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
        "pending_visibility": "own", "failed_visibility": "own",
        "force_drop_on_claim": False, "force_claim_on_drop": False,
    }}
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["waiver"]["manual_priority_order"] == ids

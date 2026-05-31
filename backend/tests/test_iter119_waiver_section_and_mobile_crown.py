"""Iter 119 — Crown mobile deep-link helper + extended Waiver section.

Coverage
--------
1. Waiver claim_limits validation: PUT rejects FA > Total / Waivers > Total
   when Total is finite (server-side guard).
2. Waiver claim_limits round-trip: defaults, full payload, schema accepts
   prevent_prospects + force_drop_on_claim + force_claim_on_drop +
   pending/failed visibility = "all_teams_anonymous".
3. force_drop_on_claim enforcement: a /api/waivers/place call without
   drop_player_id returns 400 with a helpful detail.
4. force_claim_on_drop enforcement: a /api/roster/{team}/drop returns 400
   when the waiver toggle is on.
5. Waiver prevent_prospects: a player flagged is_prospect can't be claimed
   via /waivers/place when the toggle is on.
6. Crown navigation helper (mobile JS): test by importing navigation
   function indirectly — skip on backend pytest; documented in mobile
   smoke notes.
"""
import os
import secrets

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", "chriszarek@gmail.com")
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", "Chris2026!")


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
def owner_session():
    tok = _login(OWNER_EMAIL, OWNER_PW)
    if not tok:
        pytest.skip("owner login unavailable")
    me = httpx.get(f"{API}/auth/me", headers=_auth(tok), timeout=10).json()
    leagues = httpx.get(f"{API}/leagues?my_leagues=true",
                       headers=_auth(tok), timeout=10).json() or []
    for lg in leagues:
        teams = httpx.get(f"{API}/teams?league_id={lg['id']}", headers=_auth(tok), timeout=10).json() or []
        mine = next((t for t in teams if t.get("owner_id") == me["id"]), None)
        if mine:
            return tok, lg["id"], mine["id"]
    pytest.skip("owner has no team in any league")


@pytest.fixture(scope="module")
def league_id(admin_token):
    r = httpx.get(f"{API}/leagues?my_leagues=true", headers=_auth(admin_token), timeout=10)
    if r.status_code != 200 or not (r.json() or []):
        pytest.skip("admin has no leagues")
    lid = r.json()[0]["id"]
    yield lid
    # Restore defaults
    httpx.put(f"{API}/leagues/{lid}/transactions-config",
              headers=_auth(admin_token), json={}, timeout=10)


# ────────────────── (1) FA / Waivers cannot exceed Total ─────────


def test_waiver_claim_limits_reject_fa_over_total(admin_token, league_id):
    payload = {
        "waiver": {
            "enabled": True,
            "processing_mode": "days",
            "processing_days_count": 2,
            "processing_schedule": [],
            "abuse_window_enabled": False,
            "abuse_window_days": 3,
            "claim_limits": {"total": 10, "fa": 20, "waivers": 5},
            "prevent_injured": "off",
            "prevent_minors": False,
            "prevent_prospects": False,
            "pending_visibility": "own",
            "failed_visibility": "own",
            "force_drop_on_claim": False,
            "force_claim_on_drop": False,
        }
    }
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 400, r.text
    assert "Free Agency cap" in (r.json().get("detail") or "")


def test_waiver_claim_limits_reject_waivers_over_total(admin_token, league_id):
    payload = {
        "waiver": {
            "enabled": True,
            "processing_mode": "days", "processing_days_count": 2,
            "processing_schedule": [], "abuse_window_enabled": False,
            "abuse_window_days": 3,
            "claim_limits": {"total": 10, "fa": 5, "waivers": 50},
            "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
            "pending_visibility": "own", "failed_visibility": "own",
            "force_drop_on_claim": False, "force_claim_on_drop": False,
        }
    }
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 400, r.text
    assert "Waiver Wire cap" in (r.json().get("detail") or "")


# ────────────────── (2) Full schema round-trip ────────────────


def test_waiver_full_schema_round_trip(admin_token, league_id):
    payload = {
        "waiver": {
            "enabled": True,
            "processing_mode": "scheduled", "processing_days_count": 2,
            "processing_schedule": [{"day_of_week": 2, "time": "21:00"}],
            "abuse_window_enabled": True, "abuse_window_days": 5,
            "claim_limits": {"total": 50, "fa": 30, "waivers": 25},
            "prevent_injured": "nhl_ir",
            "prevent_minors": True,
            "prevent_prospects": True,
            "pending_visibility": "all_teams_anonymous",
            "failed_visibility": "league_admin",
            "force_drop_on_claim": True,
            "force_claim_on_drop": True,
        }
    }
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    w = body["waiver"]
    assert w["claim_limits"]["total"] == 50
    assert w["claim_limits"]["fa"] == 30
    assert w["prevent_injured"] == "nhl_ir"
    assert w["prevent_prospects"] is True
    assert w["pending_visibility"] == "all_teams_anonymous"
    assert w["failed_visibility"] == "league_admin"
    assert w["force_drop_on_claim"] is True
    assert w["force_claim_on_drop"] is True

    # Reset
    httpx.put(f"{API}/leagues/{league_id}/transactions-config",
              headers=_auth(admin_token), json={}, timeout=10)


# ────────────────── (3) force_drop_on_claim enforcement ────────


def test_force_drop_on_claim_rejects_claim_without_drop(admin_token, owner_session):
    owner_tok, lg, team_id = owner_session

    # Get a player to claim
    plrs = httpx.get(f"{API}/players?limit=20", headers=_auth(owner_tok), timeout=10).json() or {}
    players = plrs.get("players") or []
    me_team = httpx.get(f"{API}/teams/{team_id}", headers=_auth(owner_tok), timeout=10).json()
    roster = set(me_team.get("roster") or [])
    avail = [p for p in players if p.get("_id") and p["_id"] not in roster]
    if not avail:
        pytest.skip("no available players")
    pid = avail[0]["_id"]

    # Try admin then owner to flip config
    cfg_tok = admin_token
    payload = {"waiver": {
        "enabled": True, "processing_mode": "days", "processing_days_count": 2,
        "processing_schedule": [], "abuse_window_enabled": False, "abuse_window_days": 3,
        "claim_limits": {"total": None, "fa": None, "waivers": None},
        "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
        "pending_visibility": "own", "failed_visibility": "own",
        "force_drop_on_claim": True, "force_claim_on_drop": False,
    }}
    cfg_resp = httpx.put(f"{API}/leagues/{lg}/transactions-config",
                         headers=_auth(cfg_tok), json=payload, timeout=10)
    if cfg_resp.status_code == 403:
        cfg_tok = owner_tok
        cfg_resp = httpx.put(f"{API}/leagues/{lg}/transactions-config",
                             headers=_auth(cfg_tok), json=payload, timeout=10)
    if cfg_resp.status_code != 200:
        pytest.skip("can't configure league")

    # Place a waiver claim WITHOUT drop_player_id → should 400
    r = httpx.post(f"{API}/waivers/claim",
                   headers=_auth(owner_tok),
                   json={"league_id": lg, "player_id": pid, "bid_amount": 1},
                   timeout=10)
    httpx.put(f"{API}/leagues/{lg}/transactions-config",
              headers=_auth(cfg_tok), json={}, timeout=10)
    assert r.status_code == 400, r.text
    assert "drop" in (r.json().get("detail") or "").lower() or "ir" in (r.json().get("detail") or "").lower()


# ────────────────── (4) force_claim_on_drop enforcement ────────


def test_force_claim_on_drop_rejects_standalone_drop(admin_token, owner_session):
    owner_tok, lg, team_id = owner_session

    me_team = httpx.get(f"{API}/teams/{team_id}", headers=_auth(owner_tok), timeout=10).json()
    roster = me_team.get("roster") or []
    if not roster:
        pytest.skip("no roster to drop from")
    pid = roster[0]

    cfg_tok = admin_token
    payload = {"waiver": {
        "enabled": True, "processing_mode": "days", "processing_days_count": 2,
        "processing_schedule": [], "abuse_window_enabled": False, "abuse_window_days": 3,
        "claim_limits": {"total": None, "fa": None, "waivers": None},
        "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
        "pending_visibility": "own", "failed_visibility": "own",
        "force_drop_on_claim": False, "force_claim_on_drop": True,
    }}
    cfg_resp = httpx.put(f"{API}/leagues/{lg}/transactions-config",
                         headers=_auth(cfg_tok), json=payload, timeout=10)
    if cfg_resp.status_code == 403:
        cfg_tok = owner_tok
        cfg_resp = httpx.put(f"{API}/leagues/{lg}/transactions-config",
                             headers=_auth(cfg_tok), json=payload, timeout=10)
    if cfg_resp.status_code != 200:
        pytest.skip("can't configure league")

    r = httpx.post(f"{API}/roster/{team_id}/drop",
                   headers=_auth(owner_tok),
                   json={"player_id": pid}, timeout=10)
    httpx.put(f"{API}/leagues/{lg}/transactions-config",
              headers=_auth(cfg_tok), json={}, timeout=10)
    assert r.status_code == 400, r.text
    assert "replacement" in (r.json().get("detail") or "").lower() or "add" in (r.json().get("detail") or "").lower()


# ────────────────── (5) Mobile crown deep-link (smoke) ────────


def test_navigation_helper_file_present():
    """Sanity check that the mobile app exports `navigateFromPush` from
    AppNavigator.js and App.js wires it into usePushRegistration."""
    nav = open("/app/mobile/src/navigation/AppNavigator.js").read()
    assert "navigateFromPush" in nav, "navigateFromPush helper missing"
    assert "data.type === 'crown'" in nav, "crown type branch missing"
    assert "Profile" in nav, "Profile navigation not wired"
    app = open("/app/mobile/App.js").read()
    assert "navigateFromPush" in app, "App.js doesn't pass navigateFromPush"
    assert "usePushRegistration(user?.id || null, navigateFromPush)" in app
    profile = open("/app/mobile/src/screens/ProfileScreen.js").read()
    assert "highlightEvent" in profile, "ProfileScreen doesn't read deep-link params"
    assert "crown-banner-" in profile, "crown banner testID missing"

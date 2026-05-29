"""Iter 117 — Transactions configuration + Zarek's Frozen salary cap bug.

Coverage
--------
1. Bug fix: disabling salary cap also nulls Year+1/Year+2 fields so the
   orphaned-future-cap state can never recur.
2. GET /api/leagues/{id}/transactions-config returns the merged-with-defaults
   envelope.
3. PUT /api/leagues/{id}/transactions-config (commissioner-only):
   * non-commissioner → 403
   * malformed manual_priority_order team_id → 400
   * round-trip preserves all five sub-sections
4. GET /api/teams/{team_id}/claim-counts:
   * default visibility "user" → owner sees counts, non-owner sees visible:false
5. Roster /add enforcement:
   * setting season FA cap of 0 → next /add returns 400 with "Season FA cap reached"
6. Reset of test-league config back to defaults at module teardown so other
   tests aren't perturbed.
"""
import os
import secrets

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")
# `chriszarek` owns teams across the demo leagues — useful for the
# enforcement test which needs a real owner. They are NOT a commissioner of
# the admin's leagues, so admin credentials remain the source of truth for
# config CRUD.
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", "chriszarek@gmail.com")
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", "Chris2026!")


def _login(email, password):
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    return r.json().get("access_token") if r.status_code == 200 else None


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(ADMIN_EMAIL, ADMIN_PW)
    if not tok:
        pytest.skip("admin login unavailable")
    return tok


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def league_and_team(admin_token):
    """First league the admin commissions + any team in it (used for config
    CRUD; admin commissions but doesn't own teams)."""
    r = httpx.get(f"{API}/leagues?my_leagues=true", headers=_auth(admin_token), timeout=10)
    if r.status_code != 200 or not (r.json() or []):
        pytest.skip("admin has no leagues")
    league_id = r.json()[0]["id"]
    t = httpx.get(f"{API}/teams?league_id={league_id}", headers=_auth(admin_token), timeout=10)
    if t.status_code != 200 or not (t.json() or []):
        pytest.skip("league has no teams")
    team_id = t.json()[0]["id"]
    yield league_id, team_id
    # Reset config to defaults for clean state on subsequent runs
    httpx.put(f"{API}/leagues/{league_id}/transactions-config",
              headers=_auth(admin_token), json={}, timeout=10)


@pytest.fixture(scope="module")
def owner_session():
    """Logged-in regular user who actually owns teams. Used for the
    enforcement test that goes through `/api/roster/{team_id}/add`."""
    tok = _login(OWNER_EMAIL, OWNER_PW)
    if not tok:
        pytest.skip("owner login unavailable")
    me = httpx.get(f"{API}/auth/me", headers=_auth(tok), timeout=10).json()
    leagues = httpx.get(f"{API}/leagues?my_leagues=true",
                       headers=_auth(tok), timeout=10).json() or []
    if not leagues:
        pytest.skip("owner has no leagues")
    # Find a league where owner has a team AND admin is the commissioner so
    # we can set transactions-config via admin_token.
    for lg in leagues:
        teams = httpx.get(f"{API}/teams?league_id={lg['id']}", headers=_auth(tok), timeout=10).json() or []
        mine = next((t for t in teams if t.get("owner_id") == me["id"]), None)
        if mine:
            return tok, lg["id"], mine["id"]
    pytest.skip("owner has no team in any league")


@pytest.fixture(scope="module")
def non_admin_token():
    suffix = secrets.token_hex(4)
    email = f"iron117_{suffix}@example.com"
    pw = f"Iron-{suffix}!1"
    r = httpx.post(f"{API}/auth/register",
                   json={"email": email, "password": pw, "username": f"u117{suffix}"},
                   timeout=10)
    if r.status_code not in (200, 201):
        pytest.skip(f"register failed: {r.status_code}")
    tok = r.json().get("access_token") or _login(email, pw)
    if not tok:
        pytest.skip("login post-register failed")
    return tok


# ────────────────── (1) Salary cap bug fix ─────────────────────


def test_disabling_cap_nulls_future_year_caps(admin_token, league_and_team):
    league_id, _ = league_and_team
    # First, enable the cap with future-year values
    r = httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": True,
            "salary_cap": 85000000,
            "salary_cap_year_plus_1": 86000000,
            "salary_cap_year_plus_2": 88000000,
            "salary_cap_year_plus_1_tentative": True,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["salary_cap_enabled"] is True
    assert body["salary_cap_year_plus_1"] == 86000000
    assert body["salary_cap_year_plus_2"] == 88000000

    # Now disable the cap. The fix says: both future-year fields + their
    # tentative flags must clear so the league can't end up in the orphaned
    # "disabled but $88M Year+2 still set" state that produced the bug.
    r = httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={"salary_cap_enabled": False},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["salary_cap_enabled"] is False
    assert body["salary_cap"] is None
    assert body["salary_cap_year_plus_1"] is None
    assert body["salary_cap_year_plus_2"] is None
    assert body["salary_cap_year_plus_1_tentative"] is False
    assert body["salary_cap_year_plus_2_tentative"] is False


# ────────────────── (2) Transactions config envelope ───────────


def test_get_transactions_config_returns_defaults(admin_token, league_and_team):
    league_id, _ = league_and_team
    r = httpx.get(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("claim_limits", "claim_rules", "free_agency", "waiver", "draft_claims"):
        assert key in body
    assert body["claim_rules"]["prevent_injured"] == "off"
    assert body["free_agency"]["system_type"] == "open"
    assert body["waiver"]["enabled"] is False


def test_put_transactions_config_round_trip(admin_token, league_and_team):
    league_id, _ = league_and_team
    payload = {
        "claim_limits": {
            "season": {"total": 30, "fa": 20, "waivers": 10},
            "week": {"total": 5, "fa": 3, "waivers": 2},
        },
        "claim_rules": {
            "lock_at_first_game": True,
            "allow_non_playoff_teams_claims": False,
            "prevent_injured": "nhl_ir",
            "prevent_minors": True,
            "pending_visibility": "all_teams",
            "failed_visibility": "league_admin",
        },
        "free_agency": {
            "system_type": "auto_priority",
            "auto_priority_basis": "reverse_prev",
            "priority_recompute_cadence": "weekly",
            "manual_priority_duration": "season",
            "manual_priority_order": [],
            "manual_priority_schedule": [],
            "picks_per_round_policy": "all_then_next",
            "waivers_reset_after_claim": True,
        },
        "waiver": {
            "enabled": True,
            "processing_mode": "scheduled",
            "processing_days_count": 2,
            "processing_schedule": [{"day_of_week": 2, "time": "21:00"},
                                    {"day_of_week": 4, "time": "21:00"}],
            "abuse_window_enabled": True,
            "abuse_window_days": 5,
        },
        "draft_claims": {
            "allow_claims_before_draft": True,
            "allow_drops_during_draft": True,
        },
    }
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claim_limits"]["season"]["total"] == 30
    assert body["claim_rules"]["prevent_injured"] == "nhl_ir"
    assert body["free_agency"]["system_type"] == "auto_priority"
    assert body["waiver"]["processing_mode"] == "scheduled"
    assert len(body["waiver"]["processing_schedule"]) == 2
    assert body["draft_claims"]["allow_drops_during_draft"] is True

    # Reset for the next test
    httpx.put(f"{API}/leagues/{league_id}/transactions-config",
              headers=_auth(admin_token), json={}, timeout=10)


def test_put_rejects_non_commissioner(non_admin_token, league_and_team):
    league_id, _ = league_and_team
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(non_admin_token), json={}, timeout=10)
    assert r.status_code == 403, r.text


def test_put_rejects_manual_priority_bad_team_id(admin_token, league_and_team):
    league_id, _ = league_and_team
    payload = {
        "free_agency": {
            "system_type": "manual_priority",
            "manual_priority_order": ["000000000000000000000000"],
            "auto_priority_basis": "reverse_live",
            "priority_recompute_cadence": "live",
            "manual_priority_duration": "one_off",
            "manual_priority_schedule": [],
            "picks_per_round_policy": "top_then_next",
            "waivers_reset_after_claim": False,
        }
    }
    r = httpx.put(f"{API}/leagues/{league_id}/transactions-config",
                  headers=_auth(admin_token), json=payload, timeout=10)
    assert r.status_code == 400, r.text
    assert "team_ids" in (r.json().get("detail") or "").lower() or "not in this league" in (r.json().get("detail") or "").lower()


# ────────────────── (3) Claim counts visibility ───────────────


def test_claim_counts_visible_to_owner(owner_session):
    tok, _, team_id = owner_session
    r = httpx.get(f"{API}/teams/{team_id}/claim-counts",
                  headers=_auth(tok), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["visible"] is True
    assert "season" in body and "week" in body and "limits" in body


def test_claim_counts_hidden_for_non_member(non_admin_token, owner_session):
    _, _, team_id = owner_session
    r = httpx.get(f"{API}/teams/{team_id}/claim-counts",
                  headers=_auth(non_admin_token), timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["visible"] is False


# ────────────────── (4) Enforcement on roster /add ─────────────


def test_season_fa_cap_blocks_add(admin_token, owner_session):
    """Set FA season cap to 0 and try to add a player → 400."""
    owner_tok, league_id, team_id = owner_session

    # Find a player not currently on this team
    me_team = httpx.get(f"{API}/teams/{team_id}", headers=_auth(owner_tok), timeout=10).json()
    roster_ids = set(me_team.get("roster") or [])
    plr_resp = httpx.get(f"{API}/players?limit=20", headers=_auth(owner_tok), timeout=10)
    if plr_resp.status_code != 200:
        pytest.skip("players endpoint unavailable")
    players = (plr_resp.json() or {}).get("players") or []
    avail = [p for p in players if p.get("_id") and p["_id"] not in roster_ids]
    if not avail:
        pytest.skip("no available players for this test")
    pid = avail[0]["_id"]

    # Need commissioner to flip the league config — try admin (most leagues),
    # else owner if they happen to be commissioner.
    cfg_tok = admin_token
    cfg_resp = httpx.put(
        f"{API}/leagues/{league_id}/transactions-config",
        headers=_auth(cfg_tok),
        json={"claim_limits": {"season": {"total": None, "fa": 0, "waivers": None},
                               "week": {"total": None, "fa": None, "waivers": None}}},
        timeout=10,
    )
    if cfg_resp.status_code == 403:
        cfg_tok = owner_tok
        cfg_resp = httpx.put(
            f"{API}/leagues/{league_id}/transactions-config",
            headers=_auth(cfg_tok),
            json={"claim_limits": {"season": {"total": None, "fa": 0, "waivers": None},
                                   "week": {"total": None, "fa": None, "waivers": None}}},
            timeout=10,
        )
    if cfg_resp.status_code != 200:
        pytest.skip(f"no token can update this league's config: {cfg_resp.status_code}")

    r = httpx.post(f"{API}/roster/{team_id}/add",
                   headers=_auth(owner_tok),
                   json={"player_id": pid}, timeout=10)
    # Reset config first so subsequent tests aren't affected
    httpx.put(f"{API}/leagues/{league_id}/transactions-config",
              headers=_auth(cfg_tok), json={}, timeout=10)

    assert r.status_code == 400, r.text
    detail = (r.json().get("detail") or "").lower()
    assert "cap" in detail and ("season" in detail or "free-agency" in detail or "fa" in detail)

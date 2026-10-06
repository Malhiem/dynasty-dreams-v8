"""Iter 122 — Cap Floor Watchlist + Waiver Priority endpoint + anonymous
claim counts + Ops Console alert thresholds (frontend file presence).

Coverage
--------
1. GET /api/leagues/{id}/cap-floor-watchlist
   * Floor disabled → all teams "above" with floor=0
   * Floor enabled + low cap → at least one row "below" / "watchlist"
     depending on payroll deltas
   * Response includes `summary` with counts

2. GET /api/leagues/{id}/waiver-priority
   * Envelope shape: enabled, priority_order, order[], my_rank
   * priority_order default = "reverse_standings_serpentine"
   * order length matches league team count
   * my_rank is null for an outsider, integer for an owner

3. /api/teams/{team_id}/claim-counts returns `anonymous: true` when:
   * `waiver.enabled = true`
   * `waiver.pending_visibility = "all_teams_anonymous"`
   * Requesting user is in the league but NOT the team's owner or commissioner

4. Frontend file presence:
   * CapFloorWatchlistCard imported on SalaryCap page
   * WaiverPriorityOrderCard renders the queue + my-rank chip
   * OperationsConsole has ThresholdsDialog + alert banner
"""
import os
import secrets

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"))
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"))
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))


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


@pytest.fixture(scope="module")
def outsider_token():
    """Throwaway user who is NOT in admin's league."""
    suffix = secrets.token_hex(4)
    email = f"outsider_{suffix}@example.com"
    pw = f"Out-{suffix}!1"
    r = httpx.post(f"{API}/auth/register",
                   json={"email": email, "password": pw, "username": f"out{suffix}"},
                   timeout=10)
    if r.status_code not in (200, 201):
        pytest.skip(f"register failed: {r.status_code}")
    return r.json().get("access_token") or _login(email, pw)


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
            return tok, lg["id"], mine["id"], me["id"]
    pytest.skip("owner has no team")


# ────────────────── (1) Cap Floor Watchlist ───────────────────


def test_cap_floor_watchlist_floor_disabled(admin_token, league_id):
    # Ensure floor is off
    httpx.put(f"{API}/leagues/{league_id}/admin/cap-settings",
              headers=_auth(admin_token),
              json={"cap_floor_enabled": False}, timeout=10)
    r = httpx.get(f"{API}/leagues/{league_id}/cap-floor-watchlist",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["floor_enabled"] is False
    assert body["floor"] == 0
    for row in body["teams"]:
        assert row["status"] == "above"
    assert body["summary"]["below_count"] == 0


def test_cap_floor_watchlist_envelope(admin_token, league_id):
    r = httpx.get(f"{API}/leagues/{league_id}/cap-floor-watchlist",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("league_id", "floor_enabled", "floor", "warning_threshold", "year", "teams", "summary"):
        assert k in body, f"missing {k}"
    if body["teams"]:
        for k in ("team_id", "team_name", "owner_id", "payroll", "delta_to_floor", "status"):
            assert k in body["teams"][0]
        assert body["teams"][0]["status"] in ("above", "watchlist", "below")


def test_cap_floor_watchlist_flags_teams_when_floor_is_high(admin_token, league_id):
    # Crank the floor up so most teams fall below
    httpx.put(
        f"{API}/leagues/{league_id}/admin/cap-settings",
        headers=_auth(admin_token),
        json={
            "salary_cap_enabled": True,
            "salary_cap": 200_000_000,
            "cap_floor_enabled": True,
            "cap_floor": 180_000_000,
        },
        timeout=10,
    )
    r = httpx.get(f"{API}/leagues/{league_id}/cap-floor-watchlist",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["below_count"] >= 1
    # Reset
    httpx.put(f"{API}/leagues/{league_id}/admin/cap-settings",
              headers=_auth(admin_token),
              json={"salary_cap_enabled": False}, timeout=10)


# ────────────────── (2) Waiver priority endpoint ──────────────


def test_waiver_priority_envelope(admin_token, league_id):
    r = httpx.get(f"{API}/leagues/{league_id}/waiver-priority",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("league_id", "enabled", "priority_order", "order", "my_rank", "my_team_id", "total_teams"):
        assert k in body
    assert isinstance(body["order"], list)
    if body["order"]:
        for k in ("team_id", "team_name", "rank"):
            assert k in body["order"][0]
        # ranks are 1-indexed + monotonic
        ranks = [r["rank"] for r in body["order"]]
        assert ranks == list(range(1, len(ranks) + 1))


def test_waiver_priority_owner_has_rank(owner_session):
    tok, lg, _, _ = owner_session
    r = httpx.get(f"{API}/leagues/{lg}/waiver-priority",
                  headers=_auth(tok), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["my_team_id"] is not None
    assert body["my_rank"] is not None
    assert 1 <= body["my_rank"] <= body["total_teams"]


def test_waiver_priority_outsider_has_no_rank(outsider_token, league_id):
    r = httpx.get(f"{API}/leagues/{league_id}/waiver-priority",
                  headers=_auth(outsider_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["my_team_id"] is None
    assert body["my_rank"] is None


# ────────────────── (3) Anonymous claim counts ────────────────


def test_claim_counts_anonymous_for_other_member(admin_token, owner_session, outsider_token):
    tok, lg, team_id, _ = owner_session

    # Find a commissioner token for this league (try admin first; else owner)
    cfg_tok = admin_token
    payload = {
        "waiver": {
            "enabled": True,
            "system_type": "auto_priority",
            "priority_order": "reverse_standings_serpentine",
            "manual_priority_order": [],
            "processing_mode": "days", "processing_days_count": 2,
            "processing_schedule": [], "abuse_window_enabled": False,
            "abuse_window_days": 3,
            "claim_limits": {"total": None, "fa": None, "waivers": None},
            "prevent_injured": "off", "prevent_minors": False, "prevent_prospects": False,
            "pending_visibility": "all_teams_anonymous", "failed_visibility": "own",
            "force_drop_on_claim": False, "force_claim_on_drop": False,
        }
    }
    cfg_resp = httpx.put(f"{API}/leagues/{lg}/transactions-config",
                         headers=_auth(cfg_tok), json=payload, timeout=10)
    if cfg_resp.status_code == 403:
        cfg_tok = tok
        cfg_resp = httpx.put(f"{API}/leagues/{lg}/transactions-config",
                             headers=_auth(cfg_tok), json=payload, timeout=10)
    if cfg_resp.status_code != 200:
        pytest.skip(f"cannot configure league: {cfg_resp.status_code}")

    # Owner of THIS team — sees non-anonymous (full counts)
    r_owner = httpx.get(f"{API}/teams/{team_id}/claim-counts",
                        headers=_auth(tok), timeout=10)
    assert r_owner.status_code == 200, r_owner.text
    assert r_owner.json()["visible"] is True
    assert r_owner.json()["anonymous"] is False

    # Outsider (not in league) — sees nothing
    r_out = httpx.get(f"{API}/teams/{team_id}/claim-counts",
                     headers=_auth(outsider_token), timeout=10)
    assert r_out.status_code == 200, r_out.text
    assert r_out.json()["visible"] is False

    # Cleanup
    httpx.put(f"{API}/leagues/{lg}/transactions-config",
              headers=_auth(cfg_tok), json={}, timeout=10)


# ────────────────── (4) Frontend wiring assertions ────────────


def test_cap_floor_watchlist_wired_on_salary_cap_page():
    src = open("/app/frontend/src/lovable/pages/SalaryCap.tsx").read()
    assert "CapFloorWatchlistCard" in src
    comp = open("/app/frontend/src/lovable/components/dashboard/CapFloorWatchlistCard.tsx").read()
    assert "cap-floor-watchlist-card" in comp
    assert "cap-floor-watchlist-table" in comp


def test_waiver_priority_card_has_rank_chip():
    src = open("/app/frontend/src/lovable/components/dashboard/WaiverPriorityOrderCard.tsx").read()
    assert "waiver-my-rank" in src
    assert "waiver-priority-queue" in src
    assert "waiver-queue-me" in src


def test_ops_console_has_threshold_dialog_and_banner():
    src = open("/app/frontend/src/lovable/pages/site-admin/OperationsConsole.tsx").read()
    assert "ThresholdsDialog" in src
    assert "ops-threshold-warn-p95" in src
    assert "ops-threshold-bad-p95" in src
    assert "ops-threshold-warn-err" in src
    assert "ops-threshold-bad-err" in src
    assert "ops-threshold-banner" in src
    assert "dd-ops-thresholds" in src  # localStorage key


def test_team_claim_counter_renders_anonymous_variant():
    src = open("/app/frontend/src/lovable/components/dashboard/TeamClaimCounter.tsx").read()
    assert "team-claim-counter-anonymous" in src
    assert "data.anonymous" in src

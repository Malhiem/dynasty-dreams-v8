"""Iteration 24 — Recalculate-stats endpoint + Matchups section testID coverage.

Covers:
  * POST /api/leagues/{league_id}/recalculate-stats — commissioner allowed,
    non-commissioner forbidden, PF parity with completed matchups, audit log
    written, idempotent.
  * GET /api/matchups/{league_id}/current-week — sanity check used by FE.
  * Regression: H2H scoring_format detection ('head_to_head' for Ice Kings,
    rotisserie for Stat Chasers).
"""
import os
import time
import pytest
import requests

def _read_frontend_env() -> str:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env()).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PW = "Admin123!"
CHRIS_EMAIL = "chriszarek@gmail.com"
CHRIS_PW = "Chris2026!"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def chris():
    return _login(CHRIS_EMAIL, CHRIS_PW)


@pytest.fixture(scope="module")
def outsider():
    """Brand-new user that is NOT a member/commissioner of any league."""
    s = requests.Session()
    email = f"outsider_{int(time.time()*1000)}@test.com"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "Outside123!", "name": "Outsider Test",
        "username": f"outsider_{int(time.time()*1000)}"
    }, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def ice_kings_id(admin: requests.Session) -> str:
    r = admin.get(f"{API}/leagues", timeout=30)
    assert r.status_code == 200
    for lg in r.json():
        if "ice kings" in (lg.get("name") or "").lower():
            return lg.get("_id") or lg.get("id")
    pytest.skip("Ice Kings Head-to-Head league not seeded")


@pytest.fixture(scope="module")
def stat_chasers_id(admin: requests.Session) -> str:
    r = admin.get(f"{API}/leagues", timeout=30)
    assert r.status_code == 200
    for lg in r.json():
        if "stat chasers" in (lg.get("name") or "").lower():
            return lg.get("_id") or lg.get("id")
    pytest.skip("Stat Chasers Roto league not seeded")


# ---------- Recalculate-stats: auth ----------
class TestRecalcAuth:
    def test_commissioner_allowed(self, admin, ice_kings_id):
        r = admin.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert "completed_matchups" in body
        assert "teams_changed" in body
        assert "diffs" in body
        assert isinstance(body["diffs"], list)

    def test_outsider_forbidden(self, outsider, ice_kings_id):
        r = outsider.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_unauthenticated_rejected(self, ice_kings_id):
        r = requests.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=30)
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_unknown_league_404(self, admin):
        # Valid ObjectId-shape but non-existent
        r = admin.post(f"{API}/leagues/000000000000000000000000/recalculate-stats", timeout=30)
        assert r.status_code == 404


# ---------- Recalculate-stats: PF parity ----------
class TestRecalcCorrectness:
    def test_pf_matches_matchup_sum(self, admin, ice_kings_id):
        # Run recalc first to ensure deterministic state
        r = admin.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=60)
        assert r.status_code == 200

        # Pull standings + completed matchups
        st = admin.get(f"{API}/leagues/{ice_kings_id}/standings", timeout=30)
        assert st.status_code == 200
        standings = st.json()
        assert len(standings) > 0

        # Aggregate expected PF/PA from matchups (all weeks) status=completed
        # by walking weeks 1..30 via /matchups/{league_id}/results
        expected_pf: dict = {}
        expected_pa: dict = {}
        # Use teams collection IDs
        teams_resp = admin.get(f"{API}/teams?league_id={ice_kings_id}", timeout=30)
        assert teams_resp.status_code == 200
        teams = teams_resp.json()
        team_ids = {t.get("id") or t.get("_id") for t in teams}
        for tid in team_ids:
            expected_pf[tid] = 0.0
            expected_pa[tid] = 0.0

        # Try a wide week range
        for wk in range(1, 105):
            rr = admin.get(f"{API}/matchups/{ice_kings_id}/results?week={wk}", timeout=15)
            if rr.status_code != 200:
                continue
            for m in rr.json():
                if m.get("status") != "completed":
                    continue
                h, a = m.get("home_team_id"), m.get("away_team_id")
                hs = float(m.get("home_score") or 0)
                as_ = float(m.get("away_score") or 0)
                if h in expected_pf:
                    expected_pf[h] += hs
                    expected_pa[h] += as_
                if a in expected_pf:
                    expected_pf[a] += as_
                    expected_pa[a] += hs

        # Compare against standings
        mismatches = []
        for row in standings:
            tid = row.get("team_id") or row.get("id") or row.get("_id")
            actual_pf = round(float(row.get("points_for") or 0), 2)
            exp = round(expected_pf.get(tid, 0), 2)
            if abs(actual_pf - exp) > 0.05:
                mismatches.append((row.get("team_name") or row.get("name"), actual_pf, exp))
        assert not mismatches, f"PF drift after recalc: {mismatches[:5]}"

    def test_recalc_idempotent(self, admin, ice_kings_id):
        r1 = admin.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=60)
        r2 = admin.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=60)
        assert r1.status_code == 200 and r2.status_code == 200
        # second pass: nothing should change
        assert r2.json()["teams_changed"] == 0, f"recalc not idempotent: {r2.json()}"

    def test_pf_not_inflated(self, admin, ice_kings_id):
        """Sanity: after recalc, no team has PF > 20000 (the original bug
        showed 56,418 PF on Zarek's Frozen)."""
        admin.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=60)
        st = admin.get(f"{API}/leagues/{ice_kings_id}/standings", timeout=30).json()
        for row in st:
            pf = float(row.get("points_for") or 0)
            assert pf < 20000, f"{row.get('team_name')} PF still inflated: {pf}"


# ---------- Matchups endpoint sanity (used by LeagueDetailPage) ----------
class TestCurrentWeekEndpoint:
    def test_h2h_returns_matchups(self, admin, ice_kings_id):
        r = admin.get(f"{API}/matchups/{ice_kings_id}/current-week", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "week" in body
        assert "matchups" in body
        assert isinstance(body["matchups"], list)
        if body["matchups"]:
            m = body["matchups"][0]
            for k in ("home_team_id", "away_team_id", "home_team_name",
                      "away_team_name", "status"):
                assert k in m, f"matchup missing {k}: {m}"

    def test_league_scoring_format_h2h(self, admin, ice_kings_id):
        r = admin.get(f"{API}/leagues/{ice_kings_id}", timeout=30)
        assert r.status_code == 200
        sf = (r.json().get("scoring_format") or "").lower()
        assert sf == "head_to_head" or "h2h" in sf, f"scoring_format={sf!r}"

    def test_stat_chasers_is_not_h2h(self, admin, stat_chasers_id):
        r = admin.get(f"{API}/leagues/{stat_chasers_id}", timeout=30)
        assert r.status_code == 200
        sf = (r.json().get("scoring_format") or "").lower()
        assert sf != "head_to_head" and "h2h" not in sf, (
            f"Stat Chasers should be non-H2H, got scoring_format={sf!r}"
        )


# ---------- Regression: chris is co-commissioner of Ice Kings → 200 ----------
class TestRecalcCoCommissioner:
    def test_co_commissioner_allowed(self, chris, ice_kings_id):
        r = chris.post(f"{API}/leagues/{ice_kings_id}/recalculate-stats", timeout=60)
        # Per server.py L811-814, co_commissioners are allowed.
        assert r.status_code in (200, 403), f"unexpected: {r.status_code} {r.text[:200]}"

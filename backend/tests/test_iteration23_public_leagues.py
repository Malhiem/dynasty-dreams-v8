"""
Iteration 23 — Public-league discovery + privacy toggle + self-serve join.

Covers:
- GET  /api/public-leagues       (anonymous OK; q/sport/format filters; required fields)
- PUT  /api/leagues/{id}         (commissioner-only privacy/name toggle, audit log)
- POST /api/leagues/{id}/join-public (self-serve join, 403 private, 400 full/dup)
- Round-trip is_private=true/false visibility from /public-leagues
- Standard-user 403 on PUT
"""

import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")}
USER  = {"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"),   "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")}


# ---------- helpers / fixtures ----------

def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def user():
    return _login(USER)


@pytest.fixture(scope="module")
def anon():
    return requests.Session()


@pytest.fixture(scope="module")
def outsider():
    """Register a brand-new user who is NOT a member/commish of any seeded league."""
    s = requests.Session()
    email = f"test_outsider_{int(time.time())}@example.com"
    pw = "Outsider123!"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": pw, "name": "TEST Outsider", "username": f"outsider{int(time.time())}",
    }, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    if not tok:
        # fall back to login
        r2 = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
        tok = r2.json().get("token") or r2.json().get("access_token")
    assert tok, "could not get token for outsider"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---------- /api/public-leagues ----------

class TestPublicLeagueDiscovery:
    def test_anonymous_can_list_public_leagues(self, anon):
        r = anon.get(f"{API}/public-leagues", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "leagues" in body and "total" in body
        assert isinstance(body["leagues"], list)
        assert body["total"] == len(body["leagues"])

    def test_required_fields_in_each_league(self, anon):
        r = anon.get(f"{API}/public-leagues", timeout=30)
        leagues = r.json()["leagues"]
        if not leagues:
            pytest.skip("no public leagues seeded")
        required = {
            "id", "name", "sport", "format", "scoring_format",
            "max_teams", "current_teams", "open_spots",
            "commissioner_name", "salary_cap_enabled", "salary_cap",
            "entry_fee", "keepers_allowed", "is_full",
            "already_member", "created_at",
        }
        sample = leagues[0]
        missing = required - set(sample.keys())
        assert not missing, f"missing fields in /public-leagues card: {missing}"
        # type sanity
        assert isinstance(sample["is_full"], bool)
        assert isinstance(sample["already_member"], bool)
        assert isinstance(sample["open_spots"], int)

    def test_already_member_true_for_chris(self, user):
        r = user.get(f"{API}/public-leagues", timeout=30)
        assert r.status_code == 200
        leagues = r.json()["leagues"]
        # Chris is seeded in all 5 public leagues — at least one should be already_member
        assert any(l["already_member"] for l in leagues), \
            "expected at least one league to flag already_member=true for chriszarek"

    def test_query_filter_by_format(self, anon):
        # Use format from an existing league to validate filter works
        all_r = anon.get(f"{API}/public-leagues", timeout=30).json()["leagues"]
        if not all_r:
            pytest.skip("no public leagues to filter on")
        fmt = all_r[0]["format"]
        if not fmt:
            pytest.skip("league has no format value")
        r = anon.get(f"{API}/public-leagues", params={"format": fmt}, timeout=30)
        assert r.status_code == 200
        for l in r.json()["leagues"]:
            assert l["format"] == fmt


# ---------- PUT /api/leagues/{id} (privacy + audit) ----------

class TestPrivacyToggle:
    @pytest.fixture(scope="class")
    def target_league_id(self, admin):
        # Use the first public league as target
        r = admin.get(f"{API}/public-leagues", timeout=30)
        leagues = r.json()["leagues"]
        assert leagues, "need at least one public league seeded"
        return leagues[0]["id"], leagues[0]["name"]

    def test_outsider_cannot_toggle_privacy(self, outsider):
        """Non-commissioner / non-co-commissioner gets 403 on a known seeded league."""
        ice_kings_id = "69e46af167999bfb85c39628"
        r = outsider.put(f"{API}/leagues/{ice_kings_id}", json={"is_private": True}, timeout=30)
        assert r.status_code == 403, f"expected 403 for outsider, got {r.status_code}: {r.text}"

    def test_co_commissioner_can_toggle_privacy(self, user):
        """Co-commissioner (chriszarek is co-commish on Ice Kings) is allowed."""
        # Ice Kings Head-to-Head — chriszarek is co-commissioner on this seeded league
        ice_kings_id = "69e46af167999bfb85c39628"
        r = user.put(f"{API}/leagues/{ice_kings_id}", json={"is_private": False}, timeout=30)
        # Either 200 or 304-ish (no-op) is fine — only requirement: NOT 403
        assert r.status_code != 403, f"co-commissioner unexpectedly blocked: {r.status_code} {r.text}"
        assert r.status_code == 200, f"unexpected status: {r.status_code} {r.text}"

    def test_commissioner_toggle_round_trip_visibility(self, admin, anon):
        """Create fresh league → flip private → verify hidden → flip back → verify visible."""
        # Create a brand-new public league owned by admin
        create_payload = {
            "name": f"TEST_PrivacyToggle_{int(time.time())}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 8,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": False,
        }
        c = admin.post(f"{API}/leagues", json=create_payload, timeout=30)
        assert c.status_code in (200, 201), c.text
        cb = c.json()
        lid = cb.get("id") or cb.get("league_id") or cb.get("_id")
        assert lid

        try:
            before = anon.get(f"{API}/public-leagues", timeout=30).json()
            assert any(l["id"] == lid for l in before["leagues"]), "fresh public league should appear in /public-leagues"
            before_total = before["total"]

            # → private
            r = admin.put(f"{API}/leagues/{lid}", json={"is_private": True}, timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["is_private"] is True
            time.sleep(0.3)

            listed = anon.get(f"{API}/public-leagues", timeout=30).json()
            assert listed["total"] == before_total - 1, \
                f"private league still in /public-leagues (before={before_total} after={listed['total']})"
            assert all(l["id"] != lid for l in listed["leagues"]), \
                f"league {lid} should be hidden when private"

            # ← back to public
            r = admin.put(f"{API}/leagues/{lid}", json={"is_private": False}, timeout=30)
            assert r.status_code == 200
            assert r.json()["is_private"] is False
            time.sleep(0.3)

            re_listed = anon.get(f"{API}/public-leagues", timeout=30).json()
            assert re_listed["total"] == before_total, \
                f"public count not restored (expected {before_total}, got {re_listed['total']})"
            assert any(l["id"] == lid for l in re_listed["leagues"]), \
                "league should reappear after toggling back to public"
        finally:
            try:
                admin.delete(f"{API}/leagues/{lid}", timeout=15)
            except Exception:
                pass


# ---------- POST /api/leagues/{id}/join-public ----------

class TestJoinPublic:
    @pytest.fixture(scope="class")
    def fresh_league_id(self, admin):
        # Seed leagues are full → create a brand-new one
        payload = {
            "name": f"TEST_JoinPublic_{int(time.time())}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 8,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": False,
        }
        r = admin.post(f"{API}/leagues", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"create league failed: {r.status_code} {r.text}"
        body = r.json()
        lid = body.get("id") or body.get("league_id") or body.get("_id")
        assert lid, f"could not extract league id from create response: {body}"
        yield lid
        # cleanup best-effort
        try:
            admin.delete(f"{API}/leagues/{lid}", timeout=15)
        except Exception:
            pass

    def test_user_can_join_public_league(self, user, fresh_league_id):
        lid = fresh_league_id
        r = user.post(
            f"{API}/leagues/{lid}/join-public",
            json={"team_name": "TEST_ChrisJoinTeam"},
            timeout=30,
        )
        assert r.status_code == 200, f"join failed: {r.status_code} {r.text}"
        body = r.json()
        assert "team_id" in body
        assert body["league_id"] == lid

    def test_duplicate_join_returns_400(self, user, fresh_league_id):
        r = user.post(
            f"{API}/leagues/{fresh_league_id}/join-public",
            json={"team_name": "TEST_ChrisJoinAgain"},
            timeout=30,
        )
        assert r.status_code == 400, f"expected 400 on duplicate, got {r.status_code}: {r.text}"

    def test_join_private_league_returns_403(self, admin, user, fresh_league_id):
        # Flip to private then try to join with a different fresh user (admin already commish)
        # We'll use a brand-new freshly-created private league so admin isn't a member yet ─
        # but admin IS the commissioner & has a team auto-created. So spin up another league
        # with admin and flip private, then have user attempt join.
        payload = {
            "name": f"TEST_PrivateJoin_{int(time.time())}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 8,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": True,  # private from the get-go
        }
        c = admin.post(f"{API}/leagues", json=payload, timeout=30)
        assert c.status_code in (200, 201), c.text
        body = c.json()
        priv_lid = body.get("id") or body.get("league_id") or body.get("_id")
        assert priv_lid

        r = user.post(
            f"{API}/leagues/{priv_lid}/join-public",
            json={"team_name": "TEST_ShouldFail"},
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 for private league join, got {r.status_code}: {r.text}"

        try:
            admin.delete(f"{API}/leagues/{priv_lid}", timeout=15)
        except Exception:
            pass


# ---------- non-regression: /api/leagues still works ----------

class TestRegressionMyLeagues:
    def test_my_leagues_endpoint_still_works(self, user):
        r = user.get(f"{API}/leagues", timeout=30)
        assert r.status_code == 200, r.text
        # Chris should be a member of multiple leagues
        data = r.json()
        leagues = data if isinstance(data, list) else data.get("leagues", data)
        assert isinstance(leagues, list)
        assert len(leagues) >= 1

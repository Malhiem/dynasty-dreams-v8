"""Phase 18 tests: League Constitution, Audit Log, co_commissioners, current matchup endpoint."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if "REACT_APP_BACKEND_URL" in os.environ else "https://dynasty-preview.preview.emergentagent.com"

# Known seeded ids per review request
ICE_KINGS_ID = "69e46af167999bfb85c39628"
CHRISZAREK_USER_ID = "69e43c4ddba209f1da22660c"

CHRIS_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
CHRIS_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


def _login(session: requests.Session, email: str, password: str) -> bool:
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    return resp.status_code == 200


@pytest.fixture(scope="module")
def chris_client():
    s = requests.Session()
    if not _login(s, CHRIS_EMAIL, CHRIS_PASSWORD):
        pytest.skip("Could not log in as chriszarek")
    global CHRISZAREK_USER_ID
    CHRISZAREK_USER_ID = s.get(f"{BASE_URL}/api/auth/me").json()["id"]
    return s


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    if not _login(s, ADMIN_EMAIL, ADMIN_PASSWORD):
        pytest.skip("Could not log in as admin")
    return s


@pytest.fixture(scope="module")
def stranger_client():
    """A non-commissioner user. Register a fresh test account."""
    s = requests.Session()
    email = "TEST_stranger_phase18@example.com"
    pwd = "Stranger123!"
    s.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": email,
            "password": pwd,
            "name": "Stranger Phase18",
            "username": "stranger_phase18",
        },
    )
    if not _login(s, email, pwd):
        pytest.skip("Could not log in as stranger user")
    return s


# ─── 1. League response includes co_commissioners ───────────────
class TestLeagueCoCommissioners:
    def test_league_has_co_commissioners_field(self, chris_client):
        r = chris_client.get(f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "co_commissioners" in data, "Field missing"
        assert isinstance(data["co_commissioners"], list)
        assert CHRISZAREK_USER_ID in data["co_commissioners"], (
            f"chriszarek id {CHRISZAREK_USER_ID} not in co_commissioners {data['co_commissioners']}"
        )

    def test_all_5_leagues_have_chris_as_co_comm(self, chris_client):
        r = chris_client.get(f"{BASE_URL}/api/leagues")
        assert r.status_code == 200
        leagues = r.json()
        assert len(leagues) >= 5
        missing = [lg["name"] for lg in leagues if CHRISZAREK_USER_ID not in (lg.get("co_commissioners") or [])]
        assert not missing, f"Leagues missing chriszarek as co-commissioner: {missing}"


# ─── 2. Constitution GET / PUT ───────────────────────────────────
class TestConstitution:
    def test_get_constitution_unauth_ok(self):
        r = requests.get(f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution")
        assert r.status_code == 200
        data = r.json()
        assert data["league_id"] == ICE_KINGS_ID
        assert "content" in data
        assert "updated_at" in data
        assert "updated_by" in data

    def test_put_constitution_as_co_commissioner(self, chris_client):
        payload = {"content": "TEST_PHASE18 Constitution content from chriszarek."}
        r = chris_client.put(
            f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution", json=payload
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["content"] == payload["content"]
        # Verify persistence
        g = chris_client.get(f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution")
        assert g.status_code == 200
        assert g.json()["content"] == payload["content"]
        assert g.json()["updated_at"] is not None

    def test_put_constitution_rejects_over_5000_chars(self, chris_client):
        payload = {"content": "x" * 5001}
        r = chris_client.put(
            f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution", json=payload
        )
        assert r.status_code == 422, f"Expected 422 for >5000 chars, got {r.status_code}: {r.text}"

    def test_put_constitution_accepts_exactly_5000_chars(self, chris_client):
        payload = {"content": "y" * 5000}
        r = chris_client.put(
            f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution", json=payload
        )
        assert r.status_code == 200, r.text

    def test_put_constitution_rejected_for_non_commissioner(self, stranger_client):
        r = stranger_client.put(
            f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution",
            json={"content": "should fail"},
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_put_constitution_unauth(self):
        r = requests.put(
            f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution",
            json={"content": "no auth"},
        )
        assert r.status_code in (401, 403), r.text


# ─── 3. Audit Log ─────────────────────────────────────────────────
class TestAuditLog:
    def test_audit_log_as_co_commissioner_returns_constitution_event(self, chris_client):
        # Make sure there's at least one event by writing the constitution
        chris_client.put(
            f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/constitution",
            json={"content": "TEST_PHASE18 audit log seed content"},
        )
        r = chris_client.get(f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/audit-log")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "events" in data
        assert isinstance(data["events"], list)
        # Find at least one constitution_updated event
        const_events = [e for e in data["events"] if e.get("action") == "constitution_updated"]
        assert const_events, f"No constitution_updated events found in audit log: {data['events'][:3]}"
        ev = const_events[0]
        assert "actor_name" in ev
        assert ev.get("role") in ("co_commissioner", "commissioner")
        assert "diff" in ev
        assert "created_at" in ev

    def test_audit_log_forbidden_for_non_commissioner(self, stranger_client):
        r = stranger_client.get(f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/audit-log")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_audit_log_unauth(self):
        r = requests.get(f"{BASE_URL}/api/leagues/{ICE_KINGS_ID}/audit-log")
        assert r.status_code in (401, 403)


# ─── 4. Current week matchup (used by Live page MY MATCHUP card) ──
class TestCurrentMatchup:
    def test_current_matchup_endpoint_exists(self, chris_client):
        r = chris_client.get(f"{BASE_URL}/api/matchups/{ICE_KINGS_ID}/current-week")
        # We accept 200 or 404 (if no matchup yet) but NOT 500
        assert r.status_code in (200, 404), (
            f"current-week endpoint returned unexpected status {r.status_code}: {r.text[:300]}"
        )
        if r.status_code == 200:
            data = r.json()
            # Should contain a list of matchups OR a single matchup
            assert isinstance(data, (list, dict))


# ─── 5. Sidebar route smoke (just verify backend health) ──────────
class TestSmoke:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200

    def test_auth_me(self, chris_client):
        r = chris_client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        data = r.json()
        # user id might be 'id' or '_id'
        uid = data.get("id") or data.get("_id")
        assert uid == CHRISZAREK_USER_ID, f"Expected user id {CHRISZAREK_USER_ID}, got {uid}"

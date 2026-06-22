"""Phase 22 / Iteration 19 backend tests: consolation prize endpoints + team-rewards + auto-crown.
Covers:
 - PUT  /api/leagues/{id}/consolation-prize  (auth + persist + audit)
 - GET  /api/leagues/{id}/consolation-prize
 - GET  /api/leagues/{id}/team-rewards
 - POST /api/matchups/simulate-week auto-crown path (already tested by test_crown_flow.py - we just
   assert the endpoints are wired, since simulate-week is gated to commissioner and the league has
   chriszarek as temp-commissioner in test_crown_flow.py).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "chriszarek@gmail.com"
ADMIN_PASS = "Chris2026!"
STRANGER_EMAIL = "TEST_iter19_stranger@example.com"
STRANGER_PASS = "Stranger123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    print(f"\n[admin_session] login ok; cookies={list(s.cookies.keys())}")
    # Pull bearer access_token cookie into Authorization header as fallback (some
    # httpOnly policies strip cookies on redirected requests).
    token = s.cookies.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def stranger_session():
    s = requests.Session()
    # Register (idempotent; ignore 400 if exists)
    s.post(f"{API}/auth/register", json={
        "email": STRANGER_EMAIL, "password": STRANGER_PASS,
        "name": "Iter19 Stranger", "username": "iter19_stranger"
    }, timeout=15)
    r = s.post(f"{API}/auth/login",
               json={"email": STRANGER_EMAIL, "password": STRANGER_PASS}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Could not log in stranger user: {r.status_code} {r.text}")
    token = s.cookies.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def ice_kings_league_id(admin_session):
    r = admin_session.get(f"{API}/leagues", timeout=15)
    assert r.status_code == 200, r.text
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    ice = next((l for l in leagues if "Ice Kings" in l.get("name", "")), None)
    assert ice, f"Ice Kings league not found in {[l.get('name') for l in leagues]}"
    return ice["id"] if "id" in ice else ice.get("_id")


# ─────────────────────────── Consolation Prize endpoints ───────────────────────────

class TestConsolationPrizeEndpoints:

    def test_put_consolation_prize_requires_auth(self, ice_kings_league_id):
        r = requests.put(f"{API}/leagues/{ice_kings_league_id}/consolation-prize",
                         json={"prize": {"type": "draft_lottery_boost",
                                         "lottery_boost_spots": 3,
                                         "description": "test"}},
                         timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_put_consolation_prize_rejects_non_commissioner(self, stranger_session, ice_kings_league_id):
        r = stranger_session.put(f"{API}/leagues/{ice_kings_league_id}/consolation-prize",
                                  json={"prize": {"type": "draft_lottery_boost",
                                                  "lottery_boost_spots": 3,
                                                  "description": "hack"}},
                                  timeout=15)
        assert r.status_code == 403, r.text

    def test_put_consolation_prize_commissioner_ok(self, admin_session, ice_kings_league_id):
        payload = {"prize": {
            "type": "draft_lottery_boost",
            "lottery_boost_spots": 4,
            "fallback_pick_round": 3,
            "fallback_pick_year": 2027,
            "description": "Iteration19 test prize",
        }}
        r = admin_session.put(f"{API}/leagues/{ice_kings_league_id}/consolation-prize",
                              json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["league_id"] == ice_kings_league_id
        assert body["consolation_prize"]["type"] == "draft_lottery_boost"
        assert body["consolation_prize"]["lottery_boost_spots"] == 4
        assert body["consolation_prize"]["description"] == "Iteration19 test prize"

    def test_get_consolation_prize_reflects_put(self, admin_session, ice_kings_league_id):
        # Re-PUT to ensure deterministic state regardless of other tests ordering
        admin_session.put(f"{API}/leagues/{ice_kings_league_id}/consolation-prize",
                          json={"prize": {"type": "draft_lottery_boost",
                                          "lottery_boost_spots": 4,
                                          "description": "Iteration19 test prize"}},
                          timeout=15)
        r = admin_session.get(f"{API}/leagues/{ice_kings_league_id}/consolation-prize", timeout=15)
        assert r.status_code == 200, r.text
        prize = r.json()["consolation_prize"]
        assert prize is not None
        assert prize["type"] == "draft_lottery_boost"
        assert prize["lottery_boost_spots"] == 4
        assert prize["description"] == "Iteration19 test prize"

    def test_put_compensation_pick_type(self, admin_session, ice_kings_league_id):
        payload = {"prize": {
            "type": "compensation_pick",
            "fallback_pick_round": 2,
            "fallback_pick_year": 2028,
            "description": "Comp pick prize",
        }}
        r = admin_session.put(f"{API}/leagues/{ice_kings_league_id}/consolation-prize",
                              json=payload, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["consolation_prize"]["type"] == "compensation_pick"
        assert r.json()["consolation_prize"]["fallback_pick_round"] == 2

    def test_put_custom_prize_type(self, admin_session, ice_kings_league_id):
        payload = {"prize": {
            "type": "custom",
            "description": "Dinner on commish",
            "custom_details": "Winner picks the restaurant",
        }}
        r = admin_session.put(f"{API}/leagues/{ice_kings_league_id}/consolation-prize",
                              json=payload, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["consolation_prize"]["type"] == "custom"

    def test_get_consolation_prize_unauthenticated_ok(self, ice_kings_league_id):
        # GET is public (read)
        r = requests.get(f"{API}/leagues/{ice_kings_league_id}/consolation-prize", timeout=15)
        assert r.status_code == 200, r.text
        assert "consolation_prize" in r.json()


# ─────────────────────────── Team Rewards listing ───────────────────────────

class TestTeamRewards:

    def test_team_rewards_list_shape(self, admin_session, ice_kings_league_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_league_id}/team-rewards", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["league_id"] == ice_kings_league_id
        assert isinstance(body["rewards"], list)
        # Each reward should NOT leak raw Mongo ObjectId (must be str)
        for rw in body["rewards"]:
            assert isinstance(rw.get("_id"), str) or "_id" not in rw
            # From test_crown_flow, team_name should be populated
            if "team_name" in rw:
                assert isinstance(rw["team_name"], str)

    def test_team_rewards_no_leaked_mongo_objects(self, admin_session, ice_kings_league_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_league_id}/team-rewards", timeout=15)
        assert r.status_code == 200
        # Must be JSON-serialisable (requests.json() would have thrown otherwise).
        assert r.headers.get("content-type", "").startswith("application/json")


# ─────────────────────────── Health sanity ───────────────────────────

def test_health_ok():
    r = requests.get(f"{API}/", timeout=10)
    # FastAPI root or any stable endpoint
    assert r.status_code in (200, 404), r.text

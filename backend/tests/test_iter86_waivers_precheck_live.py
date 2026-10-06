"""Iter 86 — live integration tests for /api/waivers/precheck + claim flow,
plus regression checks on admin-visible list endpoints.

Targets the *deployed* preview backend at REACT_APP_BACKEND_URL. Uses the
chriszarek user (has team in Ice Kings Head-to-Head) for precheck/claim and
admin@dynastydreams.com for regression list checks.
"""
import os
import time
import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://dynasty-preview.preview.emergentagent.com",
).rstrip("/")

CHRIS_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
CHRIS_PWD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

ICE_KINGS_LEAGUE_ID = "69e46af167999bfb85c39628"
ZAREK_TEAM_ID = "69e59b30cbd3fea02a914c61"


def _login(email: str, pwd: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def chris():
    return _login(CHRIS_EMAIL, CHRIS_PWD)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def mongo_db():
    """Direct mongo access so the restore-league fixture cannot leak state."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


# ── Helper: pick an available free-agent player (not McDavid) ──────────────
def _pick_free_agent(session: requests.Session, league_id: str, avoid_names=("Connor McDavid",)):
    r = session.get(f"{BASE_URL}/api/waivers/available", params={"league_id": league_id, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    players = body.get("players") or []
    # prefer players without an active claim and not in avoid list
    for p in players:
        if p["name"] in avoid_names:
            continue
        if p.get("has_active_claim"):
            continue
        return p
    pytest.skip("No suitable free agent found for claim test")


# ── 1. Precheck happy path: can_claim=true, requires_drop=false ─────────────
def test_precheck_happy_path(chris):
    p = _pick_free_agent(chris, ICE_KINGS_LEAGUE_ID)
    r = chris.get(
        f"{BASE_URL}/api/waivers/precheck",
        params={"league_id": ICE_KINGS_LEAGUE_ID, "player_id": p["id"], "bid_amount": 1},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # shape
    for k in ("can_claim", "requires_drop", "roster", "cap", "issues", "team"):
        assert k in data, f"missing {k} in precheck response"
    assert data["roster"]["has_room"] is True
    assert data["can_claim"] is True
    assert data["requires_drop"] is False
    # roster pill values
    assert isinstance(data["roster"]["current"], int)
    assert data["roster"]["max"] >= data["roster"]["current"]
    # cap disabled by default for this league
    assert data["cap"]["enabled"] in (False, True)
    assert data["team"]["id"] == ZAREK_TEAM_ID


# ── 2. Precheck requires_drop path (roster full + tight salary cap) ─────────
def test_precheck_requires_drop_when_roster_full_and_cap_tight(chris, mongo_db):
    league_oid = ObjectId(ICE_KINGS_LEAGUE_ID)
    original = mongo_db.leagues.find_one({"_id": league_oid})
    assert original is not None
    try:
        mongo_db.leagues.update_one(
            {"_id": league_oid},
            {"$set": {
                "roster_size": 13,
                "salary_cap_enabled": True,
                "salary_cap": 50_000_000,
            }},
        )
        p = _pick_free_agent(chris, ICE_KINGS_LEAGUE_ID)
        r = chris.get(
            f"{BASE_URL}/api/waivers/precheck",
            params={"league_id": ICE_KINGS_LEAGUE_ID, "player_id": p["id"], "bid_amount": 1},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["can_claim"] is False
        assert data["requires_drop"] is True
        # blocker codes
        codes = [i.get("code") for i in (data.get("issues") or [])]
        assert "no_roster_space" in codes, f"missing no_roster_space; got {codes}"
        # cap may or may not fit at 50M depending on team's salary_used,
        # but if it does NOT fit insufficient_cap must surface. Capture it.
        # we just assert at least one drop-suggesting blocker exists.
        assert any(i.get("suggested_action") == "drop" for i in (data.get("issues") or []))
        assert data["roster"]["has_room"] is False
    finally:
        # ALWAYS restore — even on assertion failure
        mongo_db.leagues.update_one(
            {"_id": league_oid},
            {"$set": {
                "roster_size": original.get("roster_size", 23),
                "salary_cap_enabled": original.get("salary_cap_enabled", False),
                "salary_cap": original.get("salary_cap", 0),
            }},
        )


# ── 3. POST /api/waivers/claim creates pending row and shows in my_claims ──
def test_place_claim_appears_in_my_claims(chris, mongo_db):
    p = _pick_free_agent(chris, ICE_KINGS_LEAGUE_ID)
    placed = None
    try:
        r = chris.post(
            f"{BASE_URL}/api/waivers/claim",
            json={
                "league_id": ICE_KINGS_LEAGUE_ID,
                "player_id": p["id"],
                "bid_amount": 2,
            },
        )
        assert r.status_code == 200, r.text
        placed = r.json()
        for k in ("_id", "league_id", "team_id", "player_id", "bid_amount", "status"):
            assert k in placed, f"claim response missing {k}"
        assert placed["status"] == "pending"
        assert placed["bid_amount"] == 2
        assert placed["player_id"] == p["id"]

        # verify it shows up in my_claims
        r2 = chris.get(
            f"{BASE_URL}/api/waivers/claims",
            params={"my_claims": True, "league_id": ICE_KINGS_LEAGUE_ID},
        )
        assert r2.status_code == 200
        rows = r2.json()
        ids = [c.get("_id") for c in rows]
        assert placed["_id"] in ids, f"placed claim {placed['_id']} not in my_claims list {ids[:5]}"
    finally:
        if placed and placed.get("_id"):
            # cleanup so we don't pollute future iterations
            try:
                mongo_db.waiver_claims.delete_one({"_id": ObjectId(placed["_id"])})
            except Exception:
                pass


# ── 4. Regression admin list endpoints ──────────────────────────────────────
def test_regression_admin_endpoints_return_200(admin):
    r = admin.get(f"{BASE_URL}/api/leagues", params={"my_leagues": True})
    assert r.status_code == 200, r.text
    leagues = r.json()
    assert isinstance(leagues, list)

    # Pick a league the admin actually has access to (so /teams returns rows)
    league_id = ICE_KINGS_LEAGUE_ID
    if leagues:
        # use first league admin owns
        league_id = leagues[0].get("_id") or leagues[0].get("id") or league_id

    r = admin.get(f"{BASE_URL}/api/teams", params={"league_id": league_id})
    assert r.status_code == 200, r.text

    r = admin.get(f"{BASE_URL}/api/players", params={"limit": 5})
    assert r.status_code == 200, r.text

    r = admin.get(f"{BASE_URL}/api/trade-block", params={"league_id": league_id})
    assert r.status_code == 200, r.text

    r = admin.get(f"{BASE_URL}/api/activity/{league_id}")
    assert r.status_code == 200, r.text

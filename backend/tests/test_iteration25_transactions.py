"""Iteration 25 — League transactions + pending-trades endpoints, comma-separated event_type
filter on /activity, waiver_won activity log + roster $addToSet, enriched roster_add/drop metadata.
"""
import os
import time
import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
CHRIS_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
CHRIS_PASS = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")


# ─── Fixtures ──────────────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def chris_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": CHRIS_EMAIL, "password": CHRIS_PASS})
    assert r.status_code == 200, f"chris login failed: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def ice_kings_id(db):
    league = db.leagues.find_one({"name": {"$regex": "Ice Kings", "$options": "i"}})
    assert league, "Ice Kings league not found"
    return str(league["_id"])


@pytest.fixture(scope="module")
def chris_team(db, ice_kings_id):
    chris = db.users.find_one({"email": CHRIS_EMAIL})
    assert chris
    team = db.teams.find_one({"league_id": ice_kings_id, "owner_id": str(chris["_id"])})
    assert team, "Chris's team in Ice Kings not found"
    return team


# ─── /transactions endpoint ──────────────────────────────────────────
class TestLeagueTransactions:
    def test_transactions_default_limit(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/transactions")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["league_id"] == ice_kings_id
        assert "transactions" in data and isinstance(data["transactions"], list)
        assert data["count"] == len(data["transactions"])
        assert len(data["transactions"]) <= 30

    def test_transactions_only_supported_types(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/transactions?limit=100")
        assert r.status_code == 200
        allowed = {"roster_add", "roster_drop", "waiver_won", "trade_executed", "lineup_change"}
        for tx in r.json()["transactions"]:
            assert tx["type"] in allowed, f"unexpected type {tx['type']}"
            # required keys
            for k in ("id", "type", "description", "team_id", "team_name",
                      "player_id", "player_name", "bid_amount", "created_at"):
                assert k in tx, f"missing key {k}"

    def test_transactions_limit_capped_at_100(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/transactions?limit=500")
        assert r.status_code == 200
        assert len(r.json()["transactions"]) <= 100

    def test_transactions_custom_limit(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/transactions?limit=5")
        assert r.status_code == 200
        assert len(r.json()["transactions"]) <= 5

    def test_transactions_sorted_desc(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/transactions?limit=20")
        items = r.json()["transactions"]
        if len(items) >= 2:
            for a, b in zip(items, items[1:]):
                if a.get("created_at") and b.get("created_at"):
                    assert a["created_at"] >= b["created_at"]


# ─── /pending-trades endpoint ──────────────────────────────────────
class TestPendingTrades:
    def test_pending_trades_shape(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/pending-trades")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["league_id"] == ice_kings_id
        assert isinstance(data["pending_trades"], list)
        assert data["count"] == len(data["pending_trades"])

    def test_pending_trades_status_filter(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/pending-trades")
        # Iter 231h — `proposed` (awaiting recipient response) was added
        # alongside the existing pending/voting/conditional states.
        allowed = {"proposed", "pending", "voting", "conditional"}
        for t in r.json()["pending_trades"]:
            assert t.get("status") in allowed, f"unexpected status {t.get('status')}"

    def test_pending_trades_sorted_by_submitted_desc(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/pending-trades")
        ts = [t.get("submitted_at") for t in r.json()["pending_trades"] if t.get("submitted_at")]
        if len(ts) >= 2:
            for a, b in zip(ts, ts[1:]):
                assert a >= b

    def test_pending_trades_no_objectid_leak(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/leagues/{ice_kings_id}/pending-trades")
        # Response must JSON serialize cleanly (no ObjectId)
        for t in r.json()["pending_trades"]:
            assert isinstance(t.get("_id"), str)


# ─── /activity comma-separated event_type filter ─────────────────
class TestActivityCommaFilter:
    def test_activity_single_type(self, admin_session, ice_kings_id):
        r = admin_session.get(f"{API}/activity/{ice_kings_id}?event_type=roster_add&limit=20")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["event_type"] == "roster_add"

    def test_activity_comma_separated_types(self, admin_session, ice_kings_id):
        r = admin_session.get(
            f"{API}/activity/{ice_kings_id}?event_type=roster_add,roster_drop&limit=50"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for it in data["items"]:
            assert it["event_type"] in ("roster_add", "roster_drop"), \
                f"unexpected {it['event_type']}"

    def test_activity_three_types(self, admin_session, ice_kings_id):
        r = admin_session.get(
            f"{API}/activity/{ice_kings_id}"
            f"?event_type=roster_add,roster_drop,waiver_won&limit=50"
        )
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["event_type"] in ("roster_add", "roster_drop", "waiver_won")


# ─── roster_add / roster_drop metadata enrichment ───────────────
class TestRosterAddDropMetadata:
    def test_roster_add_writes_metadata(self, chris_session, ice_kings_id, chris_team, db):
        # Find a player NOT on the roster
        roster_ids = set(chris_team.get("roster") or [])
        player = db.players.find_one({"_id": {"$nin": [ObjectId(x) for x in roster_ids]}})
        assert player, "No spare player found"
        team_id = str(chris_team["_id"])
        pid = str(player["_id"])

        # Make sure roster has space — if full, drop one first then re-add at end
        league = db.leagues.find_one({"_id": ObjectId(ice_kings_id)})
        max_roster = league.get("roster_spots", 20)
        added_for_room = None
        if len(chris_team.get("roster") or []) >= max_roster:
            victim = (chris_team.get("roster") or [])[0]
            r0 = chris_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": victim})
            assert r0.status_code == 200, r0.text
            added_for_room = victim

        r = chris_session.post(f"{API}/roster/{team_id}/add", json={"player_id": pid})
        if r.status_code == 400 and "already" in r.text.lower():
            # Already on roster — drop & retry
            chris_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": pid})
            r = chris_session.post(f"{API}/roster/{team_id}/add", json={"player_id": pid})
        assert r.status_code == 200, r.text
        time.sleep(0.4)

        # Verify activity feed has metadata
        feed = chris_session.get(
            f"{API}/activity/{ice_kings_id}?event_type=roster_add&limit=10"
        ).json()["items"]
        match = next((it for it in feed
                      if (it.get("metadata") or {}).get("player_id") == pid), None)
        assert match, "roster_add activity not found for new add"
        meta = match["metadata"]
        assert meta.get("team_id") == team_id
        assert meta.get("team_name")
        assert meta.get("player_name")
        assert "position" in meta

        # Cleanup: drop the test player back
        chris_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": pid})
        if added_for_room:
            chris_session.post(f"{API}/roster/{team_id}/add", json={"player_id": added_for_room})

    def test_roster_drop_writes_metadata(self, chris_session, ice_kings_id, chris_team, db):
        # Add a temp player, then drop it and check metadata
        roster_ids = set(chris_team.get("roster") or [])
        player = db.players.find_one({"_id": {"$nin": [ObjectId(x) for x in roster_ids]}})
        assert player
        team_id = str(chris_team["_id"])
        pid = str(player["_id"])

        # Ensure room
        league = db.leagues.find_one({"_id": ObjectId(ice_kings_id)})
        max_roster = league.get("roster_spots", 20)
        team_now = db.teams.find_one({"_id": ObjectId(team_id)})
        added_for_room = None
        if len(team_now.get("roster") or []) >= max_roster:
            victim = (team_now.get("roster") or [])[0]
            chris_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": victim})
            added_for_room = victim

        chris_session.post(f"{API}/roster/{team_id}/add", json={"player_id": pid})
        time.sleep(0.2)
        r = chris_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": pid})
        assert r.status_code == 200, r.text
        time.sleep(0.4)

        feed = chris_session.get(
            f"{API}/activity/{ice_kings_id}?event_type=roster_drop&limit=10"
        ).json()["items"]
        match = next((it for it in feed
                      if (it.get("metadata") or {}).get("player_id") == pid), None)
        assert match, "roster_drop activity not found"
        meta = match["metadata"]
        assert meta.get("team_id") == team_id
        assert meta.get("team_name")
        assert meta.get("player_name")
        if added_for_room:
            chris_session.post(f"{API}/roster/{team_id}/add", json={"player_id": added_for_room})


# ─── waiver_won activity + $addToSet roster ─────────────────────
class TestWaiverWonProcessing:
    def test_waiver_won_logged_and_roster_updated(
        self, admin_session, ice_kings_id, chris_team, db
    ):
        """Create a winning waiver claim, call process_waivers, verify
        (a) team roster contains the player, (b) waiver_won activity row exists with metadata."""
        team_id = str(chris_team["_id"])
        # Find a player NOT on any roster of admin team
        roster_ids = set(chris_team.get("roster") or [])
        player = db.players.find_one({"_id": {"$nin": [ObjectId(x) for x in roster_ids]}})
        assert player
        pid = str(player["_id"])

        # Make sure not already on roster
        await_roster = db.teams.find_one({"_id": ObjectId(team_id)}).get("roster") or []
        added_for_room = None
        league_doc = db.leagues.find_one({"_id": ObjectId(ice_kings_id)})
        max_r = league_doc.get("roster_spots", 20)
        if len(await_roster) >= max_r:
            victim = await_roster[0]
            admin_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": victim})
            added_for_room = victim

        if pid in (db.teams.find_one({"_id": ObjectId(team_id)}).get("roster") or []):
            admin_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": pid})

        # Ensure budget exists
        budget = db.waiver_budgets.find_one({"team_id": team_id, "league_id": ice_kings_id})
        if not budget:
            db.waiver_budgets.insert_one({
                "team_id": team_id, "league_id": ice_kings_id,
                "season": 2025, "spent": 0, "remaining": 100, "total": 100,
            })

        # Insert pending claim directly (no competing claims = guaranteed winner)
        from datetime import datetime, timezone
        claim_doc = {
            "league_id": ice_kings_id,
            "team_id": team_id,
            "team_name": chris_team["name"],
            "player_id": pid,
            "player_name": player["name"],
            "bid_amount": 1,
            "priority": 1,
            "status": "pending",
            "drop_player_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        ins = db.waiver_claims.insert_one(claim_doc)

        try:
            # Call process
            commissioner_login = requests.post(f"{API}/auth/login", json={
                "email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"),
                "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")})
            assert commissioner_login.status_code == 200, commissioner_login.text
            r = requests.post(f"{API}/waivers/process?league_id={ice_kings_id}&force=true",
                headers={"Authorization": f"Bearer {commissioner_login.json()['access_token']}"})
            assert r.status_code == 200, r.text
            time.sleep(0.5)

            # Roster should now contain pid
            team_after = db.teams.find_one({"_id": ObjectId(team_id)})
            assert pid in (team_after.get("roster") or []), \
                "winning waiver player not added to roster via $addToSet"

            # Activity feed should have a waiver_won entry
            feed = admin_session.get(
                f"{API}/activity/{ice_kings_id}?event_type=waiver_won&limit=20"
            ).json()["items"]
            match = next((it for it in feed
                          if (it.get("metadata") or {}).get("player_id") == pid), None)
            assert match, "waiver_won activity not logged"
            meta = match["metadata"]
            assert meta.get("team_id") == team_id
            assert meta.get("team_name")
            assert meta.get("player_name")
            assert meta.get("bid_amount") == 1

            # Same waiver_won should appear in /transactions
            txs = admin_session.get(
                f"{API}/leagues/{ice_kings_id}/transactions?limit=50"
            ).json()["transactions"]
            assert any(
                t["type"] == "waiver_won" and t.get("player_id") == pid for t in txs
            ), "waiver_won not surfaced in /transactions"
        finally:
            # Cleanup: remove the test claim and player off roster
            db.waiver_claims.delete_one({"_id": ins.inserted_id})
            admin_session.post(f"{API}/roster/{team_id}/drop", json={"player_id": pid})
            if added_for_room:
                admin_session.post(f"{API}/roster/{team_id}/add",
                                   json={"player_id": added_for_room})


# ─── 404 / negative ────────────────────────────────────────
class TestNegative:
    def test_transactions_unknown_league_returns_empty(self, admin_session):
        # current implementation queries activity_feed by league_id — unknown ID returns empty list, 200
        r = admin_session.get(f"{API}/leagues/000000000000000000000000/transactions")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_pending_trades_unknown_league_empty(self, admin_session):
        r = admin_session.get(f"{API}/leagues/000000000000000000000000/pending-trades")
        assert r.status_code == 200
        assert r.json()["count"] == 0

"""
Iter 228h — Auto-generate draft_picks on draft create + CSV bulk import +
clock-timezone persistence.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")


def _db_sync():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def _register(prefix="i228h"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _login_admin():
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": "Admin123!"})
    r.raise_for_status()
    return r.json()["access_token"]


def _create_league(tok):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228h-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    r.raise_for_status()
    league = r.json()
    db = _db_sync()
    # Seed 3 extra teams so we have 4 total
    for i in range(3):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"test_owner_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}",
            "name": f"Test Team {chr(65 + i)}",
            "roster": [],
        })
    return league


# ── Tests ────────────────────────────────────────────────────


def test_create_draft_with_immediate_pick_trading_auto_generates_picks():
    """When pick_trading_enabled=true + trading_window_opens='immediately',
    the draft creation auto-materialises rounds × teams draft_picks rows."""
    _, tok = _register("ag")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "TFHL Test Draft",
        "total_rounds": 5, "time_per_pick": 60,
        "pick_trading_enabled": True,
        "trading_window_opens": "immediately",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["picks_generated"] >= 5 * 4, body  # 5 rounds × 4 teams = 20

    # Verify in DB
    db = _db_sync()
    picks = list(db.draft_picks.find({"league_id": league["id"]}))
    assert len(picks) == 5 * 4
    # Each pick should have current_team_id == original_team_id
    for p in picks:
        assert p["current_team_id"] == p["original_team_id"]
        assert p["tradeable"] is True
        assert 1 <= p["round"] <= 5


def test_create_draft_without_trading_does_not_generate_picks():
    """Default (pick_trading_enabled=false) does NOT auto-generate picks."""
    _, tok = _register("ng")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "No-trade draft",
        "total_rounds": 3, "time_per_pick": 60,
    })
    assert r.status_code == 200, r.text
    assert r.json().get("picks_generated", 0) == 0

    db = _db_sync()
    picks = list(db.draft_picks.find({"league_id": league["id"]}))
    assert len(picks) == 0


def test_create_draft_persists_clock_timezone():
    """clock_timezone + clock_starts_at + clock_stops_at persist on the doc."""
    _, tok = _register("tz")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "TZ test",
        "total_rounds": 3, "time_per_pick": 60,
        "clock_timezone": "America/New_York",
        "clock_starts_at": "09:00",
        "clock_stops_at": "23:00",
    })
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["clock_timezone"] == "America/New_York"
    assert b["clock_starts_at"] == "09:00"
    assert b["clock_stops_at"] == "23:00"


def test_admin_bulk_csv_import_inserts_rows_and_skips_duplicates():
    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}
    name1 = f"Bulk-{uuid.uuid4().hex[:6]} Tester"
    name2 = f"Bulk-{uuid.uuid4().hex[:6]} Two"
    rows = [
        {"name": name1, "position": "C", "team": "TOR", "league_status": "AHL"},
        {"name": name2, "position": "RW", "team": "NYR", "league_status": "Junior",
         "date_of_birth": "2007-04-12"},
        {"name": name1, "position": "C", "team": "TOR", "league_status": "AHL"},
    ]
    r = requests.post(f"{API_URL}/api/admin/players/bulk-import", headers=Ha,
                      json={"rows": rows, "skip_duplicates": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 2
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["name"] == name1

    db = _db_sync()
    assert db.players.find_one({"name": name1, "source": "admin_bulk_csv"})
    assert db.players.find_one({"name": name2, "source": "admin_bulk_csv"})


def test_admin_bulk_csv_import_requires_admin():
    _, tok = _register("bk")
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/admin/players/bulk-import", headers=H, json={
        "rows": [{"name": "X", "position": "C"}], "skip_duplicates": True,
    })
    assert r.status_code == 403


def test_create_draft_rejects_rounds_above_roster_capacity():
    """Confirms the iter228d roster-cap validation still enforced."""
    _, tok = _register("rc")
    league = _create_league(tok)
    db = _db_sync()
    # Set roster shape: 10+4+0 = 14, so max should be max(14, 30) = 30
    db.leagues.update_one(
        {"_id": ObjectId(league["id"])},
        {"$set": {"roster_spots": 10, "bench_spots": 4, "minors_spots": 0}},
    )
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Too big",
        "total_rounds": 55, "time_per_pick": 60,
    })
    assert r.status_code == 422, r.text


def test_create_draft_allows_rounds_up_to_roster_capacity():
    """19+6+30=55 dynasty league can run 55 rounds."""
    _, tok = _register("ok")
    league = _create_league(tok)
    db = _db_sync()
    db.leagues.update_one(
        {"_id": ObjectId(league["id"])},
        {"$set": {"roster_spots": 19, "bench_spots": 6, "minors_spots": 30}},
    )
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Full dynasty draft",
        "total_rounds": 55, "time_per_pick": 60,
    })
    assert r.status_code == 200, r.text
    assert r.json()["total_rounds"] == 55

"""
Iter 228i — Pick-seed retroactive endpoint + roster-shape propagate +
DraftRoom crash regression.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def _register(prefix="i228i"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _create_league(tok, seed_extra=3):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228i-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    r.raise_for_status()
    league = r.json()
    db = _db()
    for i in range(seed_extra):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"owner_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}", "name": f"Team {chr(65 + i)}",
            "roster": [],
        })
    return league


def test_seed_picks_endpoint_backfills_existing_draft():
    """Drafts created before iter228h didn't auto-gen picks. The new
    seed-picks endpoint backfills them idempotently."""
    _, tok = _register()
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    # Create a draft WITHOUT trading enabled first → no auto-gen
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Legacy Draft",
        "total_rounds": 3, "time_per_pick": 60,
    })
    assert r.status_code == 200
    draft_id = r.json()["_id"]
    db = _db()
    assert db.draft_picks.count_documents({"league_id": league["id"]}) == 0

    # Backfill
    r2 = requests.post(f"{API_URL}/api/drafts/{draft_id}/seed-picks", headers=H)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["picks_inserted"] == 3 * 4  # 3 rounds × 4 teams

    # Idempotent re-run
    r3 = requests.post(f"{API_URL}/api/drafts/{draft_id}/seed-picks", headers=H)
    assert r3.status_code == 200
    assert r3.json()["picks_inserted"] == 0


def test_seed_picks_requires_commissioner():
    _, tok_a = _register("a")
    league = _create_league(tok_a)
    Ha = {"Authorization": f"Bearer {tok_a}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=Ha, json={
        "league_id": league["id"], "name": "Drft", "total_rounds": 3,
        "time_per_pick": 60,
    })
    draft_id = r.json()["_id"]

    _, tok_b = _register("b")
    Hb = {"Authorization": f"Bearer {tok_b}"}
    r2 = requests.post(f"{API_URL}/api/drafts/{draft_id}/seed-picks", headers=Hb)
    assert r2.status_code == 403


def test_propagate_roster_shape_trims_overflow():
    """When league roster shape shrinks, all teams' rosters are trimmed
    to the new cap."""
    _, tok = _register()
    league = _create_league(tok, seed_extra=2)
    db = _db()

    # Set roster shape to small + overload one team
    db.leagues.update_one({"_id": ObjectId(league["id"])}, {"$set": {
        "roster_spots": 3, "bench_spots": 1, "minors_spots": 0,
    }})
    overload_team = db.teams.find_one({"league_id": league["id"]})
    db.teams.update_one(
        {"_id": overload_team["_id"]},
        {"$set": {"roster": [f"pid_{i}" for i in range(10)]}},
    )

    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(
        f"{API_URL}/api/leagues/{league['id']}/propagate-roster-shape",
        headers=H,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cap"] == 4  # 3 + 1 + 0
    assert body["teams_trimmed"] == 1
    assert body["teams_updated"] == 3

    # Overload team now has exactly 4 players
    after = db.teams.find_one({"_id": overload_team["_id"]})
    assert len(after["roster"]) == 4
    assert after["roster_max"] == 4
    assert after["active_max"] == 3
    assert after["bench_max"] == 1


def test_propagate_roster_shape_requires_commissioner():
    _, tok_a = _register("propA")
    league = _create_league(tok_a)
    _, tok_b = _register("propB")
    Hb = {"Authorization": f"Bearer {tok_b}"}
    r = requests.post(
        f"{API_URL}/api/leagues/{league['id']}/propagate-roster-shape",
        headers=Hb,
    )
    assert r.status_code == 403

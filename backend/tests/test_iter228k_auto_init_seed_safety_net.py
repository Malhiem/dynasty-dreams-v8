"""
Iter 228k — auto-init Draft Room safety net.

Verifies:
  - POST /api/drafts/auto-init/{league_id} on a NEW league derives
    `total_rounds` from `roster_spots + bench_spots + minors_spots`
    instead of the legacy default of 5, and auto-seeds draft_picks.
  - On a pre-existing draft (created with the legacy default of 5)
    whose picks haven't been seeded yet, the endpoint heals the
    `total_rounds` to the roster cap AND seeds the missing picks.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def _register(prefix="i228k"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _create_league(tok, roster_spots=18, bench_spots=8, minors_spots=4, max_teams=4):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228k-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": max_teams,
        "draft_type": "snake", "roster_spots": roster_spots,
        "bench_spots": bench_spots, "minors_spots": minors_spots,
    })
    r.raise_for_status()
    league = r.json()
    db = _db()
    # POST /api/leagues only persists roster_spots — write bench/minors
    # directly so the auto-init cap derivation has full inputs.
    db.leagues.update_one(
        {"_id": ObjectId(league["id"])},
        {"$set": {"bench_spots": bench_spots, "minors_spots": minors_spots}},
    )
    # Seed extra teams so picks generation has multiple slots
    for i in range(max_teams - 1):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"owner_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}", "name": f"Team {chr(65 + i)}",
            "roster": [],
        })
    return league


def test_auto_init_derives_total_rounds_from_roster_cap_and_seeds():
    """Fresh auto-init computes total_rounds = active + bench + minors
    and immediately materialises draft_picks rows."""
    _, tok = _register("fresh")
    league = _create_league(tok, roster_spots=18, bench_spots=8, minors_spots=4, max_teams=4)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.post(f"{API_URL}/api/drafts/auto-init/{league['id']}?commit=true", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["draft"]["total_rounds"] == 30  # 18 + 8 + 4

    # draft_picks rows materialised
    db = _db()
    n = db.draft_picks.count_documents({"league_id": league["id"]})
    assert n == 30 * 4, f"expected 120 seeded picks, got {n}"


def test_auto_init_heals_legacy_total_rounds_and_seeds_existing():
    """A legacy draft created with total_rounds=5 + no picks gets healed
    to the league's full roster cap, and the safety net seeds picks."""
    _, tok = _register("legacy")
    league = _create_league(tok, roster_spots=15, bench_spots=10, minors_spots=5, max_teams=4)

    # Manually insert a legacy draft document (mimics pre-iter228k auto-init)
    db = _db()
    draft_id = db.drafts.insert_one({
        "league_id": league["id"],
        "league_name": league["name"],
        "draft_type": "snake",
        "total_rounds": 5,  # legacy default
        "time_per_pick": 120,
        "snake_draft": True,
        "missed_pick_action": "skip",
        "current_pick": 1,
        "status": "scheduled",
        "draft_started": False,
        "picks": [],
        "team_abbrs": [],
        "team_map": {},
        "chat_messages": [],
        "created_at": "2026-01-01T00:00:00+00:00",
    }).inserted_id

    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts/auto-init/{league['id']}", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is False
    # Healed to roster cap = 30
    assert body["draft"]["total_rounds"] == 30, body["draft"]

    healed = db.drafts.find_one({"_id": draft_id})
    assert healed["total_rounds"] == 30

    # Picks were seeded transparently
    n = db.draft_picks.count_documents({"league_id": league["id"]})
    assert n == 30 * 4


def test_auto_init_does_not_heal_in_progress_draft():
    """A draft with status='active' or with picks already made must NOT
    have its total_rounds rewritten — protects mid-draft integrity."""
    _, tok = _register("inprog")
    league = _create_league(tok, roster_spots=15, bench_spots=10, minors_spots=5, max_teams=4)

    db = _db()
    draft_id = db.drafts.insert_one({
        "league_id": league["id"],
        "league_name": league["name"],
        "draft_type": "snake",
        "total_rounds": 5,
        "time_per_pick": 120,
        "snake_draft": True,
        "missed_pick_action": "skip",
        "current_pick": 2,
        "status": "active",        # active → must be preserved
        "draft_started": True,
        "picks": [{"overall": 1, "team": "TMA", "player": {"id": "p1"}}],
        "team_abbrs": [],
        "team_map": {},
        "chat_messages": [],
        "created_at": "2026-01-01T00:00:00+00:00",
    }).inserted_id

    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts/auto-init/{league['id']}", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["draft"]["total_rounds"] == 5  # untouched

    untouched = db.drafts.find_one({"_id": draft_id})
    assert untouched["total_rounds"] == 5

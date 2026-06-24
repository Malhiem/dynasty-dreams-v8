"""
Iter 228p — PATCH /api/drafts/{id} syncs `draft_picks` collection when
`total_rounds` changes. Root cause of the user-reported bug:
"editing # of picks adjusts the draft board but the picks don't reduce
on roster."
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def _register(prefix="i228p"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _setup_league_with_seeded_draft(rounds=3):
    """Create a league + a draft with `pick_trading_enabled` so the
    `draft_picks` collection is seeded automatically on draft create."""
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228p-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()

    # Seed 3 extra teams so we have 4 teams total (auto-created commish team + 3)
    db = _db()
    for i in range(3):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"owner_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}", "name": f"Team {chr(65 + i)}",
            "roster": [],
        })

    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Sync Test",
        "total_rounds": rounds, "time_per_pick": 60,
        "pick_trading_enabled": True, "trading_window_opens": "immediately",
    })
    r2.raise_for_status()
    draft_id = r2.json()["_id"]
    return tok, league["id"], draft_id


def test_patch_total_rounds_grows_picks_collection():
    """Editing rounds 3 → 7 should INSERT 4 more rounds of picks."""
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=3)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    before = db.draft_picks.count_documents({"draft_id": draft_id})
    # 3 rounds × 4 teams = 12 picks
    assert before == 12, before

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "total_rounds": 7,
    })
    assert r.status_code == 200, r.text

    after = db.draft_picks.count_documents({"draft_id": draft_id})
    # 7 rounds × 4 teams = 28 picks
    assert after == 28, after


def test_patch_total_rounds_shrinks_picks_collection():
    """Editing rounds 5 → 2 should DELETE the rows for rounds 3-5."""
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=5)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    before = db.draft_picks.count_documents({"draft_id": draft_id})
    assert before == 20, before   # 5 × 4

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "total_rounds": 2,
    })
    assert r.status_code == 200, r.text

    after = db.draft_picks.count_documents({"draft_id": draft_id})
    # 2 × 4 = 8 picks remain
    assert after == 8, after
    # And no rows survive for rounds 3-5
    leftover = db.draft_picks.count_documents({
        "draft_id": draft_id, "round": {"$gt": 2},
    })
    assert leftover == 0


def test_patch_shrink_preserves_traded_picks():
    """Traded picks (with trade_history) must NOT be deleted during a
    shrink — preserves integrity for completed pick trades."""
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=5)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    # Mark one round-4 pick as traded
    sample = db.draft_picks.find_one({"draft_id": draft_id, "round": 4})
    db.draft_picks.update_one(
        {"_id": sample["_id"]},
        {"$set": {"trade_history": [{
            "trade_id": "fake", "to_team_id": "X", "from_team_id": "Y",
        }]}},
    )

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "total_rounds": 2,
    })
    assert r.status_code == 200, r.text

    # The traded pick survives even though its round > 2
    survivor = db.draft_picks.find_one({"_id": sample["_id"]})
    assert survivor is not None
    assert survivor["round"] == 4


def test_patch_total_rounds_unchanged_does_not_touch_picks():
    """PATCH with the SAME total_rounds shouldn't churn picks."""
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=3)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    before = db.draft_picks.count_documents({"draft_id": draft_id})
    before_ids = sorted(str(p["_id"]) for p in db.draft_picks.find({"draft_id": draft_id}))

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "total_rounds": 3,  # unchanged
    })
    assert r.status_code == 200, r.text

    after = db.draft_picks.count_documents({"draft_id": draft_id})
    after_ids = sorted(str(p["_id"]) for p in db.draft_picks.find({"draft_id": draft_id}))
    assert after == before
    assert after_ids == before_ids


def test_patch_round_time_overrides_via_ranges_array():
    """PATCH with structured ranges array round-trips cleanly."""
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=10)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "round_time_overrides": [
            {"from": 1, "to": 5, "seconds": 3600},
            {"from": 6, "to": 10, "seconds": 300},
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()["draft"]
    assert d["round_time_overrides"] == [
        {"from": 1, "to": 5, "seconds": 3600},
        {"from": 6, "to": 10, "seconds": 300},
    ]

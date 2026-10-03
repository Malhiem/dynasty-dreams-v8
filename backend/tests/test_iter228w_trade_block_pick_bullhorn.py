"""
Iter 228w — Trade Block bullhorn for Roster Draft Picks.

The frontend adds picks via `POST /api/trade-block` with `item_type=pick`.
Verifies the existing endpoint accepts the payload shape the new
bullhorn UI sends + the resulting trade-block row carries the correct
metadata for the public Trade Block listing.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def _register(prefix="i228w"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _seed_league_with_picks():
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228w-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()
    db = _db()
    for i in range(3):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"o_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}", "name": f"T{chr(65 + i)}",
            "roster": [],
        })
    rr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Block UX Draft",
        "total_rounds": 3, "time_per_pick": 60,
        "pick_trading_enabled": True, "trading_window_opens": "immediately",
    })
    rr.raise_for_status()
    team = db.teams.find_one({"league_id": league["id"], "owner_id": {"$ne": None},
                              "name": {"$exists": True}, "owner_name": {"$exists": False}})
    # The auto-created commissioner team
    if not team:
        team = db.teams.find_one({"league_id": league["id"]})
    return tok, league["id"], str(team["_id"])


def test_post_trade_block_with_pick_id_succeeds():
    """Bullhorn UI fires POST /trade-block with item_type=pick + pick_id
    + team_id. Verify the row materialises with the expected metadata."""
    tok, league_id, team_id = _seed_league_with_picks()
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()
    # Grab any owned pick id
    pick = db.draft_picks.find_one({"current_team_id": team_id})
    assert pick, "Expected at least one owned pick to exist"

    r = requests.post(f"{API_URL}/api/trade-block", headers=H, json={
        "item_type": "pick",
        "team_id": team_id,
        "pick_id": str(pick["_id"]),
        "looking_for": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("item_type") == "pick" or body.get("id"), body

    rows = list(db.trade_block.find({"team_id": team_id, "item_type": "pick"}))
    assert any(str(x.get("pick_id")) == str(pick["_id"]) for x in rows), \
        f"Expected trade_block row with pick_id={pick['_id']}, got {rows}"


def test_post_trade_block_with_year_round_succeeds():
    """Fallback path when frontend doesn't have a pick ObjectId on hand
    (legacy/non-seeded picks). UI passes pick_year + pick_round only."""
    tok, league_id, team_id = _seed_league_with_picks()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/trade-block", headers=H, json={
        "item_type": "pick",
        "team_id": team_id,
        "pick_year": 2026,
        "pick_round": "2",
        "looking_for": [],
    })
    assert r.status_code == 200, r.text
    db = _db()
    row = db.trade_block.find_one({
        "team_id": team_id, "item_type": "pick",
        "pick_year": 2026, "pick_round": "2",
    })
    assert row is not None


def test_post_trade_block_dedups_same_pick():
    """Adding the same pick twice shouldn't create two trade_block rows."""
    tok, league_id, team_id = _seed_league_with_picks()
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()
    pick = db.draft_picks.find_one({"current_team_id": team_id})

    requests.post(f"{API_URL}/api/trade-block", headers=H, json={
        "item_type": "pick", "team_id": team_id,
        "pick_id": str(pick["_id"]),
    })
    requests.post(f"{API_URL}/api/trade-block", headers=H, json={
        "item_type": "pick", "team_id": team_id,
        "pick_id": str(pick["_id"]),
    })
    count = db.trade_block.count_documents({
        "team_id": team_id, "item_type": "pick", "pick_id": str(pick["_id"]),
    })
    assert count == 1, count

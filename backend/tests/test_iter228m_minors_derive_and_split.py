"""
Iter 228m — Minors section auto-derive + split skater/goalie sub-pools.

Verifies:
  - PUT /api/leagues/{id} with `position_breakdown.minors = {S: 30}` and
    NO explicit `minors_spots` derives the section total from the
    row sum (mirrors the Active row behaviour shipped in iter 176).
  - Same auto-derive works for `position_breakdown.bench`.
  - When the commissioner sends both row + explicit total, the explicit
    value wins (manual override).
  - `minors_split_enabled`, `minors_skater_spots`, `minors_goalie_spots`
    persist and surface in `LeagueResponse`.
  - The new "P" (Prospect) column under the Minors row counts toward
    the auto-derived total.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def _register(prefix="i228m"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _create_league(tok, roster_spots=19):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228m-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": roster_spots,
    })
    r.raise_for_status()
    return r.json()


def test_minors_total_auto_derived_from_position_breakdown_row():
    """The TFHL bug: position_breakdown.minors.S=30 but minors_spots=0 →
    Roster page shows 0/0 instead of 30. Fix: auto-derive section total."""
    _, tok = _register("minors")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.put(f"{API_URL}/api/leagues/{league['id']}", headers=H, json={
        "position_breakdown": {
            "active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1},
            "bench": {"S": 6},
            "minors": {"S": 30},
        },
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # Both bench_spots and minors_spots should be derived
    assert body["minors_spots"] == 30, body
    assert body["bench_spots"] == 6, body
    # Diff exposes the derived flag
    changes = body.get("changes") or {}
    assert changes.get("minors_spots", {}).get("derived") is True
    assert changes.get("bench_spots", {}).get("derived") is True


def test_explicit_minors_spots_wins_over_derived_sum():
    """Commissioner who sends BOTH a row AND an explicit total keeps
    the explicit value (derived only fires when total is absent)."""
    _, tok = _register("explicit")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.put(f"{API_URL}/api/leagues/{league['id']}", headers=H, json={
        "minors_spots": 40,  # explicit, larger than row sum
        "position_breakdown": {
            "active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1},
            "minors": {"S": 30},  # row sums to 30
        },
    })
    assert r.status_code == 200, r.text
    assert r.json()["minors_spots"] == 40  # explicit wins


def test_p_column_counts_toward_derived_minors_total():
    """The new "P" (Prospect) column under Minors counts the same as
    any other position cell when deriving the section total."""
    _, tok = _register("pcol")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.put(f"{API_URL}/api/leagues/{league['id']}", headers=H, json={
        "position_breakdown": {
            "active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1},
            "minors": {"P": 30},  # all 30 slots are position-agnostic
        },
    })
    assert r.status_code == 200, r.text
    assert r.json()["minors_spots"] == 30


def test_minors_split_fields_persist():
    """New fields round-trip cleanly through LeagueResponse."""
    _, tok = _register("split")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.put(f"{API_URL}/api/leagues/{league['id']}", headers=H, json={
        "minors_split_enabled": True,
        "minors_skater_spots": 25,
        "minors_goalie_spots": 5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["minors_split_enabled"] is True
    assert body["minors_skater_spots"] == 25
    assert body["minors_goalie_spots"] == 5

    # Round-trip via GET
    r2 = requests.get(f"{API_URL}/api/leagues/{league['id']}", headers=H)
    assert r2.status_code == 200
    g = r2.json()
    assert g["minors_split_enabled"] is True
    assert g["minors_skater_spots"] == 25
    assert g["minors_goalie_spots"] == 5


def test_auto_derive_does_not_fire_when_row_is_untouched():
    """If the payload doesn't include position_breakdown.minors, the
    existing minors_spots stays put — no silent overwrites."""
    _, tok = _register("untouch")
    league = _create_league(tok)
    db = _db()
    db.leagues.update_one(
        {"_id": ObjectId(league["id"])},
        {"$set": {"minors_spots": 15}},
    )
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.put(f"{API_URL}/api/leagues/{league['id']}", headers=H, json={
        # Only updates active row — minors should be left alone
        "position_breakdown": {
            "active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1},
        },
    })
    assert r.status_code == 200, r.text
    # Reload the league document
    fresh = db.leagues.find_one({"_id": ObjectId(league["id"])})
    assert fresh["minors_spots"] == 15

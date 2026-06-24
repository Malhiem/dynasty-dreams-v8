"""
Iter 228q —
  - GET /api/drafts/{id}/edit-preview computes the "what if I change
    rounds?" diff for the Edit Draft dialog banner.
  - PATCH /api/drafts/{id} now ALSO broadcasts `draft_edited` to the
    `league_{league_id}` socket room so the Rosters page (which
    doesn't know the active draft_id) refreshes live.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def _register(prefix="i228q"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _setup_league_with_seeded_draft(rounds=5, n_teams=4):
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228q-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": n_teams,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()
    db = _db()
    for i in range(n_teams - 1):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"o_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}", "name": f"T{chr(65 + i)}",
            "roster": [],
        })
    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Preview Test",
        "total_rounds": rounds, "time_per_pick": 60,
        "pick_trading_enabled": True, "trading_window_opens": "immediately",
    })
    r2.raise_for_status()
    return tok, league["id"], r2.json()["_id"]


def test_edit_preview_grow_returns_picks_added_per_team_and_total():
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=5, n_teams=4)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(
        f"{API_URL}/api/drafts/{draft_id}/edit-preview?total_rounds=8",
        headers=H,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["team_count"] == 4
    assert body["original_rounds"] == 5
    assert body["new_rounds"] == 8
    assert body["picks_added_per_team"] == 3
    assert body["picks_added"] == 12  # 3 * 4 teams
    assert body["picks_removed"] == 0
    assert body["traded_picks_preserved"] == 0


def test_edit_preview_shrink_returns_picks_removed_and_traded_preserved():
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=5, n_teams=4)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    # Mark one round-4 pick as traded so the preview reports it as preserved
    sample = db.draft_picks.find_one({"draft_id": draft_id, "round": 4})
    db.draft_picks.update_one(
        {"_id": sample["_id"]},
        {"$set": {"trade_history": [{"trade_id": "x"}]}},
    )

    r = requests.get(
        f"{API_URL}/api/drafts/{draft_id}/edit-preview?total_rounds=2",
        headers=H,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["picks_removed_per_team"] == 3
    assert body["picks_removed"] == 12  # 3 * 4 teams
    assert body["picks_added"] == 0
    assert body["traded_picks_preserved"] == 1


def test_edit_preview_no_change():
    """When new_rounds == original_rounds, diff fields are all zero."""
    tok, _, draft_id = _setup_league_with_seeded_draft(rounds=5, n_teams=4)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(
        f"{API_URL}/api/drafts/{draft_id}/edit-preview?total_rounds=5",
        headers=H,
    )
    body = r.json()
    assert body["picks_added"] == 0
    assert body["picks_removed"] == 0
    assert body["traded_picks_preserved"] == 0


def test_edit_preview_404_for_unknown_draft():
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    fake_oid = "0" * 24
    r = requests.get(
        f"{API_URL}/api/drafts/{fake_oid}/edit-preview?total_rounds=5",
        headers=H,
    )
    assert r.status_code == 404


def test_patch_still_persists_rounds_after_iter228q():
    """Sanity regression — the iter228p sync behaviour still works
    alongside the new league-channel broadcast in iter228q."""
    tok, league_id, draft_id = _setup_league_with_seeded_draft(rounds=3, n_teams=4)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "total_rounds": 7,
    })
    assert r.status_code == 200, r.text
    assert r.json()["draft"]["total_rounds"] == 7
    assert db.draft_picks.count_documents({"draft_id": draft_id}) == 7 * 4

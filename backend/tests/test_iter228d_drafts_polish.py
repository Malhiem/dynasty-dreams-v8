"""
Iter 228d — Draft creation polish + archive endpoints.

Covers:
  • POST /api/drafts persists `name` (was being dropped → "Untitled Draft")
  • POST /api/drafts persists `scheduled_time` ISO
  • POST /api/drafts persists `round_time_overrides`, `window_elapsed_actions`,
    and `missed_pick_action="defer-to-user"`
  • POST /api/drafts allows `total_rounds` up to roster capacity
    (active + bench + minors)
  • DELETE /api/drafts/{id} → soft-archives a scheduled draft
  • POST /api/drafts/{id}/restore → unarchives an archived draft
  • GET /api/drafts?include_archived=false hides archived rows by default
"""
import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _register(prefix="iter228d"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    r = requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    })
    r.raise_for_status()
    r2 = requests.post(f"{API_URL}/api/auth/login", json={"email": e, "password": "Pass123!"})
    r2.raise_for_status()
    return e, r2.json()["access_token"]


def _create_league(tok, *, roster_spots=19, bench_spots=6, minors_spots=30):
    """Creates a league via API then patches bench/minors_spots directly
    in mongo since the create endpoint only accepts roster_spots."""
    from pymongo import MongoClient
    from bson import ObjectId
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"iter228d-{uuid.uuid4().hex[:6]}",
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 4, "draft_type": "snake",
        "roster_spots": roster_spots,
    })
    r.raise_for_status()
    league = r.json()
    db.leagues.update_one(
        {"_id": ObjectId(league["id"])},
        {"$set": {
            "bench_spots": bench_spots,
            "minors_spots": minors_spots,
            "roster_spots": roster_spots,
        }},
    )
    return league


def test_post_drafts_persists_name_and_scheduled_time():
    _, tok = _register("dn")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"],
        "name": "TFHL Inaugural Draft",
        "draft_type": "entry",
        "scheduled_time": "2026-09-01T19:00:00+00:00",
        "total_rounds": 5,
        "time_per_pick": 3600,
        "snake_draft": True,
        "player_criteria": ["all"],
        "missed_pick_action": "auto-select",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "TFHL Inaugural Draft"
    assert body["scheduled_time"] == "2026-09-01T19:00:00+00:00"
    assert body["total_rounds"] == 5
    assert body["time_per_pick"] == 3600


def test_post_drafts_persists_new_optional_fields():
    _, tok = _register("dn2")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    overrides = [
        {"from": 1, "to": 5, "seconds": 7200},
        {"from": 6, "to": 30, "seconds": 3600},
    ]
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"],
        "name": "Round-tiered draft",
        "total_rounds": 30,
        "time_per_pick": 3600,
        "round_time_overrides": overrides,
        "missed_pick_action": "defer-to-user",
        "window_elapsed_actions": ["require_admin", "majority_vote"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_time_overrides"] == overrides
    assert body["missed_pick_action"] == "defer-to-user"
    assert body["window_elapsed_actions"] == ["require_admin", "majority_vote"]


def test_post_drafts_allows_rounds_up_to_roster_capacity():
    """A dynasty league with 19+6+30=55 roster spots can run 55 rounds."""
    _, tok = _register("dn3")
    league = _create_league(tok, roster_spots=19, bench_spots=6, minors_spots=30)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"],
        "name": "Big draft",
        "total_rounds": 55,
        "time_per_pick": 60,
    })
    assert r.status_code == 200, r.text
    assert r.json()["total_rounds"] == 55


def test_post_drafts_rejects_rounds_above_roster_capacity():
    """A small league (roster=20 total) can't have 60 rounds."""
    _, tok = _register("dn4")
    league = _create_league(tok, roster_spots=10, bench_spots=4, minors_spots=0)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"],
        "name": "Too many",
        "total_rounds": 60,
    })
    # Soft cap is `max(roster_cap, 30) = 30` for this league, so 60 rejected
    assert r.status_code == 422, r.text


def test_delete_and_restore_draft_lifecycle():
    """DELETE archives, GET hides by default, restore returns to scheduled."""
    _, tok = _register("dn5")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Draft to archive",
        "total_rounds": 5, "time_per_pick": 60,
    })
    assert r.status_code == 200
    draft_id = r.json()["_id"]

    # Listed by default
    r2 = requests.get(f"{API_URL}/api/drafts", headers=H, params={"league_id": league["id"]})
    assert r2.status_code == 200
    assert any(d["_id"] == draft_id for d in r2.json())

    # Archive
    r3 = requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=H)
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "archived"
    assert "archived_at" in r3.json()

    # Hidden from default listing
    r4 = requests.get(f"{API_URL}/api/drafts", headers=H, params={"league_id": league["id"]})
    assert not any(d["_id"] == draft_id for d in r4.json()), \
        "archived draft should be hidden by default"

    # Visible with include_archived=true
    r5 = requests.get(f"{API_URL}/api/drafts", headers=H, params={
        "league_id": league["id"], "include_archived": "true",
    })
    archived_row = next((d for d in r5.json() if d["_id"] == draft_id), None)
    assert archived_row is not None, "archived draft should appear with include_archived"
    assert archived_row["status"] == "archived"

    # Restore
    r6 = requests.post(f"{API_URL}/api/drafts/{draft_id}/restore", headers=H)
    assert r6.status_code == 200
    assert r6.json()["status"] == "scheduled"

    # Now visible in default listing again
    r7 = requests.get(f"{API_URL}/api/drafts", headers=H, params={"league_id": league["id"]})
    assert any(d["_id"] == draft_id for d in r7.json())


def test_delete_draft_requires_commissioner():
    """A non-commissioner cannot archive someone else's draft."""
    _, tok_a = _register("dnA")
    league = _create_league(tok_a)
    Ha = {"Authorization": f"Bearer {tok_a}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=Ha, json={
        "league_id": league["id"], "name": "Mine", "total_rounds": 5, "time_per_pick": 60,
    })
    draft_id = r.json()["_id"]

    _, tok_b = _register("dnB")
    Hb = {"Authorization": f"Bearer {tok_b}"}
    r2 = requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=Hb)
    assert r2.status_code == 403, r2.text


def test_delete_draft_rejects_in_progress_draft():
    """In-progress drafts cannot be archived directly — must be ended first."""
    from pymongo import MongoClient
    from bson import ObjectId
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]

    _, tok = _register("dnIp")
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Hot draft", "total_rounds": 5, "time_per_pick": 60,
    })
    draft_id = r.json()["_id"]

    # Force the status to in_progress in the DB
    db.drafts.update_one({"_id": ObjectId(draft_id)},
                         {"$set": {"status": "in_progress"}})

    r2 = requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=H)
    assert r2.status_code == 400, r2.text
    assert "in_progress" in r2.json()["detail"]

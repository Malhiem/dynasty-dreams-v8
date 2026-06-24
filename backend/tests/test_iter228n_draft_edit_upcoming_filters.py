"""
Iter 228n — Draft polish pass:
  - PATCH /api/drafts/{id} for editing scheduled drafts
  - GET /api/leagues/{id}/upcoming-drafts?days=30
  - Eligibility filters: exclude_previously_drafted + minors_eligibility_required
"""
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def _register(prefix="i228n"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _create_league(tok):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228n-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    return r.json()


def _create_draft(tok, league_id, name="Edit Test", scheduled_iso=None, **kwargs):
    H = {"Authorization": f"Bearer {tok}"}
    body = {
        "league_id": league_id, "name": name,
        "total_rounds": 3, "time_per_pick": 60,
        "scheduled_time": scheduled_iso,
        **kwargs,
    }
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json=body)
    r.raise_for_status()
    return r.json()


# ── PATCH /drafts/{id} ────────────────────────────────────────────────

def test_patch_draft_edits_scheduled_draft():
    _, tok = _register("patch")
    lg = _create_league(tok)
    d = _create_draft(tok, lg["id"], name="Original Name")
    draft_id = d["_id"]
    H = {"Authorization": f"Bearer {tok}"}

    new_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "name": "Corrected Name",
        "scheduled_time": new_time,
        "total_rounds": 5,
        "time_per_pick": 180,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["updated_fields"]) >= {"name", "scheduled_time", "total_rounds", "time_per_pick"}
    assert body["draft"]["name"] == "Corrected Name"
    assert body["draft"]["total_rounds"] == 5
    assert body["draft"]["time_per_pick"] == 180


def test_patch_draft_rejects_invalid_ranges():
    _, tok = _register("range")
    lg = _create_league(tok)
    d = _create_draft(tok, lg["id"])
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.patch(f"{API_URL}/api/drafts/{d['_id']}", headers=H, json={
        "total_rounds": 150,
    })
    assert r.status_code == 400
    assert "total_rounds" in r.text


def test_patch_draft_blocks_non_scheduled_drafts():
    _, tok = _register("locked")
    lg = _create_league(tok)
    d = _create_draft(tok, lg["id"])
    db = _db()
    db.drafts.update_one(
        {"_id": ObjectId(d["_id"])}, {"$set": {"status": "active"}},
    )
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.patch(f"{API_URL}/api/drafts/{d['_id']}", headers=H, json={"name": "Nope"})
    assert r.status_code == 400


def test_patch_draft_requires_commissioner():
    _, tok_comm = _register("comm")
    lg = _create_league(tok_comm)
    d = _create_draft(tok_comm, lg["id"])

    _, tok_other = _register("other")
    H = {"Authorization": f"Bearer {tok_other}"}
    r = requests.patch(f"{API_URL}/api/drafts/{d['_id']}", headers=H, json={"name": "Hack"})
    assert r.status_code == 403


# ── GET /leagues/{id}/upcoming-drafts ─────────────────────────────────

def test_upcoming_drafts_returns_sorted_by_scheduled_time():
    _, tok = _register("upcoming")
    lg = _create_league(tok)
    now = datetime.now(timezone.utc)
    # Three scheduled drafts: in 3 days, 10 days, 25 days
    d1 = _create_draft(tok, lg["id"], name="Soonest", scheduled_iso=(now + timedelta(days=3)).isoformat())
    d2 = _create_draft(tok, lg["id"], name="Middle", scheduled_iso=(now + timedelta(days=10)).isoformat())
    d3 = _create_draft(tok, lg["id"], name="Last", scheduled_iso=(now + timedelta(days=25)).isoformat())
    # One outside the window (40 days out)
    _create_draft(tok, lg["id"], name="OutOfRange", scheduled_iso=(now + timedelta(days=40)).isoformat())

    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/leagues/{lg['id']}/upcoming-drafts?days=30", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 30
    names = [d["name"] for d in body["drafts"]]
    # Soonest, Middle, Last in sorted order — OutOfRange excluded
    assert names[:3] == ["Soonest", "Middle", "Last"]
    assert "OutOfRange" not in names


def test_upcoming_drafts_excludes_archived():
    _, tok = _register("noarch")
    lg = _create_league(tok)
    now = datetime.now(timezone.utc)
    d1 = _create_draft(tok, lg["id"], name="Live", scheduled_iso=(now + timedelta(days=5)).isoformat())
    d2 = _create_draft(tok, lg["id"], name="Archived", scheduled_iso=(now + timedelta(days=6)).isoformat())
    db = _db()
    db.drafts.update_one(
        {"_id": ObjectId(d2["_id"])},
        {"$set": {"status": "archived"}},
    )
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/leagues/{lg['id']}/upcoming-drafts", headers=H)
    assert r.status_code == 200
    names = [d["name"] for d in r.json()["drafts"]]
    assert "Live" in names
    assert "Archived" not in names


# ── Eligibility filters on /drafts/{id}/eligible-players ──────────────

def test_create_draft_persists_eligibility_filters():
    _, tok = _register("flags")
    lg = _create_league(tok)
    d = _create_draft(
        tok, lg["id"],
        exclude_previously_drafted=True,
        minors_eligibility_required=True,
    )
    db = _db()
    fresh = db.drafts.find_one({"_id": ObjectId(d["_id"])})
    assert fresh["exclude_previously_drafted"] is True
    assert fresh["minors_eligibility_required"] is True


def test_eligible_players_honours_minors_eligibility_required_flag():
    """When minors_eligibility_required is True, only minor_eligible
    players appear in the eligible-players endpoint."""
    _, tok = _register("minoronly")
    lg = _create_league(tok)
    d = _create_draft(tok, lg["id"], minors_eligibility_required=True)

    # Seed two test players — one minor_eligible, one not
    db = _db()
    sid = uuid.uuid4().hex[:8]
    db.players.insert_one({
        "name": f"Minor Eligible Forward {sid}", "position": "C",
        "team": "TST", "points": 10, "player_type": "skater",
        "minor_eligible": True, "nhl_id": f"min_{sid}",
    })
    db.players.insert_one({
        "name": f"NHL Veteran Forward {sid}", "position": "C",
        "team": "TST", "points": 10, "player_type": "skater",
        "minor_eligible": False, "nhl_id": f"vet_{sid}",
    })

    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(
        f"{API_URL}/api/drafts/{d['_id']}/eligible-players?search=Minor Eligible Forward {sid}",
        headers=H,
    )
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json().get("players", [])]
    # The minor-eligible player should appear
    assert any(f"Minor Eligible Forward {sid}" in n for n in names), names

    # Veteran should NOT appear (search for it returns empty)
    r2 = requests.get(
        f"{API_URL}/api/drafts/{d['_id']}/eligible-players?search=NHL Veteran Forward {sid}",
        headers=H,
    )
    names2 = [p["name"] for p in r2.json().get("players", [])]
    assert not any(f"NHL Veteran Forward {sid}" in n for n in names2), names2


def test_eligible_players_excludes_previously_drafted_when_flag_on():
    """When exclude_previously_drafted=True, players drafted in any
    OTHER draft in this league are filtered out."""
    _, tok = _register("hist")
    lg = _create_league(tok)
    db = _db()

    # Seed a player
    sid = uuid.uuid4().hex[:8]
    player_oid = db.players.insert_one({
        "name": f"Repeat Pick {sid}", "position": "C",
        "team": "TST", "points": 99, "player_type": "skater",
        "nhl_id": f"rp_{sid}",
    }).inserted_id

    # First draft: complete + record the player in picks
    d1 = _create_draft(tok, lg["id"], name="Historical")
    db.drafts.update_one(
        {"_id": ObjectId(d1["_id"])},
        {"$set": {
            "status": "completed",
            "picks": [{"overall": 1, "round": 1, "pick_in_round": 1,
                       "team": "TST", "player_id": str(player_oid),
                       "player": {"id": str(player_oid), "name": f"Repeat Pick {sid}"}}],
        }},
    )

    # New draft with the flag enabled
    d2 = _create_draft(tok, lg["id"], name="New", exclude_previously_drafted=True)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(
        f"{API_URL}/api/drafts/{d2['_id']}/eligible-players?search=Repeat Pick {sid}",
        headers=H,
    )
    assert r.status_code == 200
    names = [p["name"] for p in r.json().get("players", [])]
    assert not any(f"Repeat Pick {sid}" in n for n in names), \
        f"Repeat Pick should be filtered out, got: {names}"

    # Sanity: without the flag, the player IS visible
    d3 = _create_draft(tok, lg["id"], name="Open", exclude_previously_drafted=False)
    r3 = requests.get(
        f"{API_URL}/api/drafts/{d3['_id']}/eligible-players?search=Repeat Pick {sid}",
        headers=H,
    )
    names3 = [p["name"] for p in r3.json().get("players", [])]
    assert any(f"Repeat Pick {sid}" in n for n in names3), names3

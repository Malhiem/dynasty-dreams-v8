"""
Iter 228p — Additional integration tests against the LIVE preview
backend (REACT_APP_BACKEND_URL).  These complement the unit-style tests
in `test_iter228p_patch_total_rounds_syncs_picks.py` and exercise the
full PATCH /api/drafts/{id} contract end-to-end:

    * Grow / shrink the draft_picks collection is REFLECTED on the
      per-team Roster Draft Picks card (GET /api/teams/{id}/draft-picks).
    * 400 for out-of-range total_rounds.
    * 403 for non-commissioner.
    * 400 for non-scheduled drafts (active / completed / archived).
    * PATCH without `total_rounds` MUST NOT touch the draft_picks
      collection at all.
    * Full Edit-Draft dialog payload round-trips cleanly.
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


# ---------- shared helpers ----------------------------------------------------
def _register(prefix="i228pint"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    r.raise_for_status()
    return e, r.json()["access_token"]


def _setup(rounds=3, team_count=4):
    """Create league + 3 extra teams + scheduled draft (pick_trading on
    so the draft_picks collection is auto-seeded)."""
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228p-int-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": team_count,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()
    db = _db()
    for i in range(team_count - 1):
        db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"owner_{i}_{uuid.uuid4().hex[:6]}",
            "owner_name": f"Owner {i}", "name": f"Team {chr(65 + i)}",
            "roster": [],
        })
    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Int Test",
        "total_rounds": rounds, "time_per_pick": 60,
        "pick_trading_enabled": True, "trading_window_opens": "immediately",
    })
    r2.raise_for_status()
    return tok, league["id"], r2.json()["_id"], team_count


# ---------- 1. Roster page reflects the sync -----------------------------------
def test_roster_page_reflects_grow_and_shrink_immediately():
    tok, league_id, draft_id, team_count = _setup(rounds=3)
    H = {"Authorization": f"Bearer {tok}"}

    # Pick any team in this league
    team = _db().teams.find_one({"league_id": league_id})
    team_id = str(team["_id"])

    # Baseline: 3 rounds → 3 picks per team
    r = requests.get(f"{API_URL}/api/teams/{team_id}/draft-picks", headers=H)
    assert r.status_code == 200, r.text
    baseline = r.json()
    picks = baseline.get("picks") or baseline.get("draft_picks") or baseline
    if isinstance(picks, dict):
        picks = picks.get("picks") or []
    assert len(picks) == 3, f"expected 3, got {len(picks)}: {baseline}"

    # GROW → 6
    rp = requests.patch(f"{API_URL}/api/drafts/{draft_id}",
                        headers=H, json={"total_rounds": 6})
    assert rp.status_code == 200, rp.text
    r = requests.get(f"{API_URL}/api/teams/{team_id}/draft-picks", headers=H)
    assert r.status_code == 200
    picks = r.json().get("picks") or r.json()
    if isinstance(picks, dict):
        picks = picks.get("picks") or []
    assert len(picks) == 6, f"after grow expected 6, got {len(picks)}"

    # SHRINK → 2
    rp = requests.patch(f"{API_URL}/api/drafts/{draft_id}",
                        headers=H, json={"total_rounds": 2})
    assert rp.status_code == 200, rp.text
    r = requests.get(f"{API_URL}/api/teams/{team_id}/draft-picks", headers=H)
    assert r.status_code == 200
    picks = r.json().get("picks") or r.json()
    if isinstance(picks, dict):
        picks = picks.get("picks") or []
    assert len(picks) == 2, f"after shrink expected 2, got {len(picks)}"


# ---------- 2. Validation: out-of-range total_rounds → 400 --------------------
def test_patch_rejects_total_rounds_out_of_range():
    tok, _league_id, draft_id, _ = _setup(rounds=3)
    H = {"Authorization": f"Bearer {tok}"}

    for bad in [150, 0, -1, "not-a-number"]:
        r = requests.patch(f"{API_URL}/api/drafts/{draft_id}",
                           headers=H, json={"total_rounds": bad})
        assert r.status_code == 400, f"value {bad!r} should 400, got {r.status_code}: {r.text}"

    # Picks collection untouched after rejected requests
    after = _db().draft_picks.count_documents({"draft_id": draft_id})
    assert after == 12, f"expected 12 picks unchanged, got {after}"


# ---------- 3. Non-commissioner → 403 -----------------------------------------
def test_patch_blocks_non_commissioner():
    tok, league_id, draft_id, _ = _setup(rounds=3)

    # Register a brand new user — NOT the commissioner of this league
    _, other_tok = _register(prefix="i228pother")
    H_other = {"Authorization": f"Bearer {other_tok}"}

    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}",
                       headers=H_other, json={"total_rounds": 5})
    assert r.status_code == 403, r.text

    # No state change
    after = _db().draft_picks.count_documents({"draft_id": draft_id})
    assert after == 12


# ---------- 4. PATCH on non-scheduled draft → 400 -----------------------------
def test_patch_blocks_active_completed_archived():
    tok, _league_id, draft_id, _ = _setup(rounds=3)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    for status in ["active", "completed", "archived"]:
        db.drafts.update_one({"_id": ObjectId(draft_id)},
                             {"$set": {"status": status}})
        r = requests.patch(f"{API_URL}/api/drafts/{draft_id}",
                           headers=H, json={"total_rounds": 4})
        assert r.status_code == 400, f"{status} should 400, got {r.status_code}: {r.text}"
        assert status in r.text or "scheduled" in r.text.lower()


# ---------- 5. PATCH without total_rounds must NOT touch picks ----------------
def test_patch_without_total_rounds_does_not_touch_picks_collection():
    tok, _league_id, draft_id, _ = _setup(rounds=4)
    H = {"Authorization": f"Bearer {tok}"}
    db = _db()

    before_ids = sorted(str(p["_id"]) for p in db.draft_picks.find({"draft_id": draft_id}))

    # Update a bunch of fields but NOT total_rounds
    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "name": "Renamed Draft",
        "time_per_pick": 120,
        "missed_pick_action": "auto_pick",
        "snake_draft": True,
        "draft_type": "snake",
    })
    assert r.status_code == 200, r.text

    after_ids = sorted(str(p["_id"]) for p in db.draft_picks.find({"draft_id": draft_id}))
    assert after_ids == before_ids, "PATCH without total_rounds must not churn picks"


# ---------- 6. Full Edit-Draft dialog round-trip -------------------------------
def test_full_edit_dialog_payload_round_trip():
    tok, _league_id, draft_id, _ = _setup(rounds=4)
    H = {"Authorization": f"Bearer {tok}"}

    payload = {
        "name": "Big Edit",
        "scheduled_time": "2030-01-15T18:00:00Z",
        "total_rounds": 6,
        "time_per_pick": 1800,  # 30 minutes
        "draft_type": "snake",
        "snake_draft": True,
        "player_criteria": ["nhl_only", "no_injured"],
        "missed_pick_action": "auto_pick",
        "defer_user_options": True,
        "round_time_overrides": [
            {"from": 1, "to": 2, "seconds": 3600},
            {"from": 3, "to": 6, "seconds": 300},
        ],
        "exclude_previously_drafted": True,
        "minors_eligibility_required": False,
    }
    r = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json=payload)
    assert r.status_code == 200, r.text
    d = r.json()["draft"]
    for k, v in payload.items():
        if k == "scheduled_time":
            # Date may come back ISO-normalised — just verify it's set
            assert d.get(k), f"{k} missing in response"
            continue
        assert d.get(k) == v, f"field {k} mismatch: got {d.get(k)!r}, expected {v!r}"

    # And the picks collection was synced from 4 → 6 rounds
    db = _db()
    cnt = db.draft_picks.count_documents({"draft_id": draft_id})
    assert cnt == 6 * 4, f"expected 24 picks after grow, got {cnt}"


# ---------- 7. End-to-end smoke (create → patch → get → roster) ---------------
def test_e2e_create_patch_get_roster_smoke():
    tok, league_id, draft_id, team_count = _setup(rounds=5)
    H = {"Authorization": f"Bearer {tok}"}

    # GET draft
    r = requests.get(f"{API_URL}/api/drafts/{draft_id}", headers=H)
    assert r.status_code == 200, r.text
    assert r.json().get("total_rounds") == 5

    # PATCH to 3
    rp = requests.patch(f"{API_URL}/api/drafts/{draft_id}",
                        headers=H, json={"total_rounds": 3})
    assert rp.status_code == 200, rp.text

    # GET draft again
    r = requests.get(f"{API_URL}/api/drafts/{draft_id}", headers=H)
    assert r.json().get("total_rounds") == 3

    # All teams in this league should have exactly 3 picks each
    db = _db()
    teams = list(db.teams.find({"league_id": league_id}))
    for t in teams:
        tid = str(t["_id"])
        r = requests.get(f"{API_URL}/api/teams/{tid}/draft-picks", headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        picks = body.get("picks") if isinstance(body, dict) else body
        if isinstance(picks, dict):
            picks = picks.get("picks") or []
        assert len(picks) == 3, f"team {tid}: expected 3 picks, got {len(picks)}"

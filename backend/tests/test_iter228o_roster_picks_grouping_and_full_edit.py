"""
Iter 228o — Roster Draft Picks now grouped by parent draft.

Verifies:
  - GET /api/teams/{id}/draft-picks decorates each pick with
    `draft_id` + `draft_name` (explicit field, or year-derived fallback)
    so the Roster page can section picks by parent draft.
"""
import os
import uuid
import requests
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def _register(prefix="i228o"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def test_team_draft_picks_decorated_with_explicit_draft_id():
    """Newly-seeded picks carry draft_id; the endpoint returns matching draft_name."""
    _, tok = _register("explicit")
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228o-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()

    # Create a draft with a distinctive name + 1 round so seeding emits picks
    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Inaugural Roster Picks",
        "total_rounds": 2, "time_per_pick": 60,
        "pick_trading_enabled": True, "trading_window_opens": "immediately",
    })
    r2.raise_for_status()
    draft_id = r2.json()["_id"]

    # Find a team in the league
    db = _db()
    team = db.teams.find_one({"league_id": league["id"]})
    assert team, "Expected at least one team auto-created"

    # Verify picks have draft_id set in DB
    seeded = list(db.draft_picks.find({"draft_id": draft_id}))
    assert len(seeded) > 0, "Seeded picks should be present"
    assert all(p.get("draft_id") == draft_id for p in seeded)

    # Hit the team-draft-picks endpoint
    r3 = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    assert r3.status_code == 200, r3.text
    picks = r3.json()["picks"]
    own_picks = [p for p in picks if p.get("draft_id") == draft_id]
    assert len(own_picks) > 0, picks
    assert all(p.get("draft_name") == "Inaugural Roster Picks" for p in own_picks)


def test_team_draft_picks_legacy_falls_back_to_year_join():
    """Legacy picks without draft_id are matched against drafts by
    (league_id, year-derived-from-scheduled_time)."""
    _, tok = _register("legacy")
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228o-leg-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()

    # Create a draft scheduled in 2028 so we can target it by year
    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "2028 Legacy Test Draft",
        "scheduled_time": "2028-05-15T19:00:00Z",
        "total_rounds": 1, "time_per_pick": 60,
    })
    r2.raise_for_status()

    db = _db()
    team = db.teams.find_one({"league_id": league["id"]})

    # Manually insert a legacy pick WITHOUT draft_id but with matching year
    db.draft_picks.insert_one({
        "league_id": league["id"],
        "year": 2028,  # matches the draft above
        "round": 1, "slot": 1, "overall": 1,
        "original_team_id": str(team["_id"]),
        "original_team_name": team["name"],
        "current_team_id": str(team["_id"]),
        "current_team_name": team["name"],
        "trade_history": [],
        "tradeable": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # No draft_id field — simulates pre-iter228o picks
    })

    r3 = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks?year=2028", headers=H)
    assert r3.status_code == 200, r3.text
    picks = r3.json()["picks"]
    assert len(picks) >= 1
    p = next((p for p in picks if p["year"] == 2028 and "draft_id" not in p.get("_id", "")), picks[0])
    # Fallback should have populated draft_name from year join
    assert p.get("draft_name") == "2028 Legacy Test Draft", p
    assert p.get("draft_id")  # populated by fallback


def test_team_draft_picks_unmapped_year_uses_year_label():
    """Picks for years with no scheduled draft fall back to a
    "YYYY Draft" label so the UI never shows undefined."""
    _, tok = _register("orphan")
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228o-orp-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()

    db = _db()
    team = db.teams.find_one({"league_id": league["id"]})

    # Insert a pick for a year with NO scheduled draft
    db.draft_picks.insert_one({
        "league_id": league["id"],
        "year": 2099, "round": 1, "slot": 1, "overall": 1,
        "original_team_id": str(team["_id"]),
        "original_team_name": team["name"],
        "current_team_id": str(team["_id"]),
        "current_team_name": team["name"],
        "trade_history": [], "tradeable": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    r2 = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks?year=2099", headers=H)
    assert r2.status_code == 200
    picks = r2.json()["picks"]
    assert any(p.get("draft_name") == "2099 Draft" for p in picks)


# ── Edit Draft — verify FULL config payload round-trips ───────────────

def test_patch_draft_accepts_full_customization_payload():
    """The edit endpoint accepts every editable field at once."""
    _, tok = _register("full")
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228o-full-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()
    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Full Edit Test",
        "total_rounds": 3, "time_per_pick": 60,
    })
    r2.raise_for_status()
    draft_id = r2.json()["_id"]

    # Send EVERY editable field at once
    r3 = requests.patch(f"{API_URL}/api/drafts/{draft_id}", headers=H, json={
        "name": "Fully Edited",
        "draft_type": "keeper",
        "snake_draft": False,
        "total_rounds": 7,
        "time_per_pick": 300,
        "missed_pick_action": "defer-to-user",
        "defer_user_options": ["auto-best", "pick-anytime"],
        "player_criteria": ["entry"],
        "round_time_overrides": [{"from": 1, "to": 3, "seconds": 600}],
        "exclude_previously_drafted": True,
        "minors_eligibility_required": True,
    })
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert set(body["updated_fields"]) >= {
        "name", "draft_type", "snake_draft", "total_rounds",
        "time_per_pick", "missed_pick_action", "defer_user_options",
        "player_criteria", "round_time_overrides",
        "exclude_previously_drafted", "minors_eligibility_required",
    }
    d = body["draft"]
    assert d["name"] == "Fully Edited"
    assert d["draft_type"] == "keeper"
    assert d["snake_draft"] is False
    assert d["total_rounds"] == 7
    assert d["time_per_pick"] == 300
    assert d["missed_pick_action"] == "defer-to-user"
    assert d["defer_user_options"] == ["auto-best", "pick-anytime"]
    assert d["player_criteria"] == ["entry"]
    assert d["round_time_overrides"] == [{"from": 1, "to": 3, "seconds": 600}]
    assert d["exclude_previously_drafted"] is True
    assert d["minors_eligibility_required"] is True

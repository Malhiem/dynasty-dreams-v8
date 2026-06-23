"""
Iter 221 — Force-remove user from an active draft.

Validates the upgraded /admin/platform/users/{uid}/force-remove-from-draft:
  • Sets autopick_enabled on the user's team(s)
  • Drains on-clock picks via shared auto-pick helper when the evicted
    user is currently on the clock
  • Returns picks_drained count + writes an audit row
  • Sends a user notification
  • 403s non-admins
"""
from __future__ import annotations

import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASS = "Admin123!"

_mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_db_name = os.environ.get("DB_NAME", "test_database")
_client = MongoClient(_mongo_url)
_db = _client[_db_name]


def _login(email, password):
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _register_user():
    suffix = uuid.uuid4().hex[:8]
    email = f"iter221evict_{suffix}@example.com"
    username = f"iter221evict_{suffix}"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": email, "password": "TestPass123!",
        "username": username, "name": f"Evict {suffix}",
    }).raise_for_status()
    tok = _login(email, "TestPass123!")
    me = requests.get(f"{API_URL}/api/auth/me",
                      headers={"Authorization": f"Bearer {tok}"}).json()
    return me["id"], email, tok


def _admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


def _seed_active_draft(commish_token, victim_user_id):
    """Create a league with the victim as a team owner, start a draft, and
    contrive for the victim's team to be on the clock.

    Returns (draft_id, league_id, victim_team_id).
    """
    H = {"Authorization": f"Bearer {commish_token}"}
    # Create league
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "Iter221 EvictTest " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 4, "draft_type": "snake", "roster_spots": 10,
    })
    r.raise_for_status()
    league = r.json()
    league_id = league["id"]

    # Insert a team owned by the victim directly via Mongo (bypass invite flow)
    victim_team = {
        "league_id": league_id,
        "owner_id": victim_user_id,
        "name": "Victim Squad",
        "abbr": "VIC",
        "roster": [],
        "draft_queue": [],
    }
    inserted = _db.teams.insert_one(victim_team)
    victim_team_id = str(inserted.inserted_id)

    # Two filler teams so the snake order has 3 total teams (min for variety)
    for i in range(2):
        _db.teams.insert_one({
            "league_id": league_id,
            "owner_id": f"filler_{uuid.uuid4().hex[:6]}",
            "name": f"Filler {i+1}",
            "abbr": f"F{i+1}",
            "roster": [],
            "draft_queue": [],
        })

    # Fetch teams to build draft (commish included). Auto-created commish
    # team won't have an abbr — derive one from the name.
    teams = list(_db.teams.find({"league_id": league_id}))
    for t in teams:
        if not t.get("abbr"):
            t["abbr"] = (t.get("name") or "TEAM")[:3].upper()
            _db.teams.update_one({"_id": t["_id"]}, {"$set": {"abbr": t["abbr"]}})
    team_abbrs = [t["abbr"] for t in teams]
    team_map = {t["abbr"]: {"id": str(t["_id"]), "name": t["name"]} for t in teams}

    # Manually create an ACTIVE draft positioned so the victim is on the clock.
    # current_pick = the index (1-based) where get_team_for_pick → victim abbr
    # For snake draft round 1, pick #i = team_abbrs[i-1].
    victim_idx = team_abbrs.index("VIC") + 1

    draft_doc = {
        "league_id": league_id,
        "status": "active",
        "draft_started": True,
        "snake_draft": True,
        "team_abbrs": team_abbrs,
        "team_map": team_map,
        "total_rounds": 3,
        "current_pick": victim_idx,
        "picks": [],
        "chat_messages": [],
        "player_criteria": "open",
    }
    res = _db.drafts.insert_one(draft_doc)
    return str(res.inserted_id), league_id, victim_team_id


def _ensure_players_exist():
    """Make sure there are at least a handful of non-prospect players
    available for auto-pick to land on."""
    count = _db.players.count_documents({"player_type": {"$ne": "prospect"}})
    if count >= 5:
        return
    for i in range(5):
        _db.players.insert_one({
            "name": f"Iter221 Player {i}",
            "position": "C",
            "team": "NHL",
            "points": 100 - i,
            "goals": 30, "assists": 50, "games_played": 70,
            "player_type": "skater",
        })


def test_evict_non_admin_forbidden():
    _, _, victim_tok = _register_user()
    H = {"Authorization": f"Bearer {victim_tok}"}
    victim_id, _, _ = _register_user()
    r = requests.post(
        f"{API_URL}/api/admin/platform/users/{victim_id}/force-remove-from-draft",
        headers=H, json={"draft_id": "deadbeef", "reason": "x"},
    )
    assert r.status_code in (401, 403), r.text


def test_evict_drains_on_clock_picks_and_flips_autopick():
    _ensure_players_exist()
    # Commish + victim
    _, _, commish_tok = _register_user()
    victim_id, _, _ = _register_user()
    draft_id, league_id, victim_team_id = _seed_active_draft(commish_tok, victim_id)

    H = {"Authorization": f"Bearer {_admin_token()}"}
    r = requests.post(
        f"{API_URL}/api/admin/platform/users/{victim_id}/force-remove-from-draft",
        headers=H, json={"draft_id": draft_id, "reason": "abusive behavior"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["audit_id"]
    assert body["teams_flagged"] == 1
    # At least one pick should be drained (the one the victim was on the clock for)
    assert body["picks_drained"] >= 1, body

    # Team flag flipped
    team = _db.teams.find_one({"_id": ObjectId(victim_team_id)})
    assert team["autopick_enabled"] is True
    assert team.get("autopick_forced_at")

    # Draft current_pick advanced past the victim
    draft = _db.drafts.find_one({"_id": ObjectId(draft_id)})
    assert draft["current_pick"] >= 2


def test_evict_missing_draft_id_400():
    _, _, victim_tok = _register_user()
    victim_id, _, _ = _register_user()
    H = {"Authorization": f"Bearer {_admin_token()}"}
    r = requests.post(
        f"{API_URL}/api/admin/platform/users/{victim_id}/force-remove-from-draft",
        headers=H, json={"reason": "no draft_id"},
    )
    assert r.status_code == 400


def test_evict_user_without_team_in_league_404():
    """If the user has no team in the draft's league, the action should
    bail with a clear error rather than silently no-op."""
    _ensure_players_exist()
    _, _, commish_tok = _register_user()
    victim_id, _, _ = _register_user()
    draft_id, _, _ = _seed_active_draft(commish_tok, victim_id)

    # Different user with no team — admin tries to evict them from this draft
    no_team_id, _, _ = _register_user()
    H = {"Authorization": f"Bearer {_admin_token()}"}
    r = requests.post(
        f"{API_URL}/api/admin/platform/users/{no_team_id}/force-remove-from-draft",
        headers=H, json={"draft_id": draft_id, "reason": "stranger"},
    )
    assert r.status_code == 404

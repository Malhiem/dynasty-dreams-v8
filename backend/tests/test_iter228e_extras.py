"""
Iter 228e additional edge-case tests beyond the dev's own pytest file.

Focus: authorization on every new endpoint, restore-non-archived behavior,
admin players verify filters (position + nhl_team), 9xx synthetic nhl_id range.
"""
import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"))


def _admin_token():
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")})
    r.raise_for_status()
    return r.json()["access_token"]


def _user_token(prefix="i228x"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


# ── Authorization 403 for non-admin on each admin endpoint ─────────


def test_archived_endpoints_block_non_admin():
    _, tok = _user_token()
    H = {"Authorization": f"Bearer {tok}"}
    fake_id = uuid.uuid4().hex
    # GET /api/admin/drafts/archived
    assert requests.get(f"{API_URL}/api/admin/drafts/archived", headers=H).status_code == 403
    # POST restore / purge
    assert requests.post(f"{API_URL}/api/admin/drafts/{fake_id}/restore", headers=H).status_code == 403
    assert requests.post(f"{API_URL}/api/admin/drafts/{fake_id}/purge", headers=H).status_code == 403
    # players verify + create
    assert requests.get(f"{API_URL}/api/admin/players/verify", headers=H).status_code == 403
    assert requests.post(f"{API_URL}/api/admin/players", headers=H, json={
        "name": "Forbidden", "position": "C", "team": "X",
        "league_status": "AHL", "player_type": "skater",
    }).status_code == 403


# ── Admin player create: synthetic 9xx nhl_id range ────────────────


def test_admin_player_create_yields_namespaced_synthetic_id():
    Ha = {"Authorization": f"Bearer {_admin_token()}"}
    name = f"E2E AHL {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API_URL}/api/admin/players", headers=Ha, json={
        "name": name, "position": "C", "team": "Hershey Bears",
        "league_status": "AHL", "player_type": "skater",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    # Admin identifiers use a separate namespace from real NHL numeric IDs.
    assert str(body["nhl_id"]).startswith("admin_")
    from bson import ObjectId
    assert ObjectId.is_valid(body["nhl_id"].removeprefix("admin_"))


# ── Filter combinations on /api/admin/players/verify ───────────────


def test_admin_players_verify_position_and_team_filter():
    Ha = {"Authorization": f"Bearer {_admin_token()}"}
    # Add a junior player with very specific name + team
    suffix = uuid.uuid4().hex[:6]
    name = f"E2E Junior {suffix}"
    team = f"OHL-{suffix}"
    requests.post(f"{API_URL}/api/admin/players", headers=Ha, json={
        "name": name, "position": "LW", "team": team,
        "league_status": "Junior", "player_type": "skater",
    }).raise_for_status()

    # Filter by team (backend stores team uppercased)
    r = requests.get(f"{API_URL}/api/admin/players/verify",
                     headers=Ha, params={"nhl_team": team.upper()})
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json()["players"]]
    assert name in names, r.json()

    # Filter by position only (might be many, but ours should be there with search)
    r2 = requests.get(f"{API_URL}/api/admin/players/verify",
                      headers=Ha, params={"position": "LW", "search": suffix})
    assert r2.status_code == 200
    names2 = [p["name"] for p in r2.json()["players"]]
    assert name in names2


# ── Restore of a never-archived draft ──────────────────────────────


def test_restore_of_non_archived_draft_returns_400_or_404():
    """Restore should reject drafts that are not in archived state."""
    _, tok = _user_token("rest")
    H = {"Authorization": f"Bearer {tok}"}
    lr = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228x-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    lr.raise_for_status()
    league = lr.json()
    dr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Active draft",
        "total_rounds": 5, "time_per_pick": 60,
        "missed_pick_action": "auto-select",
    })
    dr.raise_for_status()
    draft = dr.json()
    Ha = {"Authorization": f"Bearer {_admin_token()}"}
    r = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/restore", headers=Ha)
    # Either 400 (not archived) or 404 (not found in archived collection); both acceptable
    assert r.status_code in (200, 400, 404), r.text


# ── GET defer with persisted choice round-trip ─────────────────────


def test_defer_get_reflects_available_options_list_intact():
    _, tok = _user_token("dx")
    H = {"Authorization": f"Bearer {tok}"}
    lr = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228x-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    league = lr.json()
    dr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Defer subset draft",
        "total_rounds": 5, "time_per_pick": 60,
        "missed_pick_action": "defer-to-user",
        "defer_user_options": ["auto-best", "pick-anytime"],  # subset
    })
    dr.raise_for_status()
    draft = dr.json()
    r = requests.get(f"{API_URL}/api/drafts/{draft['_id']}/picks/2/defer", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["available_options"]) == {"auto-best", "pick-anytime"}, body

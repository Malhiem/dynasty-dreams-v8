"""
Iter 228e — Admin archived-drafts UI + per-claim defer-to-user + player verification.
"""
import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")


def _login_admin():
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": "Admin123!"})
    r.raise_for_status()
    return r.json()["access_token"]


def _register(prefix="i228e"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _create_league_and_draft(tok):
    H = {"Authorization": f"Bearer {tok}"}
    lr = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228e-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    lr.raise_for_status()
    league = lr.json()
    dr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Archive test",
        "total_rounds": 5, "time_per_pick": 60,
        "missed_pick_action": "defer-to-user",
        "defer_user_options": ["auto-best", "auto-queue", "pick-anytime"],
    })
    dr.raise_for_status()
    return league, dr.json()


# ─── Archived drafts admin UI ─────────────────────────────────


def test_admin_list_archived_drafts_requires_admin():
    """Non-admins get 403; admin sees archived drafts with days_until_purge."""
    _, tok = _register("ad")
    league, draft = _create_league_and_draft(tok)
    Hc = {"Authorization": f"Bearer {tok}"}
    requests.delete(f"{API_URL}/api/drafts/{draft['_id']}", headers=Hc).raise_for_status()

    # Non-admin gets 403
    r = requests.get(f"{API_URL}/api/admin/drafts/archived", headers=Hc)
    assert r.status_code == 403

    # Admin sees the row
    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}
    r2 = requests.get(f"{API_URL}/api/admin/drafts/archived", headers=Ha)
    assert r2.status_code == 200
    body = r2.json()
    rows = [d for d in body["drafts"] if d["id"] == draft["_id"]]
    assert rows, body
    row = rows[0]
    assert row["name"] == "Archive test"
    # days_until_purge should be 15 (just archived) within a small window
    assert 14 <= int(row["days_until_purge"]) <= 15, row


def test_admin_purge_then_admin_restore_lifecycle():
    """Admin can permanently purge OR restore an archived draft."""
    _, tok = _register("ad2")
    _, draft = _create_league_and_draft(tok)
    Hc = {"Authorization": f"Bearer {tok}"}
    requests.delete(f"{API_URL}/api/drafts/{draft['_id']}", headers=Hc).raise_for_status()

    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}

    # Admin can restore an archived draft
    r = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/restore", headers=Ha)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"

    # Re-archive then purge
    requests.delete(f"{API_URL}/api/drafts/{draft['_id']}", headers=Hc).raise_for_status()
    r2 = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/purge", headers=Ha)
    assert r2.status_code == 200
    assert r2.json()["status"] == "purged"

    # Now gone
    r3 = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/purge", headers=Ha)
    assert r3.status_code == 404, r3.text


def test_admin_purge_refuses_non_archived_draft():
    """Purge requires the draft be already soft-archived."""
    _, tok = _register("ad3")
    _, draft = _create_league_and_draft(tok)
    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}
    r = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/purge", headers=Ha)
    assert r.status_code == 400
    assert "archived" in r.json()["detail"].lower()


# ─── Per-pick defer-to-user ───────────────────────────────────


def test_get_defer_options_surfaces_draft_level_defaults():
    """Even before a pick is materialized, GET returns the available options."""
    _, tok = _register("df")
    _, draft = _create_league_and_draft(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/drafts/{draft['_id']}/picks/1/defer", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available_options"] == ["auto-best", "auto-queue", "pick-anytime"]
    assert body["defer_choice"] is None


def test_pre_pick_defer_choice_persists_in_pending_map():
    """When the pick isn't materialized, choice is stored in pick_defer_choices."""
    _, tok = _register("df2")
    _, draft = _create_league_and_draft(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts/{draft['_id']}/picks/3/defer",
                      headers=H, json={"choice": "auto-queue"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["choice"] == "auto-queue"
    assert body["stored"] == "pending"

    # Read it back
    r2 = requests.get(f"{API_URL}/api/drafts/{draft['_id']}/picks/3/defer", headers=H)
    assert r2.status_code == 200
    assert r2.json()["defer_choice"] == "auto-queue"


def test_defer_rejects_invalid_choice():
    _, tok = _register("df3")
    _, draft = _create_league_and_draft(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/drafts/{draft['_id']}/picks/1/defer",
                      headers=H, json={"choice": "random-bogus"})
    assert r.status_code == 400


def test_defer_rejects_when_draft_is_not_defer_to_user():
    """Drafts whose missed_pick_action != 'defer-to-user' return 400."""
    _, tok = _register("df4")
    H = {"Authorization": f"Bearer {tok}"}
    lr = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228e-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    league = lr.json()
    dr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "Auto-select draft",
        "total_rounds": 5, "time_per_pick": 60,
        "missed_pick_action": "auto-select",
    })
    draft = dr.json()
    r = requests.post(f"{API_URL}/api/drafts/{draft['_id']}/picks/1/defer",
                      headers=H, json={"choice": "auto-best"})
    assert r.status_code == 400
    assert "defer-to-user" in r.json()["detail"]


# ─── Admin player verify ──────────────────────────────────────


def test_admin_verify_players_filters_by_league_status():
    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}

    # Insert a synthetic European-league player via admin POST
    name = f"E2E Euro {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API_URL}/api/admin/players", headers=Ha, json={
        "name": name, "position": "RW", "team": "SKA",
        "league_status": "Europe", "player_type": "skater",
    })
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert pid

    # Listing Europe-only should include it
    r2 = requests.get(f"{API_URL}/api/admin/players/verify",
                      headers=Ha, params={"league_status": "Europe", "search": "E2E Euro"})
    assert r2.status_code == 200, r2.text
    names = [p["name"] for p in r2.json()["players"]]
    assert name in names, r2.json()


def test_admin_verify_players_requires_admin():
    _, tok = _register("pv")
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/admin/players/verify", headers=H)
    assert r.status_code == 403


# ─── Iter 228f — Admin purge/restore audit logging ────────────


def test_admin_purge_writes_audit_row():
    """Purging an archived draft writes an admin_user_actions audit row
    with the draft snapshot in metadata."""
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    _, tok = _register("aupg")
    league, draft = _create_league_and_draft(tok)
    Hc = {"Authorization": f"Bearer {tok}"}
    requests.delete(f"{API_URL}/api/drafts/{draft['_id']}", headers=Hc).raise_for_status()

    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}
    r = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/purge", headers=Ha)
    assert r.status_code == 200

    row = db.admin_user_actions.find_one({
        "action": "draft_purge",
        "metadata.draft_id": draft["_id"],
    })
    assert row is not None, "expected an audit row for the purge"
    assert row["admin_email"] == ADMIN_EMAIL
    assert row["metadata"]["draft_name"] == "Archive test"
    assert row["metadata"]["league_id"] == league["id"]
    assert row["target_user_id"]  # commissioner's id captured
    assert "ts" in row


def test_admin_restore_writes_audit_row():
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    _, tok = _register("aurs")
    _, draft = _create_league_and_draft(tok)
    Hc = {"Authorization": f"Bearer {tok}"}
    requests.delete(f"{API_URL}/api/drafts/{draft['_id']}", headers=Hc).raise_for_status()

    admin_tok = _login_admin()
    Ha = {"Authorization": f"Bearer {admin_tok}"}
    r = requests.post(f"{API_URL}/api/admin/drafts/{draft['_id']}/restore", headers=Ha)
    assert r.status_code == 200

    row = db.admin_user_actions.find_one({
        "action": "draft_restore",
        "metadata.draft_id": draft["_id"],
    })
    assert row is not None, "expected an audit row for the restore"
    assert row["prior_state"]["status"] == "archived"

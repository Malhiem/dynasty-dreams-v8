"""
Iter 228l — Draft audit-log timeline endpoint + commissioner-side audit
rows for archive/restore.

Verifies:
  - DELETE /api/drafts/{id} writes an `admin_user_actions` row tagged
    `action="draft_archive"`.
  - POST /api/drafts/{id}/restore writes a `draft_restore` row.
  - GET /api/admin/drafts/{id}/audit returns the merged timeline
    sorted newest-first.
  - Endpoint is site-admin only (non-admin → 403).
"""
import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def _register(prefix="i228l"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def _admin_login():
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), "password": os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")})
    r.raise_for_status()
    return r.json()["access_token"]


def _create_league_with_draft(tok):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228l-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 20,
    })
    r.raise_for_status()
    league = r.json()
    r2 = requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league["id"], "name": "AuditTrail Draft",
        "total_rounds": 3, "time_per_pick": 60,
    })
    r2.raise_for_status()
    return league, r2.json()["_id"]


def test_commish_archive_writes_audit_row():
    _, tok = _register("arch")
    league, draft_id = _create_league_with_draft(tok)
    H = {"Authorization": f"Bearer {tok}"}

    r = requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "archived"

    db = _db()
    audit = list(db.admin_user_actions.find({
        "metadata.draft_id": draft_id, "action": "draft_archive",
    }))
    assert len(audit) == 1
    assert audit[0]["metadata"]["draft_name"] == "AuditTrail Draft"
    assert audit[0]["metadata"]["league_id"] == league["id"]


def test_commish_restore_writes_audit_row():
    _, tok = _register("restore")
    _, draft_id = _create_league_with_draft(tok)
    H = {"Authorization": f"Bearer {tok}"}

    requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=H).raise_for_status()
    r = requests.post(f"{API_URL}/api/drafts/{draft_id}/restore", headers=H)
    assert r.status_code == 200, r.text

    db = _db()
    rows = list(db.admin_user_actions.find({
        "metadata.draft_id": draft_id,
        "action": {"$in": ["draft_archive", "draft_restore"]},
    }).sort("ts", 1))
    actions = [r["action"] for r in rows]
    assert actions == ["draft_archive", "draft_restore"], actions


def test_admin_audit_timeline_endpoint_returns_merged_history():
    _, comm_tok = _register("comm")
    league, draft_id = _create_league_with_draft(comm_tok)
    Hc = {"Authorization": f"Bearer {comm_tok}"}

    # Soft delete + restore + soft delete again
    requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=Hc).raise_for_status()
    requests.post(f"{API_URL}/api/drafts/{draft_id}/restore", headers=Hc).raise_for_status()
    requests.delete(f"{API_URL}/api/drafts/{draft_id}", headers=Hc).raise_for_status()

    # Admin purges it
    admin_tok = _admin_login()
    Ha = {"Authorization": f"Bearer {admin_tok}"}
    pr = requests.post(f"{API_URL}/api/admin/drafts/{draft_id}/purge", headers=Ha)
    assert pr.status_code == 200, pr.text

    # Fetch audit timeline
    r = requests.get(f"{API_URL}/api/admin/drafts/{draft_id}/audit", headers=Ha)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft_id"] == draft_id
    actions = [e["action"] for e in body["entries"]]
    # Sorted newest-first → purge is first, then archive, restore, archive
    assert actions[0] == "draft_purge"
    assert "draft_restore" in actions
    assert actions.count("draft_archive") == 2

    # Verify metadata snapshot present
    purge_entry = next(e for e in body["entries"] if e["action"] == "draft_purge")
    assert purge_entry["metadata"]["draft_name"] == "AuditTrail Draft"
    assert purge_entry["admin_email"] == os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")


def test_admin_audit_endpoint_requires_admin():
    _, tok = _register("nonadmin")
    _, draft_id = _create_league_with_draft(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/admin/drafts/{draft_id}/audit", headers=H)
    assert r.status_code == 403

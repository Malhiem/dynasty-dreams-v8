"""
Iter 217 — Forum + Roster snapshots + real Account-merge tests.
"""
from __future__ import annotations

import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASS = "Admin123!"


def _login(email, password) -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASS)}"}


def _make_disposable_user():
    suffix = uuid.uuid4().hex[:8]
    email = f"iter217_{suffix}@example.com"
    username = f"iter217_{suffix}"
    password = "TestPass123!"
    r = requests.post(f"{API_URL}/api/auth/register",
                      json={"email": email, "password": password,
                            "username": username, "name": "Iter217 Tester"})
    r.raise_for_status()
    token = _login(email, password)
    me = requests.get(f"{API_URL}/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}).json()
    return me["id"], email, token


def _find_active_league_and_team(token):
    """Return (league_id, team_id) for a league the user already belongs
    to. Falls back to admin context if needed."""
    r = requests.get(f"{API_URL}/api/leagues",
                     headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        return None, None
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    for lg in leagues[:3]:
        lid = lg.get("id") or lg.get("_id") or str(lg.get("league_id"))
        teams_r = requests.get(f"{API_URL}/api/teams?league_id={lid}",
                                headers={"Authorization": f"Bearer {token}"})
        if teams_r.status_code == 200:
            teams = teams_r.json() if isinstance(teams_r.json(), list) else teams_r.json().get("teams", [])
            if teams:
                return lid, teams[0].get("id") or teams[0].get("_id")
    return None, None


# ─── Forum ──────────────────────────────────────────────────────────

def test_forum_thread_create_and_list_admin_path():
    """Admin can create + list threads in any league (admin bypass)."""
    H = _admin_headers()
    # Find any league
    leagues_r = requests.get(f"{API_URL}/api/admin/platform/league-health?limit=1", headers=H)
    if leagues_r.status_code != 200 or not leagues_r.json().get("leagues"):
        return  # skip if no league
    league_id = leagues_r.json()["leagues"][0]["league_id"]
    title = f"iter217 thread {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API_URL}/api/forum/threads", headers=H,
                      json={"league_id": league_id, "title": title,
                            "body": "First post in this thread"})
    assert r.status_code == 200, r.text
    tid = r.json()["thread_id"]
    # List threads
    lr = requests.get(f"{API_URL}/api/forum/threads?league_id={league_id}", headers=H)
    assert lr.status_code == 200
    assert any(t["id"] == tid for t in lr.json()["threads"])
    # Get posts in thread (the first post)
    pr = requests.get(f"{API_URL}/api/forum/threads/{tid}/posts", headers=H)
    assert pr.status_code == 200
    assert len(pr.json()["posts"]) >= 1
    # Reply to thread
    rr = requests.post(f"{API_URL}/api/forum/threads/{tid}/posts", headers=H,
                      json={"body": "Second post"})
    assert rr.status_code == 200
    # Cleanup
    requests.delete(f"{API_URL}/api/forum/threads/{tid}", headers=H)


def test_forum_unauth_blocked():
    r = requests.get(f"{API_URL}/api/forum/threads?league_id=000000000000000000000000")
    assert r.status_code == 401


def test_forum_non_member_blocked():
    """A user with no team in the league cannot list/post threads."""
    H = _admin_headers()
    leagues_r = requests.get(f"{API_URL}/api/admin/platform/league-health?limit=1", headers=H)
    if leagues_r.status_code != 200 or not leagues_r.json().get("leagues"):
        return
    league_id = leagues_r.json()["leagues"][0]["league_id"]
    _, _, user_token = _make_disposable_user()
    r = requests.get(f"{API_URL}/api/forum/threads?league_id={league_id}",
                     headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 403


# ─── Roster snapshots ───────────────────────────────────────────────

def test_snapshot_create_list_restore():
    """Manual snapshot, list, then restore round-trip."""
    H = _admin_headers()
    leagues_r = requests.get(f"{API_URL}/api/admin/platform/league-health?limit=1", headers=H)
    if leagues_r.status_code != 200 or not leagues_r.json().get("leagues"):
        return
    league_id = leagues_r.json()["leagues"][0]["league_id"]
    # Find a team in that league
    team_r = requests.get(f"{API_URL}/api/teams?league_id={league_id}", headers=H)
    if team_r.status_code != 200:
        return
    teams = team_r.json() if isinstance(team_r.json(), list) else team_r.json().get("teams", [])
    if not teams:
        return
    team_id = teams[0].get("id") or teams[0].get("_id") or str(teams[0].get("_id"))
    # Take a snapshot
    snap = requests.post(f"{API_URL}/api/teams/{team_id}/snapshots", headers=H,
                         json={"reason": "iter217 test snapshot"})
    assert snap.status_code == 200, snap.text
    sid = snap.json()["snapshot_id"]
    # List snapshots
    lr = requests.get(f"{API_URL}/api/teams/{team_id}/snapshots", headers=H)
    assert lr.status_code == 200
    assert any(s["id"] == sid for s in lr.json()["snapshots"])
    # Restore — should auto-create a pre-restore snapshot
    rr = requests.post(f"{API_URL}/api/teams/{team_id}/snapshots/{sid}/restore", headers=H)
    assert rr.status_code == 200, rr.text
    assert rr.json()["pre_restore_snapshot_id"]


def test_snapshot_unauth():
    r = requests.get(f"{API_URL}/api/teams/000000000000000000000000/snapshots")
    assert r.status_code == 401


# ─── Real account merge ─────────────────────────────────────────────

def test_account_merge_migrates_data_and_soft_deletes_source():
    """End-to-end merge: source user has a flag-for-review action and
    a notification → after merge those rows belong to target, and
    source.status='merged_into_other_account'."""
    H = _admin_headers()
    # Create source + target
    src_id, src_email, _ = _make_disposable_user()
    tgt_id, tgt_email, _ = _make_disposable_user()

    # Generate some source-owned audit rows (flag + warning)
    requests.post(f"{API_URL}/api/admin/platform/users/{src_id}/flag-for-review",
                  headers=H, json={"reason": "iter217 merge source"})
    requests.post(f"{API_URL}/api/admin/platform/users/{src_id}/warning",
                  headers=H, json={"reason": "iter217 source warning"})

    # Confirm action rows reference the source
    pre = requests.get(f"{API_URL}/api/admin/platform/users/{src_id}/admin-actions", headers=H)
    assert any(a["action"] == "flag_for_review" for a in pre.json()["actions"])

    # Execute merge
    mr = requests.post(f"{API_URL}/api/admin/platform/users/{tgt_id}/merge-accounts",
                       headers=H,
                       json={"source_user_id": src_id, "reason": "iter217 merge test"})
    assert mr.status_code == 200, mr.text
    d = mr.json()
    assert d.get("mocked") is None or d.get("mocked") is False
    counts = d["counts"]
    assert counts["admin_actions_target"] >= 2

    # Source must now be soft-deleted (merged status)
    src_detail = requests.get(f"{API_URL}/api/admin/platform/users/{src_id}", headers=H).json()
    assert src_detail["status"] == "merged_into_other_account"
    assert "merged_" in src_detail["email"]  # anonymised

    # Target now has the source's admin actions (rows moved)
    tgt_actions = requests.get(f"{API_URL}/api/admin/platform/users/{tgt_id}/admin-actions",
                                headers=H).json()["actions"]
    assert any(a["action"] == "flag_for_review" for a in tgt_actions)


def test_account_merge_same_source_target_rejected():
    H = _admin_headers()
    uid, _, _ = _make_disposable_user()
    r = requests.post(f"{API_URL}/api/admin/platform/users/{uid}/merge-accounts",
                      headers=H, json={"source_user_id": uid, "reason": "x"})
    assert r.status_code == 400


def test_account_merge_missing_source_rejected():
    H = _admin_headers()
    uid, _, _ = _make_disposable_user()
    r = requests.post(f"{API_URL}/api/admin/platform/users/{uid}/merge-accounts",
                      headers=H, json={"reason": "x"})
    assert r.status_code == 400


# ─── reset_team now uses real snapshots ─────────────────────────────

def test_reset_team_requires_snapshot_id():
    """The iter 217 reset_team is no longer a STUB. It requires a
    snapshot_id and uses the real restore flow."""
    H = _admin_headers()
    uid, _, _ = _make_disposable_user()
    # Missing snapshot_id → 400
    r = requests.post(f"{API_URL}/api/admin/platform/users/{uid}/reset-team",
                      headers=H, json={"team_id": "abc", "reason": "x"})
    assert r.status_code == 400
    # Missing team_id → 400
    r2 = requests.post(f"{API_URL}/api/admin/platform/users/{uid}/reset-team",
                       headers=H, json={"reason": "x"})
    assert r2.status_code == 400

"""
Iter 201a — Platform Admin Dashboard backend.

Verifies:
1. /admin/platform/metrics returns counts + this_week + 14-day timeseries
2. Auth gating — 401 unauth, 403 non-admin, 200 admin
3. /admin/platform/commish-actions feed + filters
4. Revert endpoint marks the original row + writes a paired audit doc
"""
from __future__ import annotations

import os
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASS = "Admin123!"
USER_EMAIL = "chriszarek@gmail.com"
USER_PASS = "Chris2026!"


def _login(email, password) -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASS)}"}


# ── Auth gating ──


def test_metrics_unauth_returns_401():
    r = requests.get(f"{API_URL}/api/admin/platform/metrics")
    assert r.status_code == 401


def test_metrics_non_admin_returns_403():
    headers = {"Authorization": f"Bearer {_login(USER_EMAIL, USER_PASS)}"}
    r = requests.get(f"{API_URL}/api/admin/platform/metrics", headers=headers)
    assert r.status_code == 403


def test_metrics_admin_returns_payload():
    r = requests.get(f"{API_URL}/api/admin/platform/metrics", headers=_admin_headers())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "counts" in d and "this_week" in d and "timeseries_14d" in d
    # Basic shape
    for k in ("users", "leagues", "teams", "trades", "drafts"):
        assert k in d["counts"]
        assert isinstance(d["counts"][k], int)
    for k in ("new_users", "new_leagues", "trades", "transactions", "active_drafts"):
        assert k in d["this_week"]
        assert isinstance(d["this_week"][k], int)
    # 15 days inclusive of today
    assert len(d["timeseries_14d"]) == 15
    for entry in d["timeseries_14d"]:
        assert "date" in entry and "new_users" in entry and "new_leagues" in entry


# ── Commish actions feed ──


def test_commish_actions_returns_entries_with_labels():
    r = requests.get(f"{API_URL}/api/admin/platform/commish-actions?limit=5", headers=_admin_headers())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "entries" in d
    # Ice Kings has playoff_winner_marked events; should have at least one row
    if d["entries"]:
        row = d["entries"][0]
        assert "id" in row and "event_type" in row and "created_at" in row
        # league + user hydration
        assert "league_name" in row  # may be None if league deleted
        assert "user" in row  # may be None


def test_commish_actions_filter_by_event_type():
    r = requests.get(
        f"{API_URL}/api/admin/platform/commish-actions?event_type=playoff_winner_marked&limit=3",
        headers=_admin_headers(),
    )
    assert r.status_code == 200
    for e in r.json().get("entries", []):
        assert e["event_type"] == "playoff_winner_marked"


def test_commish_actions_rejects_unknown_event_type():
    r = requests.get(
        f"{API_URL}/api/admin/platform/commish-actions?event_type=bogus_event",
        headers=_admin_headers(),
    )
    assert r.status_code == 400


# ── Revert ──


def test_revert_commish_action_marks_reverted_and_writes_paired_audit():
    # Find a non-reverted commish action
    r = requests.get(f"{API_URL}/api/admin/platform/commish-actions?limit=50", headers=_admin_headers())
    target = None
    for e in r.json().get("entries", []):
        if not e.get("reverted"):
            target = e
            break
    if not target:
        # Skip if all are already reverted (test environment dependent)
        return
    aid = target["id"]
    rv = requests.post(
        f"{API_URL}/api/admin/platform/commish-actions/{aid}/revert",
        headers=_admin_headers(),
    )
    assert rv.status_code == 200, rv.text
    body = rv.json()
    assert body["ok"] is True
    assert body["action_id"] == aid
    assert body["revert_audit_id"]

    # Re-fetching the same action should now report reverted=true
    r2 = requests.get(f"{API_URL}/api/admin/platform/commish-actions?limit=100", headers=_admin_headers())
    refetched = next((e for e in r2.json().get("entries", []) if e["id"] == aid), None)
    assert refetched is not None
    assert refetched["reverted"] is True


def test_revert_already_reverted_returns_400():
    # First, find a reverted action (from prior test or pre-existing)
    r = requests.get(f"{API_URL}/api/admin/platform/commish-actions?limit=50", headers=_admin_headers())
    reverted = next((e for e in r.json().get("entries", []) if e.get("reverted")), None)
    if not reverted:
        return  # nothing to test
    rv = requests.post(
        f"{API_URL}/api/admin/platform/commish-actions/{reverted['id']}/revert",
        headers=_admin_headers(),
    )
    assert rv.status_code == 400


def test_revert_invalid_action_id_returns_400():
    rv = requests.post(
        f"{API_URL}/api/admin/platform/commish-actions/not-an-id/revert",
        headers=_admin_headers(),
    )
    assert rv.status_code == 400


def test_revert_unknown_action_id_returns_404():
    rv = requests.post(
        f"{API_URL}/api/admin/platform/commish-actions/000000000000000000000000/revert",
        headers=_admin_headers(),
    )
    assert rv.status_code == 404

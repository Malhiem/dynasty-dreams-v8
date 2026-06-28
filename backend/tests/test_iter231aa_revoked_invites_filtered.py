"""Iter 231aa — list_league_team_invites hides revoked invites by default.

User reported (after iter 231z): "Revoke functionality still not operating
as intended." Investigation found that even after the sidebar route was
fixed to render the live TeamsTab, the listing endpoint
`/api/leagues/{league_id}/team-invites` returned REVOKED invites in the
default response. The frontend rendered them as pending → clicking
revoke on an already-revoked invite was a silent backend no-op (revoke
endpoint is idempotent), the toast said success, but the row never
disappeared because the next list() round-tripped the same revoked
invite right back.

Fix: list_league_team_invites filters out `status=="revoked"` by default;
audit views can opt-in with `?include_revoked=true`. Belt-and-suspenders
client-side filter added in TeamsTab.load() too.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


def _api_url():
    return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


# ─── Source-grep guards ────────────────────────────────────────────


def test_list_endpoint_accepts_include_revoked_flag():
    from pathlib import Path
    src = Path("/app/backend/routes/team_invites.py").read_text()
    assert "include_revoked: bool = False" in src
    assert 'if not include_revoked and status == "revoked":' in src
    # Comment must explain the iter231aa context.
    assert "Iter 231aa" in src


def test_frontend_also_filters_revoked_invites_defense_in_depth():
    from pathlib import Path
    src = Path("/app/frontend/src/lovable/components/admin/TeamsTab.tsx").read_text()
    # Client-side guard so any legacy server still returning revoked
    # invites won't break the page.
    assert 'inv?.status === "revoked"' in src


# ─── Functional test against the live backend ─────────────────────


def _register_via_api(email_prefix: str):
    """Register a fresh user + JWT for the test."""
    import requests
    suffix = uuid.uuid4().hex[:8]
    email = f"i231aa_{email_prefix}_{suffix}@example.com"
    username = f"i231aa_{email_prefix[:6]}_{suffix}"[:24]
    r = requests.post(
        f"{_api_url()}/api/auth/register",
        json={"email": email, "password": "Iter231aaTest123!", "username": username, "name": f"i231aa {email_prefix}"},
        timeout=10,
    )
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    data = r.json()
    uid = data.get("user", {}).get("_id") or data.get("user", {}).get("id") or data.get("id")
    return uid, data["access_token"]


@pytest.mark.asyncio
async def test_revoked_invites_hidden_by_default_listed_with_flag():
    """End-to-end: create a league + team + invite, revoke the invite,
    then assert the default listing excludes it and the audit listing
    includes it."""
    import requests
    db = _db()
    user_id, token = _register_via_api("comm")
    H = {"Authorization": f"Bearer {token}"}

    league_id_obj = ObjectId()
    league_id = str(league_id_obj)
    await db.leagues.insert_one({
        "_id": league_id_obj, "name": f"i231aa League {league_id}",
        "commissioner_id": user_id, "status": "active",
    })
    team_id_obj = ObjectId()
    team_id = str(team_id_obj)
    await db.teams.insert_one({
        "_id": team_id_obj, "name": "i231aa Team", "league_id": league_id,
        "owner_id": None, "roster": [],
    })

    try:
        # Mint invite via the real endpoint.
        r = requests.post(
            f"{_api_url()}/api/leagues/{league_id}/teams/{team_id}/invites",
            json={"email": "rev_target@example.com", "role": "owner"},
            headers=H, timeout=10,
        )
        assert r.status_code in (200, 201), r.text
        inv_id = r.json()["id"]

        # Sanity: default list includes the pending invite.
        r = requests.get(
            f"{_api_url()}/api/leagues/{league_id}/team-invites",
            headers=H, timeout=10,
        )
        body = r.json()
        assert any(i["id"] == inv_id and i["status"] == "pending" for i in body["invites"])

        # Revoke it.
        r = requests.delete(f"{_api_url()}/api/team-invites/{inv_id}", headers=H, timeout=10)
        assert r.status_code == 200, r.text

        # Default list MUST NOT include the revoked invite (this is the
        # fix). Before iter231aa it would still appear with status=revoked.
        r = requests.get(
            f"{_api_url()}/api/leagues/{league_id}/team-invites",
            headers=H, timeout=10,
        )
        default_body = r.json()
        assert not any(i["id"] == inv_id for i in default_body["invites"]), (
            "Revoked invite should be hidden from default listing"
        )

        # With include_revoked=true it must appear (for audit views).
        r = requests.get(
            f"{_api_url()}/api/leagues/{league_id}/team-invites?include_revoked=true",
            headers=H, timeout=10,
        )
        audit_body = r.json()
        revoked_match = next((i for i in audit_body["invites"] if i["id"] == inv_id), None)
        assert revoked_match is not None
        assert revoked_match["status"] == "revoked"
    finally:
        await db.leagues.delete_one({"_id": league_id_obj})
        await db.teams.delete_one({"_id": team_id_obj})
        await db.users.delete_one({"_id": ObjectId(user_id)})
        await db.team_invites.delete_many({"league_id": league_id})

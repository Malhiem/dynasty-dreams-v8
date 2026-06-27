"""Iter 231f — Archived drafts must NOT be resurrected by auto-init or start.

Background: user reported a draft "running" in their Ice Kings H2H league
that they had archived 2 days earlier. Investigation surfaced two
compounding bugs:

  1. `auto_init_draft` returned ANY existing draft for the league,
     including archived ones. So when the commissioner opened the Draft
     Room after archiving, they saw the archived draft as if it were
     live.
  2. `start_draft` had no `status == "archived"` guard. Combined with
     bug #1, the auto-init → materialise → start flow happily flipped
     the archived draft back to `status: "active"`.

Fix: both endpoints now reject archived drafts. Auto-init excludes them
from the "existing" lookup; start_draft refuses to activate them.
"""
import os
import random
import pytest
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
pytestmark = pytest.mark.asyncio


async def _register(client, suffix):
    suf = f"{suffix}_{random.randint(10000, 99999)}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": f"u_{suf}",
            "email": f"u_{suf}@example.com",
            "password": "TestPass123!",
        },
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _create_league(client, token, suffix):
    r = await client.post(
        "/api/leagues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"TEST_Iter231f_{suffix}_{random.randint(10000, 99999)}",
            "season": "2026",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "roster_spots": 10,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_auto_init_excludes_archived_drafts():
    """When the only existing draft is archived, auto-init must return
    a preview (or commit fresh) — NOT the archived draft."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "f_autoinit")
        league_id = await _create_league(client, token, "autoinit")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Commit a real draft.
        r1 = await client.post(
            f"/api/drafts/auto-init/{league_id}?commit=true",
            headers=headers,
        )
        assert r1.status_code == 200, r1.text
        draft_id = r1.json()["draft"]["_id"]
        assert draft_id

        # 2. Archive it.
        ra = await client.delete(f"/api/drafts/{draft_id}", headers=headers)
        assert ra.status_code == 200, ra.text

        # 3. Default auto-init must NOT return the archived draft — it
        # should now return a preview because the only existing row is
        # archived.
        r2 = await client.post(
            f"/api/drafts/auto-init/{league_id}",
            headers=headers,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        # Either preview=true (no other live draft exists) OR a NEW
        # different draft id — but NEVER the archived one.
        returned_id = body["draft"]["_id"]
        assert returned_id != draft_id, (
            f"auto-init returned the archived draft id {draft_id} — "
            f"archived drafts must be excluded from the existing-draft lookup."
        )


async def test_auto_init_commit_does_not_resurrect_archived():
    """Even with `commit=true`, auto-init must not surface the archived
    draft. Instead it should materialise a fresh one."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "f_commit")
        league_id = await _create_league(client, token, "commit")
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await client.post(f"/api/drafts/auto-init/{league_id}?commit=true", headers=headers)
        archived_id = r1.json()["draft"]["_id"]
        ra = await client.delete(f"/api/drafts/{archived_id}", headers=headers)
        assert ra.status_code == 200

        r2 = await client.post(f"/api/drafts/auto-init/{league_id}?commit=true", headers=headers)
        assert r2.status_code == 200
        new_id = r2.json()["draft"]["_id"]
        assert new_id != archived_id, "commit=true must not surface archived drafts"


async def test_start_draft_rejects_archived():
    """Even if a caller obtains an archived draft id directly,
    /drafts/{id}/start must refuse to activate it (defense in depth)."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "f_start")
        league_id = await _create_league(client, token, "start")
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await client.post(f"/api/drafts/auto-init/{league_id}?commit=true", headers=headers)
        draft_id = r1.json()["draft"]["_id"]
        # Archive
        await client.delete(f"/api/drafts/{draft_id}", headers=headers)

        # Try to start the archived draft.
        rs = await client.post(
            f"/api/drafts/{draft_id}/start?early_start=true",
            headers=headers,
        )
        assert rs.status_code == 400, (
            f"start_draft should reject archived drafts with 400; got {rs.status_code}: {rs.text}"
        )
        body = rs.json()
        assert "archived" in (body.get("detail") or "").lower()


async def test_restored_draft_can_be_started_normally():
    """Sanity — once restored, the draft regains normal start semantics."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "f_restore")
        league_id = await _create_league(client, token, "restore")
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await client.post(f"/api/drafts/auto-init/{league_id}?commit=true", headers=headers)
        draft_id = r1.json()["draft"]["_id"]
        # Archive then restore
        await client.delete(f"/api/drafts/{draft_id}", headers=headers)
        rr = await client.post(f"/api/drafts/{draft_id}/restore", headers=headers)
        assert rr.status_code == 200, rr.text

        # Now start succeeds.
        rs = await client.post(
            f"/api/drafts/{draft_id}/start?early_start=true",
            headers=headers,
        )
        assert rs.status_code == 200, (
            f"restored draft should be startable; got {rs.status_code}: {rs.text}"
        )

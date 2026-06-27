"""Iter 231 — `auto_init_draft` returns a preview WITHOUT persisting.

Background: opening the Draft Room used to call `POST /drafts/auto-init/
{league_id}` which created an empty stub draft on every visit. With a
commissioner-only gate, that stub was harmless data noise but it made
the Draft Room UI report a phantom "draft scheduled" state for leagues
that hadn't actually configured anything yet.

Fix: `commit=False` (the default) now returns a preview shape WITHOUT
writing to the database. The frontend Draft Room renders the board
from the preview so commissioners can still see what their draft will
look like. Materialisation happens only when the commissioner takes an
explicit action (clicking Start / Schedule).
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
    # Iter 230y noted: register response id may drift; re-read /auth/me to
    # get the actually-authenticated user id. Also clear cookies so the
    # Bearer header wins on subsequent calls (iter 230ac fix).
    client.cookies.clear()
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["id"]


async def _create_league_with_teams(client, token, suffix, n_teams=3):
    """Create a league via POST /api/leagues, then add teams."""
    r = await client.post(
        "/api/leagues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"TEST_Iter231Preview_{suffix}_{random.randint(10000, 99999)}",
            "season": "2026",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "roster_spots": 18,
            "bench_spots": 4,
            "minors_spots": 4,
        },
    )
    assert r.status_code == 200, r.text
    league_id = r.json()["id"]
    # Add additional teams beyond the commissioner's auto-created one.
    for i in range(1, n_teams):
        await client.post(
            "/api/teams",
            headers={"Authorization": f"Bearer {token}"},
            json={"league_id": league_id, "name": f"Bot Team {i}", "logo_abbr": f"BT{i}"},
        )
    return league_id


async def test_auto_init_preview_does_not_persist():
    """Default `auto_init_draft` call returns preview WITHOUT a DB row."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "previewcommish")
        league_id = await _create_league_with_teams(client, token, "preview")

        # Count drafts BEFORE the preview call.
        r0 = await client.get(
            f"/api/drafts?league_id={league_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        before = len((r0.json() or {}).get("drafts") or r0.json() or [])

        r = await client.post(
            f"/api/drafts/auto-init/{league_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("preview") is True, f"expected preview=true, got {body}"
        assert body.get("created") is False
        assert body["draft"]["_id"] is None
        assert body["draft"]["status"] == "preview"
        assert body["draft"]["league_id"] == league_id
        assert len(body["draft"]["team_abbrs"]) >= 1
        # total_rounds derived from the league's roster capacity. The
        # default create-league endpoint accepts `roster_spots` but
        # ignores bench / minors at this layer, so 18 is the value we
        # expect for an 18-spot starting roster with no bench/minors.
        assert body["draft"]["total_rounds"] == 18

        # CRITICAL — no DB write happened. The list of drafts for this
        # league is unchanged.
        r1 = await client.get(
            f"/api/drafts?league_id={league_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        after = len((r1.json() or {}).get("drafts") or r1.json() or [])
        assert after == before, f"preview must not persist a draft row (before={before}, after={after})"


async def test_auto_init_commit_true_persists():
    """`auto_init_draft?commit=true` materialises the draft into the DB."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "commitcommish")
        league_id = await _create_league_with_teams(client, token, "commit")

        r = await client.post(
            f"/api/drafts/auto-init/{league_id}?commit=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("created") is True, f"expected created=true, got {body}"
        assert body.get("preview") is not True
        assert body["draft"]["_id"] is not None
        assert body["draft"]["status"] == "scheduled"


async def test_auto_init_idempotent_when_committed_draft_exists():
    """When a real draft exists, the default (no-commit) call still
    returns it as-is — no preview ever shadows an already-materialised
    draft, and no duplicate is created."""
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "idempcommish")
        league_id = await _create_league_with_teams(client, token, "idemp")

        # Commit once.
        r1 = await client.post(
            f"/api/drafts/auto-init/{league_id}?commit=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200, r1.text
        first_id = r1.json()["draft"]["_id"]
        assert first_id is not None

        # Default (no commit) call should now return the SAME draft.
        r2 = await client.post(
            f"/api/drafts/auto-init/{league_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2.get("preview") is not True
        assert body2["draft"]["_id"] == first_id

        # Commit-true call also dedupes.
        r3 = await client.post(
            f"/api/drafts/auto-init/{league_id}?commit=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r3.json()["draft"]["_id"] == first_id


async def test_auto_init_non_commissioner_still_403():
    """The commissioner gate stays intact — preview mode does NOT relax it."""
    async with AsyncClient(base_url=BASE) as client:
        # Commissioner creates the league.
        token_a, _ = await _register(client, "ownercommish")
        league_id = await _create_league_with_teams(client, token_a, "perm")
        # Different user (non-commissioner) tries to auto-init.
        token_b, _ = await _register(client, "intruder")
        r = await client.post(
            f"/api/drafts/auto-init/{league_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 403
        assert "commissioner" in r.json()["detail"].lower()

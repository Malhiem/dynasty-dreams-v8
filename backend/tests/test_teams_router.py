"""Focused unit tests for `routes/teams.py`.

Covers the metadata-edit endpoints (name, abbreviation, URL logo, file logo
upload, logo deletion). Each test runs against an ephemeral test database
that's dropped on exit.
"""
import base64
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import teams as teams_routes  # noqa: E402

from tests.router_test_utils import (  # noqa: E402
    isolated_router_app,
    seed_league,
    seed_team,
)


def _tiny_png_bytes() -> bytes:
    """Build a minimal valid PNG using Pillow.

    Tiny means tiny — we just need the upload path to accept it and exercise
    the resize/encode pipeline.
    """
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 210, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_put_team_updates_name_and_abbr_uppercases_abbr():
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id, name="Old Name")
        r = await ctx.client.put(
            f"/api/teams/{team_id}",
            json={"name": "New Name", "logo_abbr": "abc"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] is True
        assert body["changes"]["name"]["to"] == "New Name"
        # Abbreviation validator upper-cases and trims to 3 chars.
        assert body["changes"]["logo_abbr"]["to"] == "ABC"
        # Verify Mongo persistence
        from bson import ObjectId
        doc = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert doc["name"] == "New Name"
        assert doc["logo_abbr_override"] == "ABC"


@pytest.mark.asyncio
async def test_put_team_rejects_non_owner():
    """Only the team owner can edit metadata."""
    async with isolated_router_app(
        teams_routes,
        user={"_id": "intruder", "id": "intruder", "name": "Intruder"},
    ) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id, owner_id="real_owner")
        r = await ctx.client.put(f"/api/teams/{team_id}", json={"name": "Hacked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_put_team_validates_abbr_alphanumeric():
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        # Spaces / punctuation should be rejected by the field validator,
        # which surfaces as a 422 Unprocessable Entity.
        r = await ctx.client.put(f"/api/teams/{team_id}", json={"logo_abbr": "A B"})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_team_accepts_url_logo():
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        url = "https://example.com/logo.png"
        r = await ctx.client.put(f"/api/teams/{team_id}", json={"logo_url": url})
        assert r.status_code == 200
        from bson import ObjectId
        doc = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert doc["logo_url"] == url


@pytest.mark.asyncio
async def test_post_logo_rejects_oversize_upload():
    """Files over the 1 MB cap must 400 — protects from runaway base64 blobs."""
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        big = b"x" * (teams_routes.MAX_LOGO_BYTES + 1)
        r = await ctx.client.post(
            f"/api/teams/{team_id}/logo",
            files={"file": ("big.png", big, "image/png")},
        )
        assert r.status_code == 400
        assert "too large" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_logo_rejects_unsupported_mime():
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        r = await ctx.client.post(
            f"/api/teams/{team_id}/logo",
            files={"file": ("logo.bmp", b"bmpdata", "image/bmp")},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_post_logo_happy_path_stores_data_url():
    """Valid PNG uploads should round-trip through Pillow and persist as a
    `data:image/png;base64,...` string on the team document.
    """
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        png = _tiny_png_bytes()
        r = await ctx.client.post(
            f"/api/teams/{team_id}/logo",
            files={"file": ("logo.png", png, "image/png")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["logo_url"].startswith("data:image/png;base64,")
        # Decoding the base64 prefix must succeed.
        b64 = body["logo_url"].split(",", 1)[1]
        base64.b64decode(b64)


@pytest.mark.asyncio
async def test_delete_logo_clears_field():
    async with isolated_router_app(teams_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        # Pre-seed a logo URL.
        from bson import ObjectId
        await ctx.db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {"$set": {"logo_url": "https://example.com/x.png"}},
        )
        r = await ctx.client.delete(f"/api/teams/{team_id}/logo")
        assert r.status_code == 200
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert team.get("logo_url") in (None, "")


@pytest.mark.asyncio
async def test_owner_summaries_exclude_other_owners_and_financial_fields():
    async with isolated_router_app(teams_routes, user={"_id": "summary-owner", "id": "summary-owner", "name": "Owner"}) as ctx:
        league_id = await seed_league(ctx.db)
        own_id = await seed_team(ctx.db, league_id=league_id, owner_id="summary-owner", name="Mine")
        await seed_team(ctx.db, league_id=league_id, owner_id="another-owner", name="Other")
        response = await ctx.client.get("/api/teams/mine/summaries")
        assert response.status_code == 200, response.text
        assert [team["id"] for team in response.json()] == [own_id]
        assert response.json()[0]["name"] == "Mine"
        assert "roster" not in response.json()[0]
        assert "salary_used" not in response.json()[0]


@pytest.mark.asyncio
async def test_owner_summaries_require_authentication():
    async with isolated_router_app(teams_routes) as ctx:
        original = teams_routes._deps["get_current_user"]
        async def anonymous(request):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Not authenticated")
        teams_routes._deps["get_current_user"] = anonymous
        try:
            response = await ctx.client.get("/api/teams/mine/summaries")
            assert response.status_code == 401
        finally:
            teams_routes._deps["get_current_user"] = original

"""Admin-created status must remain discoverable through verification filters."""
import os
import pytest
from bson import ObjectId
from routes import admin_players, admin
from tests.router_test_utils import isolated_router_app

@pytest.mark.asyncio
async def test_admin_created_league_status_survives_verification_and_audit():
    user = {"_id": str(ObjectId()), "role": "admin", "email": os.environ["ADMIN_EMAIL"]}
    async with isolated_router_app((admin_players, admin), user=user) as ctx:
        response = await ctx.client.post("/api/admin/players", json={
            "name": "Status Roundtrip", "position": "RW", "team": "SKA", "league_status": "Europe"})
        assert response.status_code == 200, response.text
        created = response.json()
        assert created["league_status"] == "Europe"
        filtered = await ctx.client.get("/api/admin/players/verify", params={"league_status": "Europe", "search": "Status Roundtrip"})
        assert filtered.status_code == 200, filtered.text
        assert [p["name"] for p in filtered.json()["players"]] == ["Status Roundtrip"]
        audit = await ctx.db.player_admin_audit.find_one({"player_id": created["id"], "action": "create"})
        assert audit["after"]["league_status"] == "Europe"
        hidden = await ctx.client.get("/api/admin/players/verify", params={"league_status": "AHL", "search": "Status Roundtrip"})
        assert hidden.json()["players"] == []

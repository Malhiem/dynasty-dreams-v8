"""Verify waiver processing emits both waiver_won (with competing_claims) and
waiver_lost activity rows surfaced via /api/leagues/{id}/transactions."""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()


BASE = _backend_url()


@pytest.mark.asyncio
async def test_waiver_lost_and_competing_claims_in_transactions():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        # login as chris (commissioner of Ice Kings)
        r = await c.post("/api/auth/login",
                         json={"email": "chriszarek@gmail.com", "password": "Chris2026!"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}

        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        # Chris isn't a commissioner in seed data — temporarily promote him on
        # one of his leagues so we can hit the commissioner-only process route.
        # We restore the original commissioner_id at the end of the test.
        me = (await c.get("/api/auth/me", headers=h)).json()
        chris_uid = me["id"]
        league = leagues[0]
        lid = league["id"]
        original_commish_id = league.get("commissioner_id")
        await db.leagues.update_one(
            {"_id": ObjectId(lid)},
            {"$set": {"commissioner_id": chris_uid}},
        )

        # Find a player not on any roster in this league (waiver-eligible).
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        all_roster = set()
        for t in teams:
            all_roster.update(t.get("roster", []))
        free_player = await db.players.find_one(
            {"_id": {"$nin": [ObjectId(p) for p in all_roster if ObjectId.is_valid(p)]}},
            {"name": 1},
        )
        assert free_player, "No free player found"
        pid = str(free_player["_id"])

        team_a, team_b = teams[0], teams[1]

        # Clear any pending claims for this player to ensure a clean run.
        await db.waiver_claims.delete_many({"league_id": lid, "player_id": pid})

        # Seed two competing claims directly in the DB so we don't depend on
        # the public endpoint's auth / FAAB pre-checks.
        await db.waiver_claims.insert_many([
            {
                "league_id": lid,
                "team_id": str(team_a["_id"]),
                "team_name": team_a["name"],
                "player_id": pid,
                "player_name": free_player["name"],
                "bid_amount": 25,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "league_id": lid,
                "team_id": str(team_b["_id"]),
                "team_name": team_b["name"],
                "player_id": pid,
                "player_name": free_player["name"],
                "bid_amount": 10,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
            },
        ])
        # Ensure team_a has FAAB budget (engine decrements remaining).
        await db.waiver_budgets.update_one(
            {"team_id": str(team_a["_id"]), "league_id": lid},
            {"$set": {
                "team_id": str(team_a["_id"]), "league_id": lid,
                "spent": 0, "remaining": 1000,
            }},
            upsert=True,
        )

        # Process waivers as commissioner.
        r = await c.post(f"/api/waivers/process?league_id={lid}", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["processed"] >= 1

        # Pull transactions and find both rows.
        r = await c.get(f"/api/leagues/{lid}/transactions?limit=100", headers=h)
        txns = r.json()["transactions"]
        won = next(
            (t for t in txns
             if t["type"] == "waiver_won"
             and t.get("player_name") == free_player["name"]),
            None,
        )
        lost = next(
            (t for t in txns
             if t["type"] == "waiver_lost"
             and t.get("player_name") == free_player["name"]),
            None,
        )
        assert won, f"Expected a waiver_won row for {free_player['name']}"
        assert lost, f"Expected a waiver_lost row for {free_player['name']}"

        # Winning row should expose competing_claims (one losing team).
        assert isinstance(won.get("competing_claims"), list)
        assert any(
            cc.get("team_name") == team_b["name"] and cc.get("bid_amount") == 10
            for cc in won["competing_claims"]
        ), f"competing_claims missing team_b: {won.get('competing_claims')}"

        # Losing row should expose winning_team_name + winning_bid.
        assert lost.get("winning_team_name") == team_a["name"]
        assert lost.get("winning_bid") == 25

        # Restore original commissioner.
        if original_commish_id:
            await db.leagues.update_one(
                {"_id": ObjectId(lid)},
                {"$set": {"commissioner_id": original_commish_id}},
            )

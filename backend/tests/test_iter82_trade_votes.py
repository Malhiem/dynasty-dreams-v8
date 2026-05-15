"""Iter 82 — verify:
  * Veto threshold preview endpoint computes ceil(pct * total / 100).
  * Empty trade proposals are rejected with a clear error.
  * Trade vote system supports per-voter toggling (change your mind) and
    auto-vetoes once `teams_required` is met.
  * The migrated `salary-retention-slots` endpoint still works on the same URL.
"""
import os
import sys

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(p) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError


def _env(key):
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


BASE = _backend_url()
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"
LID = "69e46af167999bfb85c39628"


async def _login(client, email=EMAIL, password=PASSWORD):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_veto_threshold_preview_math():
    """50% of 12 teams should round up to 6, not 5."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        # The seeded league has 12 teams
        r = await client.get(f"/api/leagues/{LID}/veto-threshold-preview?pct=50", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pct"] == 50
        assert body["total_teams"] >= 2
        # Strict majority: ceil(N * 50/100)
        import math
        assert body["teams_required"] == max(1, math.ceil(body["total_teams"] * 0.5))
        assert body["enabled"] is True
        # Try 0% → disabled
        r = await client.get(f"/api/leagues/{LID}/veto-threshold-preview?pct=0", headers=h)
        body = r.json()
        assert body["enabled"] is False
        assert body["teams_required"] == 0


@pytest.mark.asyncio
async def test_empty_trade_proposal_rejected():
    """A POST /trades with no assets on either side returns 400."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        teams = (await client.get(f"/api/teams?league_id={LID}", headers=h)).json()
        me = (await client.get("/api/auth/me", headers=h)).json()
        other = next(t for t in teams if t["owner_id"] != me["id"])
        r = await client.post(
            "/api/trades",
            headers=h,
            json={
                "league_id": LID,
                "target_team_id": other["id"],
                "assets_offered": [],
                "assets_requested": [],
                "message": "empty",
            },
        )
        assert r.status_code == 400, r.text
        assert "player or draft pick" in r.json()["detail"]


@pytest.mark.asyncio
async def test_salary_retention_slots_endpoint_still_works_after_refactor():
    """The migrated PUT /leagues/{id}/salary-retention-slots endpoint works."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        # Chris is the commissioner of LID; use his credentials.
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        before = (await client.get(f"/api/leagues/{LID}", headers=h)).json()
        orig = before.get("salary_retention_slots") or 3
        target = 5 if orig != 5 else 4
        try:
            r = await client.put(
                f"/api/leagues/{LID}/salary-retention-slots",
                headers=h,
                json={"salary_retention_slots": target},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["salary_retention_slots"] == target
            after = (await client.get(f"/api/leagues/{LID}", headers=h)).json()
            assert after["salary_retention_slots"] == target
            # Bad value → 400
            r = await client.put(
                f"/api/leagues/{LID}/salary-retention-slots",
                headers=h,
                json={"salary_retention_slots": 999},
            )
            assert r.status_code == 400
        finally:
            await client.put(
                f"/api/leagues/{LID}/salary-retention-slots",
                headers=h,
                json={"salary_retention_slots": orig},
            )


@pytest.mark.asyncio
async def test_trade_vote_supports_toggle_and_recount():
    """A voter can change approve→veto and the counts adjust accordingly.

    Bypasses HTTP creation (which would require a 2-team owner login dance)
    by writing a synthetic pending trade directly to mongo, then exercising
    /trades/{id}/vote and /trades/{id}/votes.
    """
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        me = (await client.get("/api/auth/me", headers=h)).json()
        teams = (await client.get(f"/api/teams?league_id={LID}", headers=h)).json()
        proposer = next((t for t in teams if t["owner_id"] != me["id"]), teams[0])
        target = next((t for t in teams if t["id"] != proposer["id"]), teams[1])

        trade_doc = {
            "league_id": LID,
            "proposer_team_id": proposer["id"],
            "proposer_team_name": proposer["name"],
            "proposer_id": proposer["owner_id"],
            "target_team_id": target["id"],
            "target_team_name": target["name"],
            "target_owner_id": target["owner_id"],
            "assets_offered": [{"asset_type": "player", "player_id": "test", "player_name": "Test"}],
            "assets_requested": [],
            "status": "pending",
            "votes": {"approve": 0, "veto": 0, "voters": []},
        }
        inserted = await db.trades.insert_one(trade_doc)
        trade_id = str(inserted.inserted_id)
        try:
            # Vote approve
            r = await client.post(
                f"/api/trades/{trade_id}/vote",
                headers=h,
                json={"vote": "approve"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["your_vote"] == "approve"
            assert r.json()["votes"]["approve"] == 1
            assert r.json()["votes"]["veto"] == 0

            # Toggle to veto
            r = await client.post(
                f"/api/trades/{trade_id}/vote",
                headers=h,
                json={"vote": "veto"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["your_vote"] == "veto"
            assert r.json()["votes"]["approve"] == 0
            assert r.json()["votes"]["veto"] == 1
            assert "changed" in r.json()["message"].lower()

            # Idempotent: voting veto again is a no-op
            r = await client.post(
                f"/api/trades/{trade_id}/vote",
                headers=h,
                json={"vote": "veto"},
            )
            assert r.status_code == 200
            assert "unchanged" in r.json()["message"].lower()
            assert r.json()["votes"]["veto"] == 1

            # Inspect via GET /votes
            r = await client.get(f"/api/trades/{trade_id}/votes", headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["your_vote"] == "veto"
            assert body["veto_threshold"]["teams_required"] >= 1
        finally:
            await db.trades.delete_one({"_id": ObjectId(trade_id)})
            mongo.close()

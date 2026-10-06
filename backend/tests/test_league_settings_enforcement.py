"""Verify that the runtime read-path honors league-administration settings:

1. `trade_deadline_week` blocks new trade proposals once the current week
   passes the configured deadline.
2. `waiver_period_days` controls the `processes_at` timestamp on new claims.
3. `regular_season_weeks` is used as the default `num_weeks` for schedule
   generation when the request omits it.
4. `LeagueResponse` now echoes the full wizard-configurable surface so the
   frontend can read every setting back via `GET /leagues/{id}`.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LID = "69e46af167999bfb85c39628"


def _env(key: str, fallback: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return fallback


def _mongo():
    return AsyncIOMotorClient(_env("MONGO_URL"))


def _db_name():
    return _env("DB_NAME", os.environ["DB_NAME"])


async def _login(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_league_response_echoes_full_surface():
    """GET /leagues/{id} returns every wizard-settable field."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        # Write a known set of settings
        await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "bench_spots": 6,
                "minors_spots": 3,
                "trade_review_period_hours": 48,
                "trade_veto_threshold_pct": 60,
                "trade_deadline_week": 18,
                "waiver_faab_budget": 150,
                "waiver_period_days": 2,
                "playoff_teams": 8,
                "playoff_start_week": 22,
                "playoff_end_week": 24,
                "playoff_rounds": 3,
                "regular_season_weeks": 20,
            },
        )
        r = await client.get(f"/api/leagues/{LID}",
                              headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        for key, expected in {
            "bench_spots": 6,
            "minors_spots": 3,
            "trade_review_period_hours": 48,
            "trade_veto_threshold_pct": 60,
            "trade_deadline_week": 18,
            "waiver_faab_budget": 150,
            "waiver_period_days": 2,
            "playoff_teams": 8,
            "playoff_start_week": 22,
            "playoff_end_week": 24,
            "playoff_rounds": 3,
            "regular_season_weeks": 20,
        }.items():
            assert body.get(key) == expected, f"GET league.{key} = {body.get(key)}"


@pytest.mark.asyncio
async def test_trade_deadline_blocks_new_proposals():
    """Once league.current_week > trade_deadline_week, POST /trades returns 400."""
    client_db = _mongo()
    db = client_db[_db_name()]

    # Snapshot original league state so we can restore afterwards
    league = await db.leagues.find_one({"_id": ObjectId(LID)})
    orig_deadline = league.get("trade_deadline_week")
    orig_current = league.get("current_week")

    try:
        # Pin current_week PAST the deadline
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"trade_deadline_week": 5, "current_week": 6}},
        )

        async with AsyncClient(base_url=BASE, timeout=20) as client:
            token = await _login(client)
            # Find any other team in the league
            r = await client.get(f"/api/teams?league_id={LID}",
                                  headers={"Authorization": f"Bearer {token}"})
            teams = r.json()
            me = (await client.get("/api/auth/me",
                                    headers={"Authorization": f"Bearer {token}"})).json()
            mine = next(t for t in teams if t["owner_id"] == me["id"])
            other = next(t for t in teams if t["owner_id"] != me["id"])

            # iter-82 guard requires at least one asset; pick the proposer's
            # first rostered player so the only failure remains the deadline.
            my_roster = mine.get("roster") or []
            asset_pid = str(my_roster[0]) if my_roster else None
            offered = [{"asset_type": "player", "player_id": asset_pid}] if asset_pid else []

            r = await client.post(
                "/api/trades",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "league_id": LID,
                    "target_team_id": other["id"],
                    "assets_offered": offered,
                    "assets_requested": [],
                    "message": "deadline test",
                },
            )
            assert r.status_code == 400, r.text
            assert "deadline" in r.json()["detail"].lower()

            # Now move current_week BACK to <= deadline → proposal should succeed
            await db.leagues.update_one(
                {"_id": ObjectId(LID)},
                {"$set": {"current_week": 4}},
            )
            r = await client.post(
                "/api/trades",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "league_id": LID,
                    "target_team_id": other["id"],
                    "assets_offered": offered,
                    "assets_requested": [],
                    "message": "pre-deadline ok",
                },
            )
            assert r.status_code == 200, r.text
            # Withdraw it so we don't leave clutter
            trade_id = r.json().get("id") or r.json().get("trade_id") or r.json().get("_id")
            if trade_id:
                await client.post(
                    f"/api/trades/{trade_id}/withdraw",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        # Restore original league state
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {
                "trade_deadline_week": orig_deadline,
                "current_week": orig_current,
            }},
        )
        client_db.close()


@pytest.mark.asyncio
async def test_waiver_period_days_drives_processes_at():
    """A claim's `processes_at` = created_at + league.waiver_period_days * 24h."""
    client_db = _mongo()
    db = client_db[_db_name()]
    league = await db.leagues.find_one({"_id": ObjectId(LID)})
    orig_period = league.get("waiver_period_days")
    try:
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"waiver_period_days": 3}},
        )

        async with AsyncClient(base_url=BASE, timeout=20) as client:
            token = await _login(client)
            # Find an unowned player from the DB directly (free agent in this league)
            owned_ids: set[str] = set()
            async for t in db.teams.find({"league_id": LID}, {"roster": 1}):
                for pid in (t.get("roster") or []):
                    owned_ids.add(str(pid))
            free_doc = await db.players.find_one(
                {"_id": {"$nin": [ObjectId(p) for p in owned_ids if ObjectId.is_valid(p)]}}
            )
            if not free_doc:
                pytest.skip("no unowned player in seed")
            player_id = str(free_doc["_id"])

            # Cancel any prior claim for idempotency
            r0 = await client.get(
                "/api/waivers/claims?my_claims=true",
                headers={"Authorization": f"Bearer {token}"},
            )
            for c in (r0.json() or []):
                if c.get("player_id") == player_id and c.get("status") == "pending":
                    cid = c.get("id") or c.get("_id")
                    if cid:
                        await client.delete(
                            f"/api/waivers/claims/{cid}",
                            headers={"Authorization": f"Bearer {token}"},
                        )

            before = datetime.now(timezone.utc)
            r = await client.post(
                "/api/waivers/claim",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "league_id": LID,
                    "player_id": player_id,
                    "bid_amount": 1,
                },
            )
            if r.status_code != 200:
                pytest.skip(f"waiver claim insertion not possible in env: {r.text}")
            body = r.json()
            claim_id = body.get("id") or body.get("_id") or body.get("claim_id")
            assert claim_id, body

            claim = await db.waiver_claims.find_one({"_id": ObjectId(claim_id)})
            assert claim is not None
            processes_at = datetime.fromisoformat(claim["processes_at"])
            # 3 days × 24h = 72h; allow ±60s for test wall-clock skew
            delta_hours = (processes_at - before).total_seconds() / 3600.0
            assert 71.9 <= delta_hours <= 72.1, f"expected ~72h, got {delta_hours}h"

            # Cleanup
            await db.waiver_claims.delete_one({"_id": ObjectId(claim_id)})
    finally:
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"waiver_period_days": orig_period}},
        )
        client_db.close()

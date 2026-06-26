"""
Iter 230w — `upcoming-drafts` includes ACTIVE drafts so a live draft
doesn't silently disappear from the Draft Room picker.

Before this change the endpoint filtered `status: "scheduled"` only.
Real-user bug from chriszarek1: TFHL had an Inaugural draft = active
+ a Winter draft = scheduled. Picker returned only Winter, so the
Draft Room auto-loaded Winter (which was correct per the picker but
catastrophically wrong UX — the manager wanted the live Inaugural).

This test seeds an active + a scheduled draft in the same league and
verifies BOTH surface, with the active one first.
"""
import os
import sys
import pytest
from bson import ObjectId
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _register(client, suffix="iter230w"):
    """Register a throwaway user so we can authenticate the GET."""
    import random
    suf = f"{suffix}_{random.randint(10000, 99999)}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": f"user_{suf}",
            "email": f"user_{suf}@example.com",
            "password": "TestPass123!",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_upcoming_drafts_includes_active_drafts():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # Seed a throwaway league + 2 drafts (1 active in the past, 1
    # scheduled in the future) so the assertions don't depend on any
    # real user's data.
    league_id = str(ObjectId())
    now = datetime.now(timezone.utc)
    active_draft_id = ObjectId()
    scheduled_draft_id = ObjectId()
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "TEST_iter230w_league",
        "commissioner_id": "00000000",
        "current_teams": 0,
    })
    await db.drafts.insert_many([
        {
            "_id": active_draft_id,
            "league_id": league_id,
            "name": "iter230w Active Draft",
            "status": "active",
            # Scheduled time is in the PAST — the old code's horizon
            # check would have excluded this even if status was allowed.
            "scheduled_time": (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
            "started_at": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "picks": [],
        },
        {
            "_id": scheduled_draft_id,
            "league_id": league_id,
            "name": "iter230w Scheduled Draft",
            "status": "scheduled",
            "scheduled_time": (now + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
            "picks": [],
        },
    ])

    try:
        async with AsyncClient(base_url=BASE, timeout=30) as client:
            token = await _register(client)
            h = {"Authorization": f"Bearer {token}"}
            r = await client.get(
                f"/api/leagues/{league_id}/upcoming-drafts?days=30",
                headers=h,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            drafts = body["drafts"]
            names = [d["name"] for d in drafts]

            # Both drafts must appear.
            assert "iter230w Active Draft" in names, names
            assert "iter230w Scheduled Draft" in names, names

            # Active one must be FIRST so the frontend auto-selects it
            # (this is exactly the chriszarek1 / TFHL bug we're fixing).
            assert drafts[0]["name"] == "iter230w Active Draft", (
                "Active draft must surface first so the picker defaults to the live one"
            )
            assert drafts[0]["status"] == "active"
    finally:
        # Always clean up seed data so we don't leak fixtures into the
        # canonical league list.
        await db.drafts.delete_many({"_id": {"$in": [active_draft_id, scheduled_draft_id]}})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})

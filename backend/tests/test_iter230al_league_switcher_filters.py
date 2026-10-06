"""Iter 230al — League switcher filter flags.

Locks the opt-in `exclude_archived` + `exclude_test` query flags on
`GET /api/leagues?my_leagues=true`. These flags are used by the global
CurrentLeague switcher / sidebar to keep automated-test artefacts and
archived leagues out of a user's day-to-day surfaces.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _register_user():
    suffix = uuid.uuid4().hex[:8]
    email = f"iter230al_{suffix}@example.com"
    requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": email, "password": "TestPass123!",
            "username": f"iter230al_{suffix}",
            "name": f"Iter230al {suffix}",
        },
    ).raise_for_status()
    login = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    login.raise_for_status()
    return login.json()["access_token"]


def _create_league(token, *, name):
    r = requests.post(
        f"{API_URL}/api/leagues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name, "format": "dynasty",
            "scoring_format": "head_to_head", "max_teams": 4,
            "draft_type": "snake", "roster_spots": 20,
        },
    )
    r.raise_for_status()
    return r.json()


@pytest.mark.asyncio
async def test_exclude_test_filters_test_prefix_and_iter_pattern():
    """`exclude_test=true` strips leagues named `TEST_*` or
    `IterN ... test` from the response while leaving normal leagues
    untouched."""
    token = _register_user()
    H = {"Authorization": f"Bearer {token}"}

    real = _create_league(token, name=f"Iter230al real league {uuid.uuid4().hex[:4]}")
    test_prefix = _create_league(token, name=f"TEST_iter230al_{uuid.uuid4().hex[:4]}")
    iter_pattern = _create_league(token, name=f"Iter230al health gate test {uuid.uuid4().hex[:4]}")

    try:
        # Without the flag, all three are returned.
        r = requests.get(f"{API_URL}/api/leagues?my_leagues=true", headers=H)
        r.raise_for_status()
        ids = {l["id"] for l in r.json()}
        assert real["id"] in ids
        assert test_prefix["id"] in ids
        assert iter_pattern["id"] in ids

        # With `exclude_test=true`, both test artefacts disappear.
        r = requests.get(
            f"{API_URL}/api/leagues?my_leagues=true&exclude_test=true",
            headers=H,
        )
        r.raise_for_status()
        ids = {l["id"] for l in r.json()}
        assert real["id"] in ids
        assert test_prefix["id"] not in ids
        assert iter_pattern["id"] not in ids
    finally:
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
        for lg in (real, test_prefix, iter_pattern):
            try:
                await db.leagues.delete_one({"_id": ObjectId(lg["id"])})
                await db.teams.delete_many({"league_id": lg["id"]})
            except Exception:
                pass


@pytest.mark.asyncio
async def test_exclude_archived_filters_archived_leagues():
    """`exclude_archived=true` strips leagues marked `archived=True` or
    `status='archived'` from the response."""
    token = _register_user()
    H = {"Authorization": f"Bearer {token}"}

    live = _create_league(token, name=f"Iter230al live {uuid.uuid4().hex[:4]}")
    soon_archived = _create_league(token, name=f"Iter230al soon-archive {uuid.uuid4().hex[:4]}")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]

    try:
        await db.leagues.update_one(
            {"_id": ObjectId(soon_archived["id"])},
            {"$set": {"archived": True, "status": "archived",
                      "archived_at": datetime.now(timezone.utc).isoformat()}},
        )

        # Without flag → both are returned.
        r = requests.get(f"{API_URL}/api/leagues?my_leagues=true", headers=H)
        r.raise_for_status()
        ids = {l["id"] for l in r.json()}
        assert live["id"] in ids
        assert soon_archived["id"] in ids

        # With flag → archived disappears.
        r = requests.get(
            f"{API_URL}/api/leagues?my_leagues=true&exclude_archived=true",
            headers=H,
        )
        r.raise_for_status()
        ids = {l["id"] for l in r.json()}
        assert live["id"] in ids
        assert soon_archived["id"] not in ids
    finally:
        for lg in (live, soon_archived):
            try:
                await db.leagues.delete_one({"_id": ObjectId(lg["id"])})
                await db.teams.delete_many({"league_id": lg["id"]})
            except Exception:
                pass


@pytest.mark.asyncio
async def test_default_my_leagues_still_returns_test_and_archived():
    """Regression guard: without the new opt-in flags the response
    must still contain TEST_ + archived leagues (other tests rely on
    this for setup/cleanup)."""
    token = _register_user()
    H = {"Authorization": f"Bearer {token}"}
    test_lg = _create_league(token, name=f"TEST_iter230al_default_{uuid.uuid4().hex[:4]}")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    try:
        r = requests.get(f"{API_URL}/api/leagues?my_leagues=true", headers=H)
        r.raise_for_status()
        ids = {l["id"] for l in r.json()}
        assert test_lg["id"] in ids
    finally:
        try:
            await db.leagues.delete_one({"_id": ObjectId(test_lg["id"])})
            await db.teams.delete_many({"league_id": test_lg["id"]})
        except Exception:
            pass

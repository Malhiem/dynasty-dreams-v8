"""Iter 231ai — Live prospect pool wiring (Prospects.tsx).

Tests:
  1. GET /api/prospects/filters returns year + position + team lists.
  2. GET /api/prospects supports year/position/search/drafted_by/limit
     filters and ranks by draft_year DESC, draft_pick_overall ASC.
  3. POST + DELETE /api/prospects/watchlist/{pid} round-trips a
     prospect into the user's `prospect_watchlist`.
  4. Frontend wires the live endpoints (mock array removed; testids
     present).
"""
from __future__ import annotations
from tests.source_tree import read_source

import os
import sys
from pathlib import Path

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


# ─── Source guards ─────────────────────────────────────────────────


def test_prospects_route_module_exists():
    src = read_source(Path("/app/backend/routes/prospects.py"))
    for path in (
        "/prospects", "/prospects/filters", "/prospects/watchlist",
        "/prospects/watchlist/{prospect_id}",
    ):
        assert path in src, f"missing route: {path}"


def test_prospects_route_wired_in_server():
    src = read_source(Path("/app/backend/server.py"))
    assert "prospects as prospects_routes" in src
    assert "prospects_routes.setup(_router_deps)" in src
    assert "api_router.include_router(prospects_routes.router)" in src


def test_frontend_prospects_uses_live_api():
    """Prospects.tsx must no longer hardcode an 8-entry mock array
    and must hit the new endpoints."""
    src = read_source(Path("/app/frontend/src/lovable/pages/Prospects.tsx"), include_imports=False)
    # Mock data removed.
    assert "Connor Bedard" not in src
    assert "Macklin Celebrini" not in src
    # Live API calls present.
    assert '"/prospects/filters"' in src
    assert '"/prospects"' in src
    assert "/prospects/watchlist" in src
    # Data testids for QA automation.
    for tid in (
        "prospects-page", "prospects-search-input",
        "prospects-year-select", "prospects-position-select",
        "prospects-tab-watchlist", "prospect-card-",
        "prospect-watch-btn-",
    ):
        assert tid in src, f"missing data-testid token: {tid}"


def test_watchlist_writes_coerce_objectid():
    """Iter 231ai bug: server.py:172 coerces user._id to string for JSON
    safety, so the watchlist update_many must coerce back to ObjectId
    or the $addToSet silently no-ops. Guard the fix."""
    src = read_source(Path("/app/backend/routes/prospects.py"))
    # Must convert back to ObjectId on the write path.
    assert 'ObjectId(user["_id"])' in src


# ─── Functional ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prospect_pool_has_full_6_year_classes():
    db = _db()
    years = set()
    async for row in db.players.aggregate([
        {"$match": {"player_type": "prospect", "draft_year": {"$ne": None}}},
        {"$group": {"_id": "$draft_year"}},
    ]):
        years.add(row["_id"])
    expected = {2020, 2021, 2022, 2023, 2024, 2025}
    assert expected.issubset(years), f"Missing classes: {expected - years}"


@pytest.mark.asyncio
async def test_watchlist_add_then_get_then_remove():
    """End-to-end round-trip on the watchlist endpoints — no HTTP layer
    needed, call the coroutines directly."""
    db = _db()
    from routes import prospects as prospects_module
    prospects_module._deps["db"] = db

    # Pick the first 2025 prospect as the watchlist target.
    target = await db.players.find_one({"player_type": "prospect", "draft_year": 2025})
    assert target is not None, "Prospect pool is empty — run iter231ah backfill first"
    target_id = str(target["_id"])

    # Seed a clean throwaway user for the watchlist round-trip.
    user_oid = ObjectId()
    user_doc = {
        "_id": user_oid,
        "email": "i231ai_watchlist@example.com",  # gets nuked by conftest sweep.
        "username": "i231ai_watch",
        "name": "i231ai watch",
        "prospect_watchlist": [],
    }
    await db.users.insert_one(user_doc)

    async def _stub_user(req):
        # Server's get_current_user stringifies _id; mirror that here
        # AND refetch from DB on each call so the stub reflects the
        # latest `prospect_watchlist` changes (the real auth path
        # always hits Mongo, so this matches behaviour).
        u = await db.users.find_one({"_id": user_oid})
        u["_id"] = str(u["_id"])
        return u

    prospects_module._deps["get_current_user"] = _stub_user

    try:
        # Empty watchlist on start.
        empty = await prospects_module.get_watchlist(request=None)
        assert empty["count"] == 0

        # Add.
        add_res = await prospects_module.add_to_watchlist(target_id, request=None)
        assert add_res["in_watchlist"] is True
        assert add_res["prospect_id"] == target_id

        # Get — should have 1 row.
        full = await prospects_module.get_watchlist(request=None)
        assert full["count"] == 1
        assert full["prospects"][0]["id"] == target_id
        assert full["prospects"][0]["in_watchlist"] is True

        # Add again — must be idempotent (still 1).
        await prospects_module.add_to_watchlist(target_id, request=None)
        again = await prospects_module.get_watchlist(request=None)
        assert again["count"] == 1

        # Remove.
        rem = await prospects_module.remove_from_watchlist(target_id, request=None)
        assert rem["in_watchlist"] is False
        after = await prospects_module.get_watchlist(request=None)
        assert after["count"] == 0
    finally:
        await db.users.delete_one({"_id": user_oid})


@pytest.mark.asyncio
async def test_list_prospects_filter_and_sort():
    """list_prospects must filter by year + position and sort
    draft_year DESC, draft_pick_overall ASC."""
    db = _db()
    from routes import prospects as prospects_module
    prospects_module._deps["db"] = db

    async def _stub_user(req):
        return {"_id": "fake", "prospect_watchlist": []}
    prospects_module._deps["get_current_user"] = _stub_user

    # Year-only filter.
    res = await prospects_module.list_prospects(
        request=None, year=2025, position=None, search=None,
        drafted_by=None, only_watchlist=False, limit=10,
    )
    assert res["count"] > 0
    for p in res["prospects"]:
        assert p["draft_year"] == 2025
    # Sort: ascending overall pick within the year.
    picks = [p["draft_pick_overall"] for p in res["prospects"] if p["draft_pick_overall"]]
    assert picks == sorted(picks), "Sort broken — overall picks should ascend"

    # Position filter (C only).
    res2 = await prospects_module.list_prospects(
        request=None, year=2025, position="C", search=None,
        drafted_by=None, only_watchlist=False, limit=10,
    )
    for p in res2["prospects"]:
        assert p["position"] == "C"

    # Multi-position filter (LW,RW).
    res3 = await prospects_module.list_prospects(
        request=None, year=2025, position="LW,RW", search=None,
        drafted_by=None, only_watchlist=False, limit=20,
    )
    for p in res3["prospects"]:
        assert p["position"] in ("LW", "RW")


@pytest.mark.asyncio
async def test_filters_endpoint_returns_distinct_options():
    db = _db()
    from routes import prospects as prospects_module
    prospects_module._deps["db"] = db

    async def _stub_user(req):
        return {"_id": "fake"}
    prospects_module._deps["get_current_user"] = _stub_user

    res = await prospects_module.prospect_filters(request=None)
    assert res["years"], "Years filter must not be empty"
    # Years sorted DESC, most-recent first.
    assert res["years"] == sorted(res["years"], reverse=True)
    assert res["positions"], "Positions must include at least C/D/G"
    expected = sorted(await db.players.distinct("drafted_by_team", {
        "player_type": "prospect", "drafted_by_team": {"$nin": [None, ""]}}))
    assert expected, "Fixture must include drafting-team affiliations"
    assert res["drafted_by_teams"] == expected

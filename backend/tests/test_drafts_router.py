"""Focused unit tests for `routes/drafts.py`."""
import os
import sys

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Iter 231al — `get_draft_picks` moved to `routes/draft_inspection.py`
# during the iter 231 router decomposition. Mount the inspection module
# alongside drafts so the legacy `/api/drafts/{league_id}/picks` route
# still resolves.
from routes import drafts as drafts_routes  # noqa: E402
from routes import draft_inspection  # noqa: E402

DRAFTS_FAMILY = (drafts_routes, draft_inspection)

from tests.router_test_utils import isolated_router_app  # noqa: E402


@pytest.mark.asyncio
async def test_picks_returns_empty_when_no_picks():
    async with isolated_router_app(DRAFTS_FAMILY) as ctx:
        r = await ctx.client.get("/api/drafts/no-such-league/picks")
        assert r.status_code == 200
        body = r.json()
        assert body == {"league_id": "no-such-league", "year": None, "draft_id": None, "picks": []}


@pytest.mark.asyncio
async def test_picks_sorted_by_year_then_round():
    async with isolated_router_app(DRAFTS_FAMILY) as ctx:
        league_id = "L1"
        await ctx.db.draft_picks.insert_many([
            {"league_id": league_id, "year": 2026, "round": 2, "pick_number": 14, "current_team_id": "T1"},
            {"league_id": league_id, "year": 2025, "round": 1, "pick_number": 3, "current_team_id": "T2"},
            {"league_id": league_id, "year": 2026, "round": 1, "pick_number": 7, "current_team_id": "T3"},
        ])
        r = await ctx.client.get(f"/api/drafts/{league_id}/picks")
        picks = r.json()["picks"]
        keys = [(p["year"], p["round"]) for p in picks]
        assert keys == [(2025, 1), (2026, 1), (2026, 2)]


@pytest.mark.asyncio
async def test_picks_year_filter():
    async with isolated_router_app(DRAFTS_FAMILY) as ctx:
        await ctx.db.draft_picks.insert_many([
            {"league_id": "L1", "year": 2025, "round": 1, "pick_number": 1, "current_team_id": "T1"},
            {"league_id": "L1", "year": 2026, "round": 1, "pick_number": 1, "current_team_id": "T1"},
        ])
        r = await ctx.client.get("/api/drafts/L1/picks?year=2026")
        body = r.json()
        assert body["year"] == 2026
        assert len(body["picks"]) == 1
        assert body["picks"][0]["year"] == 2026


@pytest.mark.asyncio
async def test_picks_attach_pending_protections_from_executed_trades():
    async with isolated_router_app(DRAFTS_FAMILY) as ctx:
        league_id = "L1"
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": league_id, "year": 2026, "round": 1, "pick_number": 4,
            "current_team_id": "T1",
        })
        pick_id = str(pick_res.inserted_id)
        await ctx.db.trades.insert_one({
            "league_id": league_id, "status": "executed",
            "pick_upgrades": [
                {
                    "pick_id": pick_id,
                    "new_round": 1, "new_year": 2027,
                    "condition": {
                        "subject_type": "pick", "metric": "pick_slot",
                        "operator": "lte", "threshold": 3,
                        "description": "Protected top-3",
                    },
                },
                # A second already-applied upgrade should not appear
                {
                    "pick_id": pick_id, "applied_at": "2025-01-01",
                    "condition": {"description": "Already applied"},
                },
            ],
        })
        r = await ctx.client.get(f"/api/drafts/{league_id}/picks")
        picks = r.json()["picks"]
        assert len(picks) == 1
        prot = picks[0]["pending_protections"]
        assert len(prot) == 1
        assert prot[0]["description"] == "Protected top-3"
        assert prot[0]["subject_type"] == "pick"
        assert prot[0]["new_year"] == 2027


@pytest.mark.asyncio
async def test_picks_no_protections_when_trade_not_executed():
    async with isolated_router_app(DRAFTS_FAMILY) as ctx:
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2026, "round": 1, "pick_number": 1,
            "current_team_id": "T1",
        })
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "pending",  # not executed
            "pick_upgrades": [{
                "pick_id": str(pick_res.inserted_id),
                "condition": {"description": "Hypothetical"},
            }],
        })
        r = await ctx.client.get("/api/drafts/L1/picks")
        assert r.json()["picks"][0]["pending_protections"] == []

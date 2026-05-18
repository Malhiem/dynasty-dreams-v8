"""Unit tests for the new `GET /api/trades/conditional` endpoint (iter 95).

Covers:
- Filters to status=executed only
- Skips trades with no conditions and no pick_upgrades
- Per-pick state mapping (triggered / failed / pending)
- Outcome-text generation
- Live trigger-condition evaluation via the injected _evaluate_conditions dep
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import trades as trades_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


# ─── Fake trade-engine deps ─────────────────────────────────────


async def _fake_evaluate_conditions(trade: dict) -> dict:
    """Stub: every condition evaluates as met=True with actual=threshold + 1."""
    results = []
    for c in (trade.get("conditions") or []):
        thr = float(c.get("threshold", 0) or 0)
        results.append({"condition": c, "actual_value": thr + 1.0, "met": True})
    return {"all_met": True, "results": results}


async def _fake_evaluate_single(cond: dict, _trade: dict):
    return True, float(cond.get("threshold", 0) or 0) + 1.0


def _wire_engine_deps():
    trades_routes._deps["_evaluate_conditions"] = _fake_evaluate_conditions
    trades_routes._deps["_evaluate_single_condition"] = _fake_evaluate_single


# ─── Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conditional_empty_when_no_executed_conditional_trades():
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        # Seed an executed trade with NO conditions — should be excluded
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "assets_offered": [], "assets_requested": [],
        })
        # Seed a PENDING trade WITH conditions — should also be excluded (status filter)
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "pending",
            "conditions": [{"metric": "nhl_points", "operator": "gte", "threshold": 50}],
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        assert r.status_code == 200
        body = r.json()
        assert body == {"trades": [], "count": 0}


@pytest.mark.asyncio
async def test_conditional_returns_executed_trades_with_conditions():
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "proposer_team_id": "T1", "target_team_id": "T2",
            "conditions": [
                {"metric": "nhl_points", "operator": "gte", "threshold": 70,
                 "description": "Hits 70 pts"},
            ],
            "executed_at": "2026-01-15T10:00:00",
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        body = r.json()
        assert body["count"] == 1
        t = body["trades"][0]
        # Live-eval populates conditions_eval
        assert len(t["conditions_eval"]) == 1
        assert t["conditions_eval"][0]["met"] is True
        # Threshold-stub increments by 1
        assert t["conditions_eval"][0]["actual_value"] == 71.0
        # No pick upgrades on this trade
        assert t["pick_upgrades_state"] == []


@pytest.mark.asyncio
async def test_conditional_pick_upgrade_state_triggered():
    """Pick upgrade with `applied_at` set → state=triggered + outcome shows new round."""
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2026, "round": 2, "pick_number": 14,
            "current_team_id": "T2",
        })
        pid = str(pick_res.inserted_id)
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "proposer_team_id": "T1", "target_team_id": "T2",
            "pick_upgrades": [{
                "pick_id": pid, "new_round": 1, "new_year": 2026,
                "description": "2nd → 1st if 50 pts",
                "condition": {"metric": "nhl_points", "operator": "gte", "threshold": 50,
                              "description": "Hits 50 pts"},
                "applied_at": "2026-01-20T10:00:00",
                "actual_value": 51.0,
            }],
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        body = r.json()
        ups = body["trades"][0]["pick_upgrades_state"]
        assert len(ups) == 1
        assert ups[0]["state"] == "triggered"
        assert ups[0]["met"] is True
        assert "2026" in ups[0]["outcome_text"]
        assert "R1" in ups[0]["outcome_text"]
        # `pick` is hydrated from draft_picks
        assert ups[0]["pick"]["round"] == 2


@pytest.mark.asyncio
async def test_conditional_pick_upgrade_state_failed():
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2026, "round": 1, "current_team_id": "T2",
        })
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "pick_upgrades": [{
                "pick_id": str(pick_res.inserted_id),
                "new_round": 3, "new_year": 2027,
                "condition": {"metric": "team_wins", "operator": "gte", "threshold": 10,
                              "description": "Win 10 games"},
                "failed_at": "2026-04-01T00:00:00",
                "actual_value": 4,
            }],
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        ups = r.json()["trades"][0]["pick_upgrades_state"]
        assert ups[0]["state"] == "failed"
        assert ups[0]["met"] is False
        assert "Did not trigger" in ups[0]["outcome_text"]


@pytest.mark.asyncio
async def test_conditional_pick_upgrade_state_pending_uses_live_eval():
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2027, "round": 1, "current_team_id": "T2",
        })
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "pick_upgrades": [{
                "pick_id": str(pick_res.inserted_id),
                "new_round": 1, "new_year": 2027,
                "condition": {"metric": "team_wins", "operator": "gte", "threshold": 20,
                              "description": "Win 20 games"},
                # No applied_at, no failed_at → pending
            }],
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        ups = r.json()["trades"][0]["pick_upgrades_state"]
        assert ups[0]["state"] == "pending"
        # Live eval stub returns met=True so the outcome describes the upgrade
        assert ups[0]["met"] is True
        # Stub returns threshold+1 = 21.0
        assert ups[0]["actual_value"] == 21.0
        assert "If triggered" in ups[0]["outcome_text"]


@pytest.mark.asyncio
async def test_conditional_route_does_not_collide_with_trade_id():
    """`/trades/conditional` must NOT be matched by `/trades/{trade_id}`."""
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        r = await ctx.client.get("/api/trades/conditional?league_id=NOPE")
        # 200 (empty), not 404 from /trades/{trade_id}
        assert r.status_code == 200
        assert r.json() == {"trades": [], "count": 0}

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
async def test_conditional_excludes_trades_with_only_whole_trade_conditions():
    """Iter 97 model change: trades with only `conditions` (whole-trade
    execution gates) and NO `pick_upgrades` are NOT surfaced on the
    Conditional tab — they're proposal-time gates, not ongoing clauses."""
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "conditions": [
                {"metric": "nhl_points", "operator": "gte", "threshold": 70,
                 "description": "Hits 70 pts"},
            ],
            # Note: NO pick_upgrades — should be excluded from /conditional
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        assert r.status_code == 200
        assert r.json() == {"trades": [], "count": 0}


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
async def test_conditional_pick_upgrade_state_triggered():
    """Pick upgrade with `applied_at` set → state=triggered + outcome shows
    new round AND the `was X` comparison using persisted from_round."""
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        # Simulate post-trigger: the pick has already been mutated to round 1,
        # and the upgrade row carries the persisted from_round = 2 / from_year = 2026
        # (this is what trade_engine writes when it applies the upgrade).
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2026, "round": 1, "pick_number": 14,
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
                "from_round": 2, "from_year": 2026,
            }],
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        body = r.json()
        ups = body["trades"][0]["pick_upgrades_state"]
        assert len(ups) == 1
        assert ups[0]["state"] == "triggered"
        assert ups[0]["met"] is True
        # Outcome text shows the FROM → TO comparison the user described
        # ("from 2nd to 1st round pick")
        outcome = ups[0]["outcome_text"]
        assert "2026 R1" in outcome
        assert "was" in outcome and "2026 R2" in outcome
        # `pick` is hydrated from draft_picks (mutated post-trigger)
        assert ups[0]["pick"]["round"] == 1


@pytest.mark.asyncio
async def test_conditional_pending_outcome_text_shows_from_to_preview():
    """Pending upgrade — outcome text previews `If triggered, pick upgrades
    from <current> to <target>`."""
    async with isolated_router_app(trades_routes) as ctx:
        _wire_engine_deps()
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2027, "round": 2, "current_team_id": "T2",
        })
        await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "pick_upgrades": [{
                "pick_id": str(pick_res.inserted_id),
                "new_round": 1, "new_year": 2027,
                "condition": {"metric": "nhl_points", "operator": "gte",
                              "threshold": 70, "description": "Hits 70"},
            }],
        })
        r = await ctx.client.get("/api/trades/conditional?league_id=L1")
        outcome = r.json()["trades"][0]["pick_upgrades_state"][0]["outcome_text"]
        assert outcome.startswith("If triggered, pick upgrades")
        assert "from 2027 R2" in outcome
        assert "to 2027 R1" in outcome


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
        assert "Pick remains" in ups[0]["outcome_text"]
        assert "condition unmet" in ups[0]["outcome_text"]


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

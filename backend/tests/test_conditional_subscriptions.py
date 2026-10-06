"""Unit tests for conditional-trade subscriptions + auto-notification on flip.

Covers:
- Subscribe / unsubscribe / list lifecycle on `routes/trades.py`
- `_apply_pick_upgrades` fires notifications for proposer + target + subs
- Stale subscriptions are cleaned up after the clause resolves
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import trades as trades_routes  # noqa: E402
from services import trade_engine  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


# ─── Subscribe endpoints ────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_404_when_trade_missing():
    async with isolated_router_app(trades_routes) as ctx:
        r = await ctx.client.post(
            f"/api/trades/conditional/{ObjectId()}/subscribe",
            json={"pick_upgrade_idx": -1, "action": "subscribe"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_subscribe_400_when_trade_not_executed():
    async with isolated_router_app(trades_routes) as ctx:
        res = await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "pending",
            "pick_upgrades": [{"pick_id": "x", "condition": {}}],
        })
        r = await ctx.client.post(
            f"/api/trades/conditional/{res.inserted_id}/subscribe",
            json={"pick_upgrade_idx": -1, "action": "subscribe"},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_subscribe_idempotent_then_unsubscribe():
    async with isolated_router_app(trades_routes) as ctx:
        res = await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "pick_upgrades": [{"pick_id": "x", "condition": {}}],
        })
        tid = str(res.inserted_id)
        # Subscribe twice → idempotent (one row)
        for _ in range(2):
            r = await ctx.client.post(
                f"/api/trades/conditional/{tid}/subscribe",
                json={"pick_upgrade_idx": 0, "action": "subscribe"},
            )
            assert r.status_code == 200
            assert r.json()["subscribed"] is True
        count = await ctx.db.conditional_subscriptions.count_documents({
            "trade_id": tid, "user_id": "test_user_0001",
        })
        assert count == 1

        # Unsubscribe → row removed
        r = await ctx.client.post(
            f"/api/trades/conditional/{tid}/subscribe",
            json={"pick_upgrade_idx": 0, "action": "unsubscribe"},
        )
        assert r.json()["subscribed"] is False
        assert r.json()["removed"] == 1


@pytest.mark.asyncio
async def test_subscribe_rejects_settled_upgrade():
    async with isolated_router_app(trades_routes) as ctx:
        res = await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "pick_upgrades": [{
                "pick_id": "x", "condition": {},
                "applied_at": "2026-01-01T00:00:00",
            }],
        })
        r = await ctx.client.post(
            f"/api/trades/conditional/{res.inserted_id}/subscribe",
            json={"pick_upgrade_idx": 0, "action": "subscribe"},
        )
        assert r.status_code == 400
        assert "settled" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_subscriptions_only_own_user():
    async with isolated_router_app(trades_routes) as ctx:
        res = await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "pick_upgrades": [{"pick_id": "x", "condition": {}}],
        })
        tid = str(res.inserted_id)
        # Mine
        await ctx.client.post(
            f"/api/trades/conditional/{tid}/subscribe",
            json={"pick_upgrade_idx": 0, "action": "subscribe"},
        )
        # Someone else (seeded directly)
        await ctx.db.conditional_subscriptions.insert_one({
            "league_id": "L1", "trade_id": tid,
            "user_id": "other_user", "pick_upgrade_idx": 0,
        })
        r = await ctx.client.get("/api/trades/conditional/subscriptions?league_id=L1")
        body = r.json()
        assert len(body["subscriptions"]) == 1
        assert body["subscriptions"][0]["user_id"] == "test_user_0001"


# ─── Auto-notification on _apply_pick_upgrades flip ─────────────


@pytest.mark.asyncio
async def test_apply_pick_upgrades_notifies_parties_and_subs_on_trigger(monkeypatch):
    """When a pending upgrade flips to triggered, both trade parties AND
    any subscribed user should receive a notification, AND the stale
    subscription rows should be cleaned up."""
    async with isolated_router_app(trades_routes) as ctx:
        # Inject trade_engine deps (it uses its own _deps dict)
        notif_log: list = []

        async def fake_create_notification(user_id, notif_type, title, message,
                                            league_id=None, link=None):
            notif_log.append({
                "user_id": user_id, "type": notif_type,
                "title": title, "message": message,
                "league_id": league_id, "link": link,
            })

        # Stub: every condition is met with actual=42
        async def fake_eval_single(_cond, _trade):
            return True, 42.0

        monkeypatch.setattr(trade_engine, "_deps", {
            "db": ctx.db,
            "logger": __import__("logging").getLogger("test"),
            "create_notification": fake_create_notification,
            "broadcast_to_room": (lambda *a, **kw: None),  # unused on this path
        })
        monkeypatch.setattr(trade_engine, "_evaluate_single_condition", fake_eval_single)

        # Seed a pick + a trade with one pending pick_upgrade
        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2026, "round": 3, "current_team_id": "T2",
        })
        trade_res = await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "proposer_id": "user_A", "target_owner_id": "user_B",
            "pick_upgrades": [{
                "pick_id": str(pick_res.inserted_id),
                "new_round": 1, "new_year": 2026,
                "condition": {"metric": "team_wins", "operator": "gte",
                              "threshold": 10, "description": "Win 10"},
            }],
        })
        # A third user subscribes to this clause
        await ctx.db.conditional_subscriptions.insert_one({
            "league_id": "L1", "trade_id": str(trade_res.inserted_id),
            "user_id": "user_C", "pick_upgrade_idx": 0,
        })

        trade = await ctx.db.trades.find_one({"_id": trade_res.inserted_id})
        await trade_engine._apply_pick_upgrades(trade)

        # All three users notified
        users = sorted(n["user_id"] for n in notif_log)
        assert users == ["user_A", "user_B", "user_C"]
        assert all(n["type"] == "conditional_triggered" for n in notif_log)
        # Message references the trigger description and the outcome
        sample = notif_log[0]
        assert "Win 10" in sample["message"]
        assert "R1" in sample["message"]
        # Link routes back to the Conditional tab
        assert "/transactions?tab=conditional" in sample["link"]

        # Subscription row was cleaned up
        remaining = await ctx.db.conditional_subscriptions.count_documents({
            "trade_id": str(trade_res.inserted_id),
        })
        assert remaining == 0


@pytest.mark.asyncio
async def test_apply_pick_upgrades_notifies_parties_on_failed_final_eval(monkeypatch):
    """When `final_eval=True` and the condition is NOT met, both trade
    parties (and any subscribers) get a 'did not trigger' notification."""
    async with isolated_router_app(trades_routes) as ctx:
        notif_log: list = []

        async def fake_create_notification(user_id, notif_type, title, message,
                                            league_id=None, link=None):
            notif_log.append({"user_id": user_id, "type": notif_type,
                              "title": title, "message": message})

        async def fake_eval_single(_cond, _trade):
            return False, 7.0  # unmet

        monkeypatch.setattr(trade_engine, "_deps", {
            "db": ctx.db,
            "logger": __import__("logging").getLogger("test"),
            "create_notification": fake_create_notification,
            "broadcast_to_room": (lambda *a, **kw: None),
        })
        monkeypatch.setattr(trade_engine, "_evaluate_single_condition", fake_eval_single)

        pick_res = await ctx.db.draft_picks.insert_one({
            "league_id": "L1", "year": 2026, "round": 1, "current_team_id": "T2",
        })
        trade_res = await ctx.db.trades.insert_one({
            "league_id": "L1", "status": "executed",
            "proposer_id": "u_A", "target_owner_id": "u_B",
            "pick_upgrades": [{
                "pick_id": str(pick_res.inserted_id),
                "new_round": 3, "new_year": 2027,
                "condition": {"metric": "team_wins", "operator": "gte",
                              "threshold": 10, "description": "Win 10"},
            }],
        })
        trade = await ctx.db.trades.find_one({"_id": trade_res.inserted_id})
        # final_eval=True → unmet clauses settle to 'failed'
        await trade_engine._apply_pick_upgrades(trade, final_eval=True)

        users = sorted(n["user_id"] for n in notif_log)
        assert users == ["u_A", "u_B"]
        assert all(n["type"] == "conditional_failed" for n in notif_log)
        assert all("did not trigger" in n["title"].lower() for n in notif_log)

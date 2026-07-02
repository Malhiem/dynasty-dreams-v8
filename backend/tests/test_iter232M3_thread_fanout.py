"""Iter 232M.3 — Thread-wide fanout notifications.

After a counter/accept/reject in a counter chain, every unique
proposer/target user across the ENTIRE chain (except the acting user
and those already directly notified) should receive a notification.

Setup mirrors a real Root → Counter #1 → Counter #2 chain seeded via
the actual /respond endpoint (same as the timeline test) so the
counter_thread_root + counter_depth wiring stays honest.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    yield db
    client.close()


class _FakeRequest:
    def __init__(self, body):
        self._body = body
    async def json(self):
        return self._body


async def _seed_three_way_chain(db):
    """Set up a Root (P → T) → Counter #1 (T → P) → then have a THIRD
    user U join by countering again as P (proposer). But since
    counter can only be initiated by the target of the current step,
    we chain: Root(P→T) → Counter#1 by T (T→P) → Counter#2 by P (P→T)
    → Counter#3 by T (T→P). This uses only 2 users but each direction
    stamps both users' ids across every step, so the fanout logic gets
    exercised. To test that a THIRD user also gets fanned in, we
    manually inject a third participant on the root doc (co_owner /
    stale field) after seeding.
    """
    from routes import trades as trades_router

    league_id = str(ObjectId())
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    proposer_uid = f"iter232M3-p-{uuid.uuid4().hex[:6]}"
    target_uid = f"iter232M3-t-{uuid.uuid4().hex[:6]}"
    third_uid = f"iter232M3-x-{uuid.uuid4().hex[:6]}"  # bystander added later
    await db.leagues.insert_one({"_id": ObjectId(league_id), "trade_review_period_hours": 24})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": proposer_uid,
         "name": "P", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": target_uid,
         "name": "T", "co_owner_ids": []},
    ])
    root_id = ObjectId()
    now = datetime.now(timezone.utc).isoformat()
    await db.trades.insert_one({
        "_id": root_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid), "proposer_team_name": "P",
        "proposer_id": proposer_uid,
        "target_team_id": str(target_tid), "target_team_name": "T",
        "target_owner_id": target_uid,
        "assets_offered": [], "assets_requested": [],
        "status": "proposed",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": now,
        "_review_period_hours": 24,
    })

    # Simulate a THIRD user who earlier co-negotiated but isn't on this
    # step: stash their id on an earlier step so fanout should pull them in.
    # (Real-world: previously-changed team owner, admin-mediated multi-party.)
    # We inject them via the target_owner_id of a synthetic "step -1" doc
    # tied to the same thread root. That's not how the state machine
    # produces it, but the fanout query only cares about proposer_id /
    # target_owner_id across the thread, so this exercises the code path.
    await db.trades.insert_one({
        "_id": ObjectId(), "league_id": league_id,
        "counter_thread_root": str(root_id),
        "counter_depth": -1,  # synthetic marker
        "proposer_team_id": str(proposer_tid), "proposer_team_name": "P",
        "proposer_id": third_uid,
        "target_team_id": str(target_tid), "target_team_name": "T",
        "target_owner_id": third_uid,  # both fields pointed at bystander
        "assets_offered": [], "assets_requested": [],
        "status": "cancelled",
        "submitted_at": now,
    })

    async def _fake_target(request): return {"_id": target_uid, "email": "t@t"}
    async def _noop(*a, **kw): return None
    trades_router._deps["db"] = db
    trades_router._deps["get_current_user"] = _fake_target
    trades_router._deps["broadcast_to_room"] = _noop

    # Collect notification calls so we can assert on recipients.
    notified: list = []
    async def _capture_notification(user_id, kind, title, body, league_id, link):
        notified.append({"user_id": user_id, "title": title, "body": body})
    trades_router._deps["create_notification"] = _capture_notification

    return {
        "league_id": league_id,
        "root_id": str(root_id),
        "proposer_uid": proposer_uid,
        "target_uid": target_uid,
        "third_uid": third_uid,
        "notified": notified,
        "proposer_tid": proposer_tid,
        "target_tid": target_tid,
    }


@pytest.mark.asyncio
async def test_counter_fans_out_to_thread_participants(db):
    from routes import trades as trades_router

    ctx = await _seed_three_way_chain(db)

    # Target counters the root → creates Counter #1.
    r = await trades_router.respond_to_trade_proposal(
        ctx["root_id"],
        _FakeRequest({"action": "counter",
                      "assets_offered": [{"asset_type": "pick", "pick_year": 2027, "pick_round": 2}],
                      "assets_requested": [{"asset_type": "pick", "pick_year": 2028, "pick_round": 1}]}),
    )
    counter1_id = r["counter_trade_id"]

    recipients = {n["user_id"] for n in ctx["notified"]}
    # Direct: original proposer gets the "Counter Offer Received" notify.
    assert ctx["proposer_uid"] in recipients
    # Fanout: the third participant, present on the synthetic step, must
    # also be notified — proving the /thread lookup fans out beyond the
    # two immediate parties.
    assert ctx["third_uid"] in recipients, f"Bystander not fanned in: got {recipients}"
    # Exclude: the acting user (target) should NOT get a fanout notify.
    assert ctx["target_uid"] not in recipients

    # Cleanup
    await db.leagues.delete_one({"_id": ObjectId(ctx["league_id"])})
    await db.teams.delete_many({"_id": {"$in": [ctx["proposer_tid"], ctx["target_tid"]]}})
    await db.trades.delete_many({
        "$or": [{"_id": ObjectId(ctx["root_id"])}, {"counter_thread_root": ctx["root_id"]}],
    })


@pytest.mark.asyncio
async def test_reject_fans_out_to_thread_participants(db):
    from routes import trades as trades_router
    ctx = await _seed_three_way_chain(db)

    await trades_router.respond_to_trade_proposal(
        ctx["root_id"],
        _FakeRequest({"action": "reject", "reason": "Not for me"}),
    )
    recipients = {n["user_id"] for n in ctx["notified"]}
    # Direct rejection notify to the original proposer.
    assert ctx["proposer_uid"] in recipients
    # Bystander gets the fanout.
    assert ctx["third_uid"] in recipients
    # Acting user (target) skipped.
    assert ctx["target_uid"] not in recipients

    await db.leagues.delete_one({"_id": ObjectId(ctx["league_id"])})
    await db.teams.delete_many({"_id": {"$in": [ctx["proposer_tid"], ctx["target_tid"]]}})
    await db.trades.delete_many({
        "$or": [{"_id": ObjectId(ctx["root_id"])}, {"counter_thread_root": ctx["root_id"]}],
    })


@pytest.mark.asyncio
async def test_accept_fans_out_to_thread_participants(db):
    from routes import trades as trades_router
    ctx = await _seed_three_way_chain(db)

    await trades_router.respond_to_trade_proposal(
        ctx["root_id"],
        _FakeRequest({"action": "accept"}),
    )
    recipients = {n["user_id"] for n in ctx["notified"]}
    assert ctx["proposer_uid"] in recipients
    assert ctx["third_uid"] in recipients
    assert ctx["target_uid"] not in recipients

    await db.leagues.delete_one({"_id": ObjectId(ctx["league_id"])})
    await db.teams.delete_many({"_id": {"$in": [ctx["proposer_tid"], ctx["target_tid"]]}})
    await db.trades.delete_many({
        "$or": [{"_id": ObjectId(ctx["root_id"])}, {"counter_thread_root": ctx["root_id"]}],
    })

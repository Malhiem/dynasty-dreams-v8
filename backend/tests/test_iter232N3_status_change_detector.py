"""Iter 232N.3 — Player status-flag change detector.

Covers:
  (1) First-run snapshot silently seeds `last_status_flags` without
      firing events (avoids spamming every owner with legacy flags).
  (2) Second run with no changes emits ZERO events.
  (3) Flipping a flag (healthy → IR) fires `player_status_change`
      to the owner's user room AND creates a persistent notification.
  (4) Clearing a flag (IR → healthy) also fires (recall/return event).
  (5) `undrafted` flips are intentionally NOT reported (not a
      player-development milestone).
  (6) Co-owners on a team also receive the toast + notification.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.player_status_change_detector import detect_and_emit_status_changes  # noqa: E402


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    d = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    yield d
    client.close()


class _Collector:
    """Small helper that captures the args passed to broadcast_fn and
    create_notification_fn so tests can assert on them."""

    def __init__(self) -> None:
        self.broadcasts: list[tuple] = []
        self.notifications: list[dict] = []

    async def broadcast(self, room, event, payload):
        self.broadcasts.append((room, event, payload))

    async def create_notification(self, **kwargs):
        self.notifications.append(kwargs)


@pytest.mark.asyncio
async def test_first_run_seeds_snapshot_silently(db):
    sfx = uuid.uuid4().hex[:8]
    player = await db.players.insert_one({
        "name": f"Seed {sfx}", "position": "C", "roster_status": "IR",
        "nhl_id": f"iter232N3-seed-{sfx}",
    })
    pid = str(player.inserted_id)
    coll = _Collector()

    res = await detect_and_emit_status_changes(
        db, [pid], broadcast_fn=coll.broadcast,
        create_notification_fn=coll.create_notification,
    )

    assert res["scanned"] == 1
    assert res["changed"] == 0  # first run — snapshot seeded, no events
    assert coll.broadcasts == []
    assert coll.notifications == []

    # Snapshot must now be persisted so a repeat run stays quiet.
    updated = await db.players.find_one({"_id": player.inserted_id})
    assert updated.get("last_status_flags") is not None
    assert updated["last_status_flags"]["injured"] is True

    await db.players.delete_one({"_id": player.inserted_id})


@pytest.mark.asyncio
async def test_flag_flip_fires_broadcast_and_notification(db):
    sfx = uuid.uuid4().hex[:8]
    user_id = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()

    player = await db.players.insert_one({
        "name": f"Flipper {sfx}", "position": "LW",
        "roster_status": "active",  # healthy
        "last_status_flags": {
            "injured": False, "in_minors": False, "unsigned": False, "undrafted": False,
        },
        "nhl_id": f"iter232N3-flip-{sfx}",
    })
    pid = str(player.inserted_id)
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_id,
        "co_owner_ids": [], "roster": [pid],
    })

    # Now move the player to IR — flag flip healthy → injured.
    await db.players.update_one({"_id": player.inserted_id}, {"$set": {"roster_status": "IR"}})

    coll = _Collector()
    res = await detect_and_emit_status_changes(
        db, [pid], broadcast_fn=coll.broadcast,
        create_notification_fn=coll.create_notification,
    )
    assert res["scanned"] == 1
    assert res["changed"] == 1
    # Exactly one event to the owner's personal room.
    assert len(coll.broadcasts) == 1
    room, event, payload = coll.broadcasts[0]
    assert room == f"user_{user_id}"
    assert event == "player_status_change"
    assert payload["flag"] == "injured"
    assert payload["value"] is True
    # Notification also fired.
    assert len(coll.notifications) == 1
    assert coll.notifications[0]["user_id"] == user_id
    assert "Injury" in coll.notifications[0]["title"]

    await db.players.delete_one({"_id": player.inserted_id})
    await db.teams.delete_one({"_id": team_id})


@pytest.mark.asyncio
async def test_recall_from_minors_fires_off_event(db):
    sfx = uuid.uuid4().hex[:8]
    user_id = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()

    # Player starts in minors (in_minors=true snapshotted).
    player = await db.players.insert_one({
        "name": f"Recall {sfx}", "position": "C", "player_type": "prospect",
        "amateur_league": "AHL",  # in_minors = true
        "last_status_flags": {
            "injured": False, "in_minors": True, "unsigned": False, "undrafted": False,
        },
        "nhl_id": f"iter232N3-recall-{sfx}",
    })
    pid = str(player.inserted_id)
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_id,
        "co_owner_ids": [], "roster": [pid],
    })

    # Recall — move to a non-minor amateur league (WHL) OR flip to NHL.
    await db.players.update_one(
        {"_id": player.inserted_id}, {"$set": {"amateur_league": "WHL"}},
    )
    coll = _Collector()
    res = await detect_and_emit_status_changes(
        db, [pid], broadcast_fn=coll.broadcast,
        create_notification_fn=coll.create_notification,
    )
    assert res["changed"] == 1
    assert coll.broadcasts[0][2]["flag"] == "in_minors"
    assert coll.broadcasts[0][2]["value"] is False  # cleared
    assert "Called up" in coll.notifications[0]["title"]

    await db.players.delete_one({"_id": player.inserted_id})
    await db.teams.delete_one({"_id": team_id})


@pytest.mark.asyncio
async def test_undrafted_flip_is_not_reported(db):
    """`undrafted` is a league-scoped bookkeeping flag; flipping it
    should NOT fire a toast."""
    sfx = uuid.uuid4().hex[:8]
    league_id = str(ObjectId())
    prev_draft_id = ObjectId()
    user_id = str(ObjectId())
    team_id = ObjectId()

    player = await db.players.insert_one({
        "name": f"Und {sfx}", "position": "C", "player_type": "prospect",
        "amateur_league": "OHL",
        "last_status_flags": {
            "injured": False, "in_minors": False, "unsigned": False, "undrafted": True,
        },
        "nhl_id": f"iter232N3-und-{sfx}",
    })
    pid = str(player.inserted_id)
    # Draft the player in a "prior" league draft.
    await db.drafts.insert_one({
        "_id": prev_draft_id, "league_id": league_id, "status": "completed",
        "picks": [{"player_id": pid}],
    })
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_id,
        "co_owner_ids": [], "roster": [pid],
    })

    coll = _Collector()
    res = await detect_and_emit_status_changes(
        db, [pid], broadcast_fn=coll.broadcast,
        create_notification_fn=coll.create_notification,
        league_id_for_undrafted=league_id,
    )
    # undrafted flipped true → false, but NO event should have fired.
    assert coll.broadcasts == []
    assert coll.notifications == []
    assert res["changed"] == 0

    await db.players.delete_one({"_id": player.inserted_id})
    await db.drafts.delete_one({"_id": prev_draft_id})
    await db.teams.delete_one({"_id": team_id})


@pytest.mark.asyncio
async def test_co_owners_also_receive_events(db):
    sfx = uuid.uuid4().hex[:8]
    user_a = str(ObjectId())
    user_b = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()

    player = await db.players.insert_one({
        "name": f"Coown {sfx}", "position": "D",
        "roster_status": "active",
        "last_status_flags": {
            "injured": False, "in_minors": False, "unsigned": False, "undrafted": False,
        },
        "nhl_id": f"iter232N3-co-{sfx}",
    })
    pid = str(player.inserted_id)
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_a,
        "co_owner_ids": [user_b], "roster": [pid],
    })
    await db.players.update_one({"_id": player.inserted_id}, {"$set": {"roster_status": "IR"}})

    coll = _Collector()
    await detect_and_emit_status_changes(
        db, [pid], broadcast_fn=coll.broadcast,
        create_notification_fn=coll.create_notification,
    )
    # Both owner and co-owner get a broadcast on their personal rooms.
    rooms = {b[0] for b in coll.broadcasts}
    assert f"user_{user_a}" in rooms
    assert f"user_{user_b}" in rooms
    assert len(coll.notifications) == 2

    await db.players.delete_one({"_id": player.inserted_id})
    await db.teams.delete_one({"_id": team_id})

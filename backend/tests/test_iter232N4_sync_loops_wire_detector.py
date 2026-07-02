"""Iter 232N.4 — Sync-loop → status-flag detector wiring.

Verifies the two background workers now fan out real-time
`player_status_change` toasts as a natural side-effect of ingesting
injury / roster feeds.

Covers:
  (1) `nhl_roster_sync_worker.sync_once` — when a rostered player's
      `league_status` flips NHL → AHL (recall/send-down), the toast
      fires to the owner.
  (2) `injury_news_scraper.scrape_news_and_dispatch` — when a matched
      headline flips a rostered player's `injury_status`, the toast
      fires to the owner.
  (3) Both call sites pass `broadcast_fn` through and populate
      `counts["status_flag_events"]` for observability.

We patch the network layers (`_fetch_team_codes` / `_fetch_team_roster`
and `_fetch_feed`) so the tests are hermetic — no live HTTP.
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


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    d = client[os.environ.get("DB_NAME", "test_database")]
    yield d
    client.close()


class _Collector:
    def __init__(self) -> None:
        self.broadcasts: list[tuple] = []

    async def broadcast(self, room, event, payload):
        self.broadcasts.append((room, event, payload))


@pytest.mark.asyncio
async def test_nhl_roster_sync_emits_status_flag_events(db, monkeypatch):
    """A rostered NHL player that disappears from the league feed must
    trigger both the existing `player_sent_down` pipeline AND a
    `player_status_change` websocket event via the new hook."""
    from services import nhl_roster_sync_worker as worker

    sfx = uuid.uuid4().hex[:8]
    nhl_id = 90000000 + hash(sfx) % 10000
    user_id = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()

    # Player currently marked NHL (previous state) — feed will "lose"
    # him so the worker flips league_status → AHL.
    player = await db.players.insert_one({
        "name": f"WorkerFlip {sfx}",
        "nhl_id": nhl_id,
        "current_team_abbrev": "EDM",
        "league_status": "NHL",
        "roster_status": "active",
        "position": "C",
        "player_type": "skater",
        # Pre-seed the snapshot so we're testing a real flip and NOT
        # first-run seeding.
        "last_status_flags": {
            "injured": False, "in_minors": False,
            "unsigned": False, "undrafted": False,
        },
    })
    pid = str(player.inserted_id)
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_id,
        "co_owner_ids": [], "roster": [pid],
    })

    # Patch the two network calls so no HTTP fires: give it enough
    # "teams" to pass the >=50% freshness gate, and an empty roster
    # everywhere so the player IS "missing" from the feed.
    async def _fake_team_codes(http):
        return ["EDM"]

    async def _fake_team_roster(http, team_code):
        return []  # nobody on the roster → player is "sent down"

    monkeypatch.setattr(worker, "_fetch_team_codes", _fake_team_codes)
    monkeypatch.setattr(worker, "_fetch_team_roster", _fake_team_roster)

    coll = _Collector()

    async def _fake_notif(**kwargs):
        return None

    counts = await worker.sync_once(
        db, create_notification=_fake_notif, broadcast_fn=coll.broadcast,
    )
    # Existing behaviour: at least 1 diff was applied.
    assert counts["team_changes"] >= 1
    # Iter 232N.4 hook: status_flag_events was populated.
    assert "status_flag_events" in counts
    # And the owner received a websocket toast.
    rooms = {b[0] for b in coll.broadcasts if b[1] == "player_status_change"}
    assert f"user_{user_id}" in rooms, (
        f"expected user_{user_id} in broadcast rooms, got {rooms}"
    )

    await db.players.delete_one({"_id": player.inserted_id})
    await db.teams.delete_one({"_id": team_id})


@pytest.mark.asyncio
async def test_injury_news_scraper_fans_out_status_flag_events(db, monkeypatch):
    """A matched injury headline that flips `injury_status` on a
    rostered player must fan out a `player_status_change` toast
    through the new hook."""
    from services import injury_news_scraper as scraper

    sfx = uuid.uuid4().hex[:8]
    user_id = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()

    unique_last = f"McTestington{sfx}"
    player = await db.players.insert_one({
        "name": f"Zed {unique_last}",
        "nhl_id": 91000000 + hash(sfx) % 10000,
        "position": "C",
        "roster_status": "active",
        "injury_status": "healthy",
        "last_status_flags": {
            "injured": False, "in_minors": False,
            "unsigned": False, "undrafted": False,
        },
    })
    pid = str(player.inserted_id)
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_id,
        "co_owner_ids": [], "roster": [pid],
    })

    # Fake an RSS item that classifies as an injury signal AND matches
    # our player by last name. The classifier looks for words like
    # "injured", "IR", "out"; we craft the description accordingly.
    class _FakeElement:
        def __init__(self, text=""):
            self.text = text
            self.attrib = {}

        def find(self, _tag):
            return None

    class _FakeItem:
        def __init__(self, title, link, description):
            self._title = title
            self._link = link
            self._description = description

        def find(self, tag):
            table = {
                "title": _FakeElement(self._title),
                "link": _FakeElement(self._link),
                "description": _FakeElement(self._description),
                # No pubDate → _parse_pub_date returns None →
                # scraper falls back to `datetime.now(timezone.utc)`
                # which is always inside the LOOKBACK_HOURS window.
            }
            for key, el in table.items():
                if tag.endswith(key):
                    return el
            return None

    fake_item = _FakeItem(
        title=f"{unique_last} placed on IR",
        link=f"https://example.test/{sfx}",
        description=f"{unique_last} injured, moved to IR.",
    )

    async def _fake_fetch_feed(http, url):
        return [fake_item]

    monkeypatch.setattr(scraper, "_fetch_feed", _fake_fetch_feed)

    coll = _Collector()

    async def _fake_notif(**kwargs):
        return None

    counts = await scraper.scrape_news_and_dispatch(
        db, create_notification=_fake_notif, broadcast_fn=coll.broadcast,
    )

    assert counts["injury_signals"] >= 1
    assert "status_flag_events" in counts
    rooms = {b[0] for b in coll.broadcasts if b[1] == "player_status_change"}
    assert f"user_{user_id}" in rooms, (
        f"expected user_{user_id} in broadcast rooms, got {rooms}"
    )

    await db.players.delete_one({"_id": player.inserted_id})
    await db.teams.delete_one({"_id": team_id})
    await db.player_news.delete_many({"player_id": pid})
    await db.injury_news_signals.delete_many({"player_id": pid})

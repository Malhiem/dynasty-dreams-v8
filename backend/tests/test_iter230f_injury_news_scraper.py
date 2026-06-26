"""Iter 230f — Injury news scraper tests.

Drives `scrape_news_and_dispatch` with a mocked feed fetcher so we can
deterministically assert classifier correctness, dedup, and the
end-to-end dispatch pipeline.
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from email.utils import format_datetime

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db_sync():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ.get("DB_NAME", "test_database")]


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


def _make_rss_item(title: str, description: str = "", pub: datetime = None) -> str:
    """Return an `<item>...</item>` XML fragment for a single headline."""
    pub_dt = pub or datetime.now(timezone.utc)
    pub_str = format_datetime(pub_dt)
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>https://example.com/{abs(hash(title))}</link>"
        f"<description>{description}</description>"
        f"<pubDate>{pub_str}</pubDate>"
        "</item>"
    )


def _make_rss(items: list) -> bytes:
    body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss><channel>"
        + "".join(items) +
        "</channel></rss>"
    )
    return body.encode("utf-8")


# ──────────────────────────────────────────────────────────────────────


def test_classifier_keyword_recognition():
    """The classifier maps known headline shapes to the right kind."""
    from services.injury_news_scraper import _classify_injury_signal

    cases = [
        ("McDavid placed on injured reserve",        ("injured", "IR")),
        ("Connor McDavid out 4 weeks with knee",     ("injured", "IR")),
        ("McDavid undergoes surgery",                ("injured", "IR")),
        ("McDavid returns from IR tonight",          ("recovered", "Healthy")),
        ("McDavid activated off injured reserve",    ("recovered", "Healthy")),
        ("McDavid listed as day-to-day",             ("injury_status_changed", "DTD")),
        ("McDavid scores hat trick",                 None),  # No signal.
    ]
    for haystack, expected in cases:
        result = _classify_injury_signal(haystack.lower())
        assert result == expected, f"{haystack!r} → {result} (expected {expected})"


@pytest.mark.asyncio
async def test_scraper_dispatches_injury_signal_end_to_end():
    """A headline matching a rostered player should patch their
    injury_status AND fire `player_injured` via the dispatcher."""
    from services import injury_news_scraper as scraper

    db = _db_sync()
    # Pick any rostered player so the dispatcher has real recipients.
    team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
    player_id = team["roster"][0]
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    original_status = player.get("injury_status")
    player_name = player["name"]

    # Clear any prior dedup state for this URL.
    test_url = f"https://example.com/{abs(hash(player_name + 'placed on injured reserve'))}"
    await db.injury_news_signals.delete_many({"player_id": player_id})

    # Build a single mocked RSS item that mentions the player by full name.
    item = _make_rss_item(
        title=f"{player_name} placed on injured reserve",
        description="The team announced the move ahead of tonight's game.",
    )
    fake_rss = _make_rss([item])
    parsed = __import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring(fake_rss)
    items = list(parsed.iter("item"))

    async def fake_fetch(http, url):
        return items if "yahoo" in url else None  # First feed succeeds, others 404.

    calls: list = []

    async def recorder(user_id, event_id, title, body, league_id=None, link=None):
        calls.append(event_id)

    try:
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"injury_status": "Healthy"}},
        )
        with patch.object(scraper, "_fetch_feed", fake_fetch):
            counts = await scraper.scrape_news_and_dispatch(db, create_notification=recorder)

        assert counts["headlines_scanned"] >= 1
        assert counts["headlines_matched"] >= 1
        assert counts["injury_signals"] >= 1
        # The dispatcher fired the injured notification for everyone who
        # rosters this player.
        assert "player_injured" in calls, f"expected player_injured event, got: {calls}"

        # Player doc now reflects the new injury_status.
        fresh = await db.players.find_one({"_id": ObjectId(player_id)})
        assert (fresh.get("injury_status") or "").upper() == "IR"

        # Dedup: re-running the same scrape should NOT re-fire.
        calls.clear()
        with patch.object(scraper, "_fetch_feed", fake_fetch):
            counts2 = await scraper.scrape_news_and_dispatch(db, create_notification=recorder)
        assert counts2["deduped"] >= 1
        assert "player_injured" not in calls
    finally:
        # Restore original injury_status + clear dedup rows we created.
        await db.injury_news_signals.delete_many({"player_id": player_id})
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"injury_status": original_status}} if original_status is not None
            else {"$unset": {"injury_status": ""}},
        )


@pytest.mark.asyncio
async def test_scraper_skips_stale_headlines():
    """Headlines older than LOOKBACK_HOURS aren't classified."""
    from services import injury_news_scraper as scraper

    db = _db_sync()
    team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
    player_id = team["roster"][0]
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    player_name = player["name"]

    # Stale (8 days ago).
    item = _make_rss_item(
        title=f"{player_name} placed on injured reserve",
        pub=datetime.now(timezone.utc) - timedelta(days=8),
    )
    fake_rss = _make_rss([item])
    items = list(__import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring(fake_rss).iter("item"))

    async def fake_fetch(http, url):
        return items if "yahoo" in url else None

    calls: list = []

    async def recorder(*a, **kw):
        calls.append(a[1] if len(a) > 1 else None)

    with patch.object(scraper, "_fetch_feed", fake_fetch):
        counts = await scraper.scrape_news_and_dispatch(db, create_notification=recorder)

    assert counts["injury_signals"] == 0
    assert calls == []


@pytest.mark.asyncio
async def test_scraper_recovery_headline_fires_player_recovered():
    from services import injury_news_scraper as scraper

    db = _db_sync()
    team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
    player_id = team["roster"][0]
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    player_name = player["name"]
    original_status = player.get("injury_status")

    item = _make_rss_item(
        title=f"{player_name} returns from injury",
        description="Coach confirmed tonight's lineup.",
    )
    fake_rss = _make_rss([item])
    items = list(__import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring(fake_rss).iter("item"))

    async def fake_fetch(http, url):
        return items if "yahoo" in url else None

    calls: list = []

    async def recorder(user_id, event_id, title, body, league_id=None, link=None):
        calls.append(event_id)

    try:
        # Start from IR so the dispatcher sees a true recovery transition.
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"injury_status": "IR"}},
        )
        await db.injury_news_signals.delete_many({"player_id": player_id})
        with patch.object(scraper, "_fetch_feed", fake_fetch):
            await scraper.scrape_news_and_dispatch(db, create_notification=recorder)
        assert "player_recovered" in calls, calls
    finally:
        await db.injury_news_signals.delete_many({"player_id": player_id})
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"injury_status": original_status}} if original_status is not None
            else {"$unset": {"injury_status": ""}},
        )

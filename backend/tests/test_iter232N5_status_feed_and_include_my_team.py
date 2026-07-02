"""Iter 232N.5 — Player status feed endpoint + include_my_team filter.

Covers:
  (1) GET /player-status/feed?scope=user returns grouped-by-player
      buckets across all the caller's notifications.
  (2) scope=league filters to notifications with matching league_id.
  (3) scope=team + team_id filters by that team's current roster
      (`reason.player_id` IN roster).
  (4) `days=` cutoff drops notifications older than the window.
  (5) Legacy notifications missing `reason.player_id` are silently
      excluded (feed only surfaces groupable rows).
  (6) /players?include_my_team=true bypasses `exclude_team_id`.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

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


async def _make_notif(db, *, user_id, player_id, player_name, flag, value,
                     league_id=None, ts=None):
    doc = {
        "user_id": user_id,
        "type": "player_status_change",
        "title": f"{player_name}: {flag}={value}",
        "message": "…",
        "league_id": league_id,
        "link": f"/players/{player_id}",
        "reason": {
            "flag": flag, "value": bool(value),
            "player_id": str(player_id), "player_name": player_name,
        },
        "read": False,
        "created_at": (ts or datetime.now(timezone.utc)).isoformat(),
    }
    r = await db.notifications.insert_one(doc)
    return str(r.inserted_id)


@pytest.mark.asyncio
async def test_feed_groups_by_player_and_sorts_by_recency(db):
    from routes import notifications as notifs_route
    from routes.notifications import get_player_status_feed

    async def _fake_user(request):
        return {"_id": user_id}

    user_id = str(ObjectId())
    notifs_route.setup({"db": db, "get_current_user": _fake_user})

    pid_a = str(ObjectId())
    pid_b = str(ObjectId())
    now = datetime.now(timezone.utc)
    older = await _make_notif(db, user_id=user_id, player_id=pid_a,
                              player_name="Alpha", flag="injured", value=True,
                              ts=now - timedelta(hours=6))
    newer = await _make_notif(db, user_id=user_id, player_id=pid_a,
                              player_name="Alpha", flag="injured", value=False,
                              ts=now - timedelta(hours=1))
    other = await _make_notif(db, user_id=user_id, player_id=pid_b,
                              player_name="Bravo", flag="in_minors", value=True,
                              ts=now - timedelta(hours=3))

    class R:
        pass
    res = await get_player_status_feed(R(), scope="user", days=7)  # type: ignore[arg-type]
    players = res["players"]
    assert len(players) == 2
    # Most-recent player first (Alpha with newer at 1h ago).
    assert players[0]["player_id"] == pid_a
    # Within a player's list, most-recent update comes first.
    assert players[0]["updates"][0]["value"] is False  # cleared
    assert players[0]["updates"][1]["value"] is True   # placed on IR
    # Total across the whole payload.
    assert res["total_updates"] == 3

    await db.notifications.delete_many({"_id": {"$in": [
        ObjectId(older), ObjectId(newer), ObjectId(other),
    ]}})


@pytest.mark.asyncio
async def test_feed_scope_league_filters_by_league_id(db):
    from routes import notifications as notifs_route
    from routes.notifications import get_player_status_feed

    user_id = str(ObjectId())
    la = str(ObjectId())
    lb = str(ObjectId())

    async def _fake_user(request):
        return {"_id": user_id}
    notifs_route.setup({"db": db, "get_current_user": _fake_user})

    p1 = str(ObjectId())
    p2 = str(ObjectId())
    n1 = await _make_notif(db, user_id=user_id, player_id=p1, player_name="P1",
                           flag="injured", value=True, league_id=la)
    n2 = await _make_notif(db, user_id=user_id, player_id=p2, player_name="P2",
                           flag="in_minors", value=True, league_id=lb)

    class R:
        pass
    res = await get_player_status_feed(R(), scope="league", league_id=la, days=7)  # type: ignore[arg-type]
    ids = {p["player_id"] for p in res["players"]}
    assert p1 in ids and p2 not in ids

    await db.notifications.delete_many({"_id": {"$in": [ObjectId(n1), ObjectId(n2)]}})


@pytest.mark.asyncio
async def test_feed_scope_team_filters_by_roster(db):
    from routes import notifications as notifs_route
    from routes.notifications import get_player_status_feed

    user_id = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()

    async def _fake_user(request):
        return {"_id": user_id}
    notifs_route.setup({"db": db, "get_current_user": _fake_user})

    rostered_pid = str(ObjectId())
    off_roster_pid = str(ObjectId())
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "roster": [rostered_pid],
    })
    n1 = await _make_notif(db, user_id=user_id, player_id=rostered_pid,
                           player_name="Rostered", flag="injured",
                           value=True, league_id=league_id)
    n2 = await _make_notif(db, user_id=user_id, player_id=off_roster_pid,
                           player_name="OffRoster", flag="in_minors",
                           value=True, league_id=league_id)

    class R:
        pass
    res = await get_player_status_feed(R(), scope="team", team_id=str(team_id), days=7)  # type: ignore[arg-type]
    ids = {p["player_id"] for p in res["players"]}
    assert rostered_pid in ids
    assert off_roster_pid not in ids

    await db.notifications.delete_many({"_id": {"$in": [ObjectId(n1), ObjectId(n2)]}})
    await db.teams.delete_one({"_id": team_id})


@pytest.mark.asyncio
async def test_feed_days_cutoff_drops_stale(db):
    from routes import notifications as notifs_route
    from routes.notifications import get_player_status_feed

    user_id = str(ObjectId())

    async def _fake_user(request):
        return {"_id": user_id}
    notifs_route.setup({"db": db, "get_current_user": _fake_user})

    now = datetime.now(timezone.utc)
    fresh = await _make_notif(db, user_id=user_id, player_id=str(ObjectId()),
                              player_name="Fresh", flag="injured", value=True,
                              ts=now - timedelta(hours=1))
    stale = await _make_notif(db, user_id=user_id, player_id=str(ObjectId()),
                              player_name="Stale", flag="injured", value=True,
                              ts=now - timedelta(days=30))

    class R:
        pass
    res = await get_player_status_feed(R(), scope="user", days=7)  # type: ignore[arg-type]
    names = {p["player_name"] for p in res["players"]}
    assert "Fresh" in names
    assert "Stale" not in names

    await db.notifications.delete_many({"_id": {"$in": [ObjectId(fresh), ObjectId(stale)]}})


@pytest.mark.asyncio
async def test_feed_drops_notifications_without_reason_player_id(db):
    from routes import notifications as notifs_route
    from routes.notifications import get_player_status_feed

    user_id = str(ObjectId())

    async def _fake_user(request):
        return {"_id": user_id}
    notifs_route.setup({"db": db, "get_current_user": _fake_user})

    # Legacy notification without reason.player_id.
    legacy = await db.notifications.insert_one({
        "user_id": user_id, "type": "player_status_change",
        "title": "Legacy row", "message": "…",
        "reason": {"flag": "injured", "value": True},
        "created_at": datetime.now(timezone.utc).isoformat(), "read": False,
    })

    class R:
        pass
    res = await get_player_status_feed(R(), scope="user", days=7)  # type: ignore[arg-type]
    assert res["players"] == []

    await db.notifications.delete_one({"_id": legacy.inserted_id})


@pytest.mark.asyncio
async def test_players_include_my_team_bypasses_exclude(db):
    """`include_my_team=true` should stop `/players` from excluding
    the caller's own roster via `exclude_team_id`."""
    from routes import players as players_routes
    from routes.players import get_players

    user_id = str(ObjectId())
    league_id = str(ObjectId())
    team_id = ObjectId()
    sfx = uuid.uuid4().hex[:8]

    async def _fake_user(request):
        return {"_id": user_id}

    def _fake_calc(stats, cfg):
        return 0.0

    players_routes.setup({
        "db": db, "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })

    mine = await db.players.insert_one({
        "name": f"Mine {sfx}", "position": "C", "points": 50,
        "player_type": "skater", "nhl_id": f"iter232N5-mine-{sfx}",
    })
    fa = await db.players.insert_one({
        "name": f"FreeAgent {sfx}", "position": "C", "points": 40,
        "player_type": "skater", "nhl_id": f"iter232N5-fa-{sfx}",
    })
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "owner_id": user_id,
        "roster": [str(mine.inserted_id)],
    })

    class R:
        pass

    # Default (include_my_team=false) → excludes the caller's roster.
    res_default = await get_players(
        request=R(),  # type: ignore[arg-type]
        search=sfx, league_id=league_id,
        exclude_team_id=str(team_id), limit=10,
    )
    names_default = {p["name"] for p in res_default["players"]}
    assert f"Mine {sfx}" not in names_default
    assert f"FreeAgent {sfx}" in names_default

    # include_my_team=true → mine is now included.
    res_include = await get_players(
        request=R(),  # type: ignore[arg-type]
        search=sfx, league_id=league_id,
        exclude_team_id=str(team_id), include_my_team=True, limit=10,
    )
    names_include = {p["name"] for p in res_include["players"]}
    assert f"Mine {sfx}" in names_include
    assert f"FreeAgent {sfx}" in names_include

    await db.players.delete_many({"_id": {"$in": [mine.inserted_id, fa.inserted_id]}})
    await db.teams.delete_one({"_id": team_id})

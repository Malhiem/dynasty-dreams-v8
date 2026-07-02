"""Iter 232N.2 — Shared player_status helper + undrafted_only filter.

Covers:
  (1) `compute_player_status_flags` returns the correct shape for
      injured / minors / unsigned / undrafted variants.
  (2) `get_previously_drafted_pids` union across league drafts.
  (3) `undrafted_only=true` filter shrinks the eligible + players +
      waivers responses to only never-drafted-in-this-league players.
  (4) `status_flags` now surfaces on /players, /waivers/available, and
      /roster/{team_id} (shared helper — Roster page can render badges).
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

from routes.player_status import (  # noqa: E402
    compute_player_status_flags,
    get_previously_drafted_pids,
)


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


# ─── (1) compute_player_status_flags — shape ────────────────────
def test_compute_flags_healthy_nhl_player_none_true():
    flags = compute_player_status_flags({
        "_id": ObjectId(), "player_type": "skater", "roster_status": "active",
    }, previously_drafted_pids=set())
    # Never-drafted NHL player: only undrafted=True.
    assert flags == {"injured": False, "in_minors": False, "unsigned": False, "undrafted": True}


def test_compute_flags_injured_prospect_in_minors_and_unsigned():
    pid = ObjectId()
    flags = compute_player_status_flags({
        "_id": pid, "player_type": "prospect", "amateur_league": "AHL",
        "roster_status": "IR", "signed": False,
    }, previously_drafted_pids=set())
    # Multi-badge case — everything true simultaneously.
    assert flags["injured"] is True
    assert flags["in_minors"] is True
    assert flags["unsigned"] is True
    assert flags["undrafted"] is True


def test_compute_flags_undrafted_defaults_false_when_set_is_none():
    """Without a set, `undrafted` must stay False (safer than
    misleadingly stamping True on unknown context)."""
    flags = compute_player_status_flags({
        "_id": ObjectId(), "player_type": "skater",
    })
    assert flags["undrafted"] is False


def test_compute_flags_previously_drafted_not_undrafted():
    pid = ObjectId()
    flags = compute_player_status_flags(
        {"_id": pid, "player_type": "prospect"},
        previously_drafted_pids={str(pid)},
    )
    assert flags["undrafted"] is False


# ─── (2) get_previously_drafted_pids ────────────────────────────
@pytest.mark.asyncio
async def test_previously_drafted_pids_unions_all_league_drafts(db):
    league_id = str(ObjectId())
    d1 = ObjectId()
    d2 = ObjectId()
    pid1 = str(ObjectId())
    pid2 = str(ObjectId())
    pid3 = str(ObjectId())
    await db.drafts.insert_many([
        {"_id": d1, "league_id": league_id, "status": "completed",
         "picks": [{"player_id": pid1}, {"player_id": pid2}]},
        {"_id": d2, "league_id": league_id, "status": "active",
         "picks": [{"player_id": pid3}]},
    ])

    pids = await get_previously_drafted_pids(db, league_id)
    assert pids == {pid1, pid2, pid3}

    # exclude_draft_id drops the excluded draft's picks
    pids2 = await get_previously_drafted_pids(db, league_id, exclude_draft_id=d2)
    assert pids2 == {pid1, pid2}

    await db.drafts.delete_many({"_id": {"$in": [d1, d2]}})


# ─── (3) undrafted_only filter — eligible-players endpoint ──────
@pytest.mark.asyncio
async def test_eligible_players_undrafted_only_excludes_prior_picks(db):
    from routes import draft_inspection
    from routes.draft_inspection import get_draft_eligible_players
    draft_inspection.setup({"db": db})

    league_id = str(ObjectId())
    prev_draft_id = ObjectId()
    cur_draft_id = ObjectId()
    sfx = uuid.uuid4().hex[:8]

    prev_picked = await db.players.insert_one({
        "name": f"Prev Picked {sfx}", "position": "C",
        "player_type": "prospect", "amateur_league": "OHL",
        "nhl_id": f"iter232N2-pp-{sfx}",
    })
    fresh_a = await db.players.insert_one({
        "name": f"Fresh A {sfx}", "position": "C",
        "player_type": "prospect", "amateur_league": "OHL",
        "nhl_id": f"iter232N2-fa-{sfx}",
    })
    fresh_b = await db.players.insert_one({
        "name": f"Fresh B {sfx}", "position": "LW",
        "player_type": "prospect", "amateur_league": "WHL",
        "nhl_id": f"iter232N2-fb-{sfx}",
    })
    prev_pid = str(prev_picked.inserted_id)

    await db.drafts.insert_many([
        {"_id": prev_draft_id, "league_id": league_id, "status": "completed",
         "picks": [{"player_id": prev_pid}]},
        {"_id": cur_draft_id, "league_id": league_id, "status": "active",
         "player_criteria": "prospects", "picks": []},
    ])

    # Without the filter — all 3 prospects appear.
    res_all = await get_draft_eligible_players(str(cur_draft_id), search=sfx, limit=50)
    names_all = {p["name"] for p in res_all["players"]}
    assert f"Prev Picked {sfx}" in names_all
    assert f"Fresh A {sfx}" in names_all
    assert f"Fresh B {sfx}" in names_all

    # With undrafted_only — the prev-picked row is filtered out.
    res_und = await get_draft_eligible_players(
        str(cur_draft_id), search=sfx, undrafted_only=True, limit=50,
    )
    names_und = {p["name"] for p in res_und["players"]}
    assert f"Prev Picked {sfx}" not in names_und
    assert f"Fresh A {sfx}" in names_und
    assert f"Fresh B {sfx}" in names_und

    await db.players.delete_many({"_id": {"$in": [
        prev_picked.inserted_id, fresh_a.inserted_id, fresh_b.inserted_id,
    ]}})
    await db.drafts.delete_many({"_id": {"$in": [prev_draft_id, cur_draft_id]}})


# ─── (4) status_flags on /players + /waivers/available + /roster ─
@pytest.mark.asyncio
async def test_players_endpoint_stamps_status_flags(db):
    from routes import players as players_routes
    from routes.players import get_players

    async def _fake_user(request):
        return {"_id": str(ObjectId())}

    def _fake_calc(stats, cfg):
        return 0.0

    players_routes.setup({
        "db": db,
        "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    prev_draft_id = ObjectId()
    prev = await db.players.insert_one({
        "name": f"P Prev {sfx}", "position": "C", "player_type": "prospect",
        "amateur_league": "OHL", "points": 50, "nhl_id": f"iter232N2-Pp-{sfx}",
    })
    fresh = await db.players.insert_one({
        "name": f"P Fresh {sfx}", "position": "C", "player_type": "prospect",
        "amateur_league": "WHL", "points": 40, "nhl_id": f"iter232N2-Pf-{sfx}",
    })
    await db.drafts.insert_one({
        "_id": prev_draft_id, "league_id": league_id, "status": "completed",
        "picks": [{"player_id": str(prev.inserted_id)}],
    })

    class FakeRequest:  # minimal — /players' _get_user is wrapped in try/except
        pass

    res = await get_players(
        request=FakeRequest(),  # type: ignore[arg-type]
        search=sfx, league_id=league_id, limit=10,
    )
    by_name = {p["name"]: p for p in res["players"]}
    assert by_name[f"P Prev {sfx}"]["status_flags"]["undrafted"] is False
    assert by_name[f"P Fresh {sfx}"]["status_flags"]["undrafted"] is True

    # Now with undrafted_only=True — the previously-drafted row should
    # NOT appear in the response at all.
    res_und = await get_players(
        request=FakeRequest(),  # type: ignore[arg-type]
        search=sfx, league_id=league_id, undrafted_only=True, limit=10,
    )
    names_und = {p["name"] for p in res_und["players"]}
    assert f"P Prev {sfx}" not in names_und
    assert f"P Fresh {sfx}" in names_und

    await db.players.delete_many({"_id": {"$in": [prev.inserted_id, fresh.inserted_id]}})
    await db.drafts.delete_one({"_id": prev_draft_id})


@pytest.mark.asyncio
async def test_waivers_available_stamps_status_flags_and_filters(db):
    from routes import waivers as waivers_routes
    from routes.waivers import get_waiver_players
    waivers_routes.setup({"db": db})

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    prev_draft_id = ObjectId()
    prev = await db.players.insert_one({
        "name": f"W Prev {sfx}", "position": "C", "player_type": "prospect",
        "amateur_league": "OHL", "points": 30, "nhl_id": f"iter232N2-Wp-{sfx}",
    })
    fresh = await db.players.insert_one({
        "name": f"W Fresh {sfx}", "position": "LW", "player_type": "prospect",
        "amateur_league": "WHL", "points": 25, "nhl_id": f"iter232N2-Wf-{sfx}",
    })
    await db.drafts.insert_one({
        "_id": prev_draft_id, "league_id": league_id, "status": "completed",
        "picks": [{"player_id": str(prev.inserted_id)}],
    })

    res = await get_waiver_players(league_id=league_id, search=sfx, limit=50)
    by_name = {p["name"]: p for p in res["players"]}
    assert by_name[f"W Prev {sfx}"]["status_flags"]["undrafted"] is False
    assert by_name[f"W Fresh {sfx}"]["status_flags"]["undrafted"] is True

    res_und = await get_waiver_players(
        league_id=league_id, search=sfx, undrafted_only=True, limit=50,
    )
    names_und = {p["name"] for p in res_und["players"]}
    assert f"W Prev {sfx}" not in names_und
    assert f"W Fresh {sfx}" in names_und

    await db.players.delete_many({"_id": {"$in": [prev.inserted_id, fresh.inserted_id]}})
    await db.drafts.delete_one({"_id": prev_draft_id})


@pytest.mark.asyncio
async def test_roster_endpoint_stamps_status_flags(db):
    from routes import roster as roster_routes
    from routes.roster import get_roster

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    user_id = str(ObjectId())
    team_id = ObjectId()

    async def _fake_user(request):
        return {"_id": user_id, "role": "admin", "email": "test@example.com"}

    def _fake_calc(player, cfg):
        return 12.0

    roster_routes.setup({
        "db": db,
        "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })

    player = await db.players.insert_one({
        "name": f"R {sfx}", "position": "C", "player_type": "prospect",
        "amateur_league": "AHL", "roster_status": "minors",
        "nhl_id": f"iter232N2-R-{sfx}",
    })
    pid = str(player.inserted_id)
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "name": "Roster Team",
        "owner_id": user_id, "roster": [pid], "lineup": {},
    })

    class FakeRequest:
        pass

    try:
        res = await get_roster(str(team_id), FakeRequest())  # type: ignore[arg-type]
        by_name = {p["name"]: p for p in res["players"]}
        assert f"R {sfx}" in by_name
        flags = by_name[f"R {sfx}"]["status_flags"]
        assert flags["in_minors"] is True
        assert flags["undrafted"] is True  # no prior league drafts
    finally:
        await db.players.delete_one({"_id": player.inserted_id})
        await db.teams.delete_one({"_id": team_id})

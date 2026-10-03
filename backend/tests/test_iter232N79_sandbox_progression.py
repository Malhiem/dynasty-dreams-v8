"""Iter 232N.79 — Sandbox progression (Setup → Draft → Weeks → Playoffs).

Covers:
  1. `/status` endpoint reports 4-step progression correctly.
  2. `simulate-week` refuses when the draft isn't complete (bug fix).
  3. `simulate-draft` auto-fills every team's roster + writes a
     `status="completed"` draft doc.
  4. After a completed simulate-draft, `simulate-week` unlocks and
     works end-to-end.
  5. `seed-playoffs` stamps `championship_won_at` on the champion team
     AND writes a `league_seasons` sandbox snapshot so the existing
     Trophy Room UI renders the championship banner automatically.
  6. `reset-simulation` wipes the sim draft, the season snapshot,
     rosters, and the `championship_won_at` stamp — league is truly
     "day 1" after a reset.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


class _StubReq:
    def __init__(self):
        self.headers = {}
        self.cookies = {}


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n79_{str(uid)[:6]}@iter.test",
        "name": "N79 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=4, roster_spots=3, with_players=True):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N79 Progression Sandbox",
        "is_test_sandbox": True,
        "roster_spots": roster_spots,
        "matchups_per_week": 1,
    })
    for i in range(num_teams):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "league_id": str(league_id),
            "name": f"N79 Team {i}",
            "created_at": datetime.now(timezone.utc),
            "roster": [],
        })
    seeded_pids = []
    if with_players:
        # Use a per-test unique nhl_id prefix so we don't collide with
        # the platform's unique index or other test suites.
        prefix = f"n79-{str(league_id)[:6]}"
        for i in range(num_teams * roster_spots + 4):
            pid = ObjectId()
            await db.players.insert_one({
                "_id": pid, "name": f"N79 Player {i}",
                "nhl_id": f"{prefix}-{i}",
                "position": "C", "team": "TOR", "league": "NHL",
                "age": 25 + (i % 10),
                "is_prospect": False,
                "season_stats": {"points": 100 - i},
                "n79_test": True,
            })
            seeded_pids.append(pid)
    return str(league_id), seeded_pids


async def _cleanup(db, league_id, admin_id, pids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.matchups.delete_many({"league_id": league_id})
    await db.drafts.delete_many({"league_id": league_id})
    await db.league_seasons.delete_many({"league_id": league_id})
    if pids:
        await db.players.delete_many({"_id": {"$in": pids}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Status endpoint reports progression correctly ─────────────────

@pytest.mark.asyncio
async def test_status_reports_progression_states():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4)

    # Step 1 → complete (settings + teams present), Step 2 → active.
    st = await m.sandbox_status(league_id, _StubReq())
    assert st["has_settings"] is True
    assert st["draft_done"] is False
    assert st["active_step"] == 2

    # After sim-draft, Step 3 unlocks.
    await m.sandbox_simulate_draft(
        league_id, m.SimulateDraftRequest(), _StubReq(),
    )
    st = await m.sandbox_status(league_id, _StubReq())
    assert st["draft_done"] is True
    assert st["draft_status"] == "completed"
    assert st["active_step"] == 3

    await _cleanup(db, league_id, admin_id, pids)


# ── Simulate-week gate: refuses when draft isn't complete ─────────

@pytest.mark.asyncio
async def test_simulate_week_refuses_without_completed_draft():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4)

    with pytest.raises(HTTPException) as exc:
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=1), _StubReq(),
        )
    assert exc.value.status_code == 400
    assert "draft" in exc.value.detail.lower()

    await _cleanup(db, league_id, admin_id, pids)


# ── simulate-draft fills every roster + creates completed draft ───

@pytest.mark.asyncio
async def test_simulate_draft_fills_rosters():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4, roster_spots=3)

    res = await m.sandbox_simulate_draft(
        league_id, m.SimulateDraftRequest(), _StubReq(),
    )
    assert res["ok"] is True
    assert res["teams_drafted"] == 4
    assert res["picks_per_team"] == 3
    assert res["total_picks"] == 12

    # Every team's roster has 3 players.
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    for t in teams:
        assert len(t.get("roster") or []) == 3

    # A completed draft doc exists.
    drafts = await db.drafts.find({
        "league_id": league_id, "sandbox_sim_draft": True,
    }).to_list(10)
    assert len(drafts) == 1
    assert drafts[0]["status"] == "completed"

    await _cleanup(db, league_id, admin_id, pids)


# ── Full happy path: draft → sim-week → playoffs → trophy ─────────

@pytest.mark.asyncio
async def test_full_progression_stamps_trophy():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4, roster_spots=3)

    # Step 2 — simulate draft.
    await m.sandbox_simulate_draft(
        league_id, m.SimulateDraftRequest(), _StubReq(),
    )
    # Step 3 — simulate a couple weeks.
    for wk in (1, 2, 3):
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=wk), _StubReq(),
        )
    # Step 4 — seed playoffs with min_week=3 for a fast test.
    result = await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )
    assert result["champion"] is not None
    champ_id = result["champion_team_id"]

    # Champion team has the trophy stamp.
    champ = await db.teams.find_one({"_id": ObjectId(champ_id)})
    assert champ.get("championship_won_at") is not None

    # league_seasons snapshot exists so the trophy-room endpoint renders.
    snap = await db.league_seasons.find_one({
        "league_id": league_id, "sandbox_sim": True,
    })
    assert snap is not None
    assert snap["champion_team_id"] == champ_id
    # The champion team's awards dict has championship_won_at set.
    champ_snap = next(
        (t for t in snap["teams"] if t["team_id"] == champ_id), None,
    )
    assert champ_snap is not None
    assert champ_snap["awards"]["championship_won_at"] is not None
    # Non-champion teams don't get the stamp.
    non_champs = [t for t in snap["teams"] if t["team_id"] != champ_id]
    assert all(t["awards"]["championship_won_at"] is None for t in non_champs)

    await _cleanup(db, league_id, admin_id, pids)


# ── Reset returns sandbox to "day 1" (rosters + trophy cleared) ────

@pytest.mark.asyncio
async def test_reset_wipes_progression_state():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4, roster_spots=3)

    await m.sandbox_simulate_draft(
        league_id, m.SimulateDraftRequest(), _StubReq(),
    )
    for wk in (1, 2, 3):
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=wk), _StubReq(),
        )
    await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )

    await m.sandbox_reset_simulation(league_id, _StubReq())

    # Every team roster empty, no championship stamp anywhere.
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    for t in teams:
        assert (t.get("roster") or []) == []
        assert t.get("championship_won_at") is None
    # No sandbox draft doc.
    assert await db.drafts.count_documents({
        "league_id": league_id, "sandbox_sim_draft": True,
    }) == 0
    # No sandbox season snapshot.
    assert await db.league_seasons.count_documents({
        "league_id": league_id, "sandbox_sim": True,
    }) == 0
    # League pointers cleared.
    lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert lg.get("sandbox_last_sim_week") is None
    assert lg.get("sandbox_playoff_champion_team_id") is None

    # After reset, `status` reports Step 2 again (draft not complete).
    st = await m.sandbox_status(league_id, _StubReq())
    assert st["active_step"] == 2
    assert st["draft_done"] is False

    await _cleanup(db, league_id, admin_id, pids)

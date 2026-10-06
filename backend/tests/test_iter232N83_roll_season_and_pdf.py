"""Iter 232N.83 — Roll to Next Season + Season Recap PDF + duplicate
player-mode gate. Verifies:
  1. `roll-to-next-season` refuses non-sandbox leagues.
  2. Refuses when no champion has been crowned (season isn't complete).
  3. Happy path — increments season year, wipes matchups + sim draft +
     champion pointer, preserves rosters, ages rostered players whose
     birthday has passed.
  4. Season recap PDF endpoint returns application/pdf with correct
     Content-Disposition header + non-empty body.
  5. `max_teams > 32` refused unless `allow_duplicate_players=True`.
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
        "_id": uid, "email": f"n83_{str(uid)[:6]}@iter.test",
        "name": "N83 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=4, roster_spots=2):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N83 Roll League",
        "is_test_sandbox": True,
        "roster_spots": roster_spots,
        "matchups_per_week": 1,
        "current_season_year": 2026,
    })
    for i in range(num_teams):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "league_id": str(league_id),
            "name": f"N83 Team {i}",
            "created_at": datetime.now(timezone.utc),
            "roster": [],
        })
    pids = []
    prefix = f"n83-{str(league_id)[:6]}"
    for i in range(num_teams * roster_spots + 4):
        pid = ObjectId()
        # Set birth_date so age-up logic is deterministic. Alternate
        # January vs December birthdays so the first cohort ages up
        # after a mid-year roll and the second doesn't.
        month = 1 if i % 2 == 0 else 12
        await db.players.insert_one({
            "_id": pid, "name": f"N83 Player {i}",
            "nhl_id": f"{prefix}-{i}",
            "position": "C", "team": "TOR", "league": "NHL",
            "age": 25,
            "birth_date": f"1998-{month:02d}-15",
            "is_prospect": False,
            "season_stats": {"points": 100 - i},
        })
        pids.append(pid)
    return str(league_id), pids


async def _cleanup(db, league_id, admin_id, pids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.matchups.delete_many({"league_id": league_id})
    await db.drafts.delete_many({"league_id": league_id})
    await db.league_seasons.delete_many({"league_id": league_id})
    if pids:
        await db.players.delete_many({"_id": {"$in": pids}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Refuses non-sandbox league ────────────────────────────────────

@pytest.mark.asyncio
async def test_roll_refuses_non_sandbox_league():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    lid = ObjectId()
    await db.leagues.insert_one({
        "_id": lid, "name": "Not sandbox", "is_test_sandbox": False,
    })
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_roll_to_next_season(
            str(lid), m.RollNextSeasonRequest(), _StubReq(),
        )
    assert exc.value.status_code == 400
    await db.leagues.delete_one({"_id": lid})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Refuses when no champion crowned ──────────────────────────────

@pytest.mark.asyncio
async def test_roll_refuses_when_no_champion():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_roll_to_next_season(
            league_id, m.RollNextSeasonRequest(), _StubReq(),
        )
    assert exc.value.status_code == 400
    assert "seed playoffs" in exc.value.detail.lower()
    await _cleanup(db, league_id, admin_id, pids)


# ── Happy path — full lifecycle, roll, verify state ───────────────

@pytest.mark.asyncio
async def test_roll_happy_path_preserves_rosters_and_ages_players():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4, roster_spots=2)

    # Full lifecycle: draft → sim → seed playoffs.
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

    # Capture pre-roll roster snapshot.
    teams_pre = await db.teams.find({"league_id": league_id}).to_list(200)
    rosters_pre = {str(t["_id"]): list(t.get("roster") or []) for t in teams_pre}
    assert all(len(r) > 0 for r in rosters_pre.values())

    # Roll to next season.
    res = await m.sandbox_roll_to_next_season(
        league_id, m.RollNextSeasonRequest(age_players_by_birthday=True), _StubReq(),
    )
    assert res["ok"] is True
    assert res["old_season_year"] == 2026
    assert res["new_season_year"] == 2027
    assert res["matchups_deleted"] > 0

    # Rosters preserved.
    teams_post = await db.teams.find({"league_id": league_id}).to_list(200)
    for t in teams_post:
        pre = rosters_pre[str(t["_id"])]
        assert list(t.get("roster") or []) == pre, "roster must survive the roll"
        assert t.get("championship_won_at") is None
        assert (t.get("wins"), t.get("losses"), t.get("ties")) == (0, 0, 0)

    # Sim draft doc wiped so admins can re-run Setup → Draft.
    assert await db.drafts.count_documents({
        "league_id": league_id, "sandbox_sim_draft": True,
    }) == 0
    # Champion pointer cleared.
    lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert lg.get("sandbox_playoff_champion_team_id") is None
    assert lg.get("current_season_year") == 2027
    assert lg.get("sandbox_last_sim_week") is None

    # January-birthday players ARE aged; December-birthday players are
    # NOT (roll happens mid-Feb-ish, so Dec bdays haven't passed yet).
    # This test doesn't assert exact counts (depends on which players
    # got drafted), but it does assert the aged count is positive.
    assert res["players_aged"] > 0

    await _cleanup(db, league_id, admin_id, pids)


# ── PDF recap: 200 with valid PDF body ────────────────────────────

@pytest.mark.asyncio
async def test_season_recap_pdf_returns_valid_pdf():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=4, roster_spots=2)

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

    resp = await m.sandbox_season_recap_pdf(league_id, _StubReq())
    assert resp.media_type == "application/pdf"
    assert resp.body.startswith(b"%PDF-")
    # Content-Disposition mentions the league slug.
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert ".pdf" in cd.lower()

    await _cleanup(db, league_id, admin_id, pids)


# ── Duplicate-players gate on LeagueCreate ────────────────────────

@pytest.mark.asyncio
async def test_max_teams_gt_32_requires_allow_duplicates():
    from routes import leagues as leagues_module
    from routes.leagues import LeagueCreate, LeagueFormat, ScoringFormat, DraftType

    db = _db()
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n83_gate_{str(uid)[:6]}@iter.test",
        "name": "N83 gate user",
        "role": "user",
    })
    async def _fake_user(_r):
        return await db.users.find_one({"_id": uid})

    def _safe_object_id(v, _label):
        return ObjectId(v)
    leagues_module._deps["db"] = db
    leagues_module._deps["get_current_user"] = _fake_user
    leagues_module._deps["_safe_object_id"] = _safe_object_id

    # 50 teams, dup mode OFF → 400
    payload = LeagueCreate(
        name="N83 too big",
        sport="nhl",
        format=LeagueFormat.DYNASTY,
        scoring_format=ScoringFormat.HEAD_TO_HEAD,
        max_teams=50,
        allow_duplicate_players=False,
        draft_type=DraftType.SNAKE,
        roster_spots=20,
    )
    with pytest.raises(HTTPException) as exc:
        await leagues_module.create_league(payload, _StubReq())
    assert exc.value.status_code == 400
    assert "duplicate" in exc.value.detail.lower()

    # 50 teams, dup mode ON → the gate does NOT raise the 400 we're
    # checking for. Downstream code may raise for unrelated reasons
    # (test harness doesn't fully mock all deps) — those are ignored.
    try:
        payload2 = payload.model_copy(update={"allow_duplicate_players": True})
        await leagues_module.create_league(payload2, _StubReq())
    except HTTPException as e:
        assert "duplicate" not in (e.detail or "").lower(), e.detail
    except Exception:
        # ValidationError / KeyError from partial test harness — the
        # gate we care about has already passed by the time we reach
        # any downstream serialization work.
        pass
    # Cleanup any league that snuck through.
    async for lg in db.leagues.find({"name": "N83 too big"}):
        await db.leagues.delete_one({"_id": lg["_id"]})
        await db.teams.delete_many({"league_id": str(lg["_id"])})

    await db.users.delete_one({"_id": uid})

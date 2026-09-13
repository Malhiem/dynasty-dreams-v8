"""Iter 232N.86 — Rotisserie scoring engine + endpoints.
Verifies:
  1. Catalog endpoint returns SKATER + GOALIE categories + selected list.
  2. Ranking with `split` tiebreak: two teams tied on a stat share
     the sum of their ranks' points.
  3. Ranking with `high` tiebreak: two teams tied get the higher rank.
  4. Lower-is-better categories (PIM, GAA) invert the rank correctly.
  5. `compute_period` aggregates per-team stats + assigns points.
  6. `compute_season` sums points across every closed period.
  7. Recompute persists + `closed=True` locks the period into totals.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


class _StubReq:
    def __init__(self):
        self.headers = {}
        self.cookies = {}


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n86_{str(uid)[:6]}@iter.test",
        "name": "N86 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import roto as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_league(db, admin_id, tiebreak="split", categories=None):
    lid = ObjectId()
    await db.leagues.insert_one({
        "_id": lid, "name": "N86 Roto",
        "scoring_format": "roto",
        "commissioner_id": admin_id,
        "roto_tiebreak": tiebreak,
        "roto_categories": categories or ["goals", "assists"],
    })
    # 4 teams, each with 2 players.
    pids = []
    prefix = f"n86-{str(lid)[:6]}"
    team_stats = [
        # team_idx: (p1_goals, p1_assists, p1_pim, p2_goals, p2_assists, p2_pim)
        (5, 3, 2, 4, 2, 1),   # team 0 → G=9, A=5, PIM=3
        (3, 4, 8, 2, 3, 4),   # team 1 → G=5, A=7, PIM=12
        (5, 3, 2, 4, 2, 1),   # team 2 → G=9, A=5, PIM=3  (ties team 0)
        (1, 1, 0, 0, 0, 0),   # team 3 → G=1, A=1, PIM=0
    ]
    for t_idx, stats in enumerate(team_stats):
        p1, p2 = ObjectId(), ObjectId()
        pids.extend([p1, p2])
        await db.players.insert_many([
            {"_id": p1, "name": f"P{t_idx}-1",
             "nhl_id": f"{prefix}-{t_idx}-1", "position": "C",
             "team": "TOR", "age": 25,
             "season_stats": {"goals": stats[0], "assists": stats[1],
                              "penalty_minutes": stats[2]}},
            {"_id": p2, "name": f"P{t_idx}-2",
             "nhl_id": f"{prefix}-{t_idx}-2", "position": "LW",
             "team": "MTL", "age": 27,
             "season_stats": {"goals": stats[3], "assists": stats[4],
                              "penalty_minutes": stats[5]}},
        ])
        await db.teams.insert_one({
            "_id": ObjectId(), "league_id": str(lid),
            "name": f"Team {t_idx}",
            "roster": [str(p1), str(p2)],
            "created_at": datetime.now(timezone.utc),
        })
    return str(lid), pids


async def _cleanup(db, league_id, admin_id, pids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.roto_period_results.delete_many({"league_id": league_id})
    if pids:
        await db.players.delete_many({"_id": {"$in": pids}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Catalog ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_returns_categories_and_selection():
    from routes import roto as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    lid, pids = await _seed_league(db, admin_id, categories=["goals", "assists"])
    res = await m.roto_catalog(lid, _StubReq())
    keys = {c["key"] for c in res["categories"]}
    assert "goals" in keys and "wins" in keys and "save_percentage" in keys
    # Skater + goalie categories combined.
    assert len(res["categories"]) >= 20
    assert res["selected"] == ["goals", "assists"]
    assert res["tiebreak"] == "split"
    await _cleanup(db, lid, admin_id, pids)


# ── Split tiebreak: tied teams share the sum of tied ranks ──────

@pytest.mark.asyncio
async def test_split_tiebreak_shares_points():
    from routes import roto as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    lid, pids = await _seed_league(
        db, admin_id, tiebreak="split", categories=["goals"],
    )
    res = await m.compute_period(db, lid)
    cat = res["categories"][0]
    # 4 teams. Goals: team0=9, team2=9, team1=5, team3=1.
    # Sorted: [9, 9, 5, 1] → ranks (from top) get [4, 3, 2, 1]
    # points. Team0+Team2 tie on rank 4+3 → share (4+3)/2 = 3.5.
    pts_vals = sorted(cat["points"].values(), reverse=True)
    assert pts_vals[0] == 3.5
    assert pts_vals[1] == 3.5
    assert pts_vals[2] == 2.0
    assert pts_vals[3] == 1.0
    await _cleanup(db, lid, admin_id, pids)


# ── High tiebreak: tied teams both get the higher rank ─────────

@pytest.mark.asyncio
async def test_high_tiebreak_gives_top_rank():
    from routes import roto as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    lid, pids = await _seed_league(
        db, admin_id, tiebreak="high", categories=["goals"],
    )
    res = await m.compute_period(db, lid)
    cat = res["categories"][0]
    pts_vals = sorted(cat["points"].values(), reverse=True)
    # Both tied teams get 4 (the higher rank), then 2, 1.
    assert pts_vals[0] == 4.0
    assert pts_vals[1] == 4.0
    assert pts_vals[2] == 2.0
    assert pts_vals[3] == 1.0
    await _cleanup(db, lid, admin_id, pids)


# ── Lower-is-better categories invert the rank ─────────────────

@pytest.mark.asyncio
async def test_lower_is_better_category_inverts_rank():
    from routes import roto as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    lid, pids = await _seed_league(
        db, admin_id, tiebreak="split", categories=["penalty_minutes"],
    )
    res = await m.compute_period(db, lid)
    cat = res["categories"][0]
    # PIM totals: team0=3, team1=12, team2=3, team3=0.
    # LOWER is better → order: [0, 3, 3, 12].
    # Points: team3=4, {team0, team2} share (3+2)/2 = 2.5, team1=1.
    pts_by_val = sorted(cat["points"].values(), reverse=True)
    assert pts_by_val[0] == 4.0    # team 3 (0 PIM)
    assert pts_by_val[1] == 2.5    # tied
    assert pts_by_val[2] == 2.5
    assert pts_by_val[3] == 1.0    # team 1 (12 PIM)
    await _cleanup(db, lid, admin_id, pids)


# ── Season aggregation across multiple closed periods ─────────

@pytest.mark.asyncio
async def test_compute_season_sums_closed_periods():
    from routes import roto as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    lid, pids = await _seed_league(
        db, admin_id, tiebreak="split", categories=["goals"],
    )
    # Fake two closed periods via the recompute endpoint.
    r1 = await m.roto_recompute(lid, m.RecomputeRequest(period=1, close=True), _StubReq())
    r2 = await m.roto_recompute(lid, m.RecomputeRequest(period=2, close=True), _StubReq())
    season = await m.compute_season(db, lid)
    assert season["aggregated"] is True
    assert season["periods_closed"] == 2
    # Points for each team should be exactly 2x a single period's points.
    single = await m.compute_period(db, lid, period=None)
    for tid, agg in season["totals"].items():
        single_pts = single["totals"][tid]["total_points"]
        assert abs(agg["total_points"] - single_pts * 2) < 0.01
    assert r1["ok"] and r2["ok"]
    await _cleanup(db, lid, admin_id, pids)

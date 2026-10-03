"""Iter 232N.85 — One-click bulk contract signings for sandbox testing.
Verifies:
  1. Non-sandbox refused.
  2. Happy path signs every rostered player, sets player.cap_hit,
     stamps bulk_signed=true, returns aggregate totals.
  3. Second run WITHOUT `overwrite_existing` skips players that
     already have an active contract (idempotent-friendly).
  4. Second run WITH `overwrite_existing=True` supersedes the prior
     active deal and creates a fresh one; old contract's status flips.
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
        "_id": uid, "email": f"n85_{str(uid)[:6]}@iter.test",
        "name": "N85 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=2, roster_size=3, is_sandbox=True):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N85 Bulk-Sign",
        "is_test_sandbox": is_sandbox,
        "current_season_year": 2026,
    })
    prefix = f"n85-{str(league_id)[:6]}"
    pids = []
    for i in range(num_teams * roster_size):
        pid = ObjectId()
        await db.players.insert_one({
            "_id": pid, "name": f"N85 Player {i}",
            "nhl_id": f"{prefix}-{i}",
            "position": "C", "team": "TOR", "league": "NHL",
            "age": 25,
            "is_prospect": False,
            "season_stats": {"points": 40 + i * 5},
            "cap_hit": 0,
        })
        pids.append(pid)
    for t_idx in range(num_teams):
        team_pids = [str(p) for p in pids[t_idx * roster_size:(t_idx + 1) * roster_size]]
        await db.teams.insert_one({
            "_id": ObjectId(), "league_id": str(league_id),
            "name": f"N85 Team {t_idx}",
            "roster": team_pids,
            "created_at": datetime.now(timezone.utc),
        })
    return str(league_id), pids


async def _cleanup(db, league_id, admin_id, pids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.contracts.delete_many({"league_id": league_id})
    if pids:
        await db.players.delete_many({"_id": {"$in": pids}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Non-sandbox refused ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_sign_refuses_non_sandbox():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, is_sandbox=False)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_bulk_sign_contracts(
            league_id, m.BulkSignContractsRequest(), _StubReq(),
        )
    assert exc.value.status_code == 400
    await _cleanup(db, league_id, admin_id, pids)


# ── Happy path: every rostered player gets signed ────────────────

@pytest.mark.asyncio
async def test_bulk_sign_happy_path():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=3, roster_size=4)

    res = await m.sandbox_bulk_sign_contracts(
        league_id, m.BulkSignContractsRequest(years=4), _StubReq(),
    )
    assert res["ok"] is True
    assert res["contracts_created"] == 12   # 3 × 4
    assert res["contracts_skipped"] == 0
    assert res["contracts_superseded"] == 0
    assert res["teams_touched"] == 3
    assert res["years"] == 4
    assert res["end_year"] == res["start_year"] + 3
    assert res["total_cap_committed"] > 0

    # DB reflects the state.
    count = await db.contracts.count_documents({
        "league_id": league_id, "status": "active", "bulk_signed": True,
    })
    assert count == 12
    # Every rostered player has non-zero cap_hit.
    for pid in pids:
        p = await db.players.find_one({"_id": pid})
        assert p["cap_hit"] > 0

    await _cleanup(db, league_id, admin_id, pids)


# ── Replay without overwrite → all skipped ───────────────────────

@pytest.mark.asyncio
async def test_bulk_sign_skips_existing_when_overwrite_false():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=2, roster_size=3)

    r1 = await m.sandbox_bulk_sign_contracts(
        league_id, m.BulkSignContractsRequest(), _StubReq(),
    )
    r2 = await m.sandbox_bulk_sign_contracts(
        league_id, m.BulkSignContractsRequest(), _StubReq(),
    )
    assert r1["contracts_created"] == 6
    assert r2["contracts_created"] == 0
    assert r2["contracts_skipped"] == 6
    # Still exactly 6 active contracts (no dupes created).
    count = await db.contracts.count_documents({
        "league_id": league_id, "status": "active",
    })
    assert count == 6

    await _cleanup(db, league_id, admin_id, pids)


# ── Replay WITH overwrite → prior deal superseded ────────────────

@pytest.mark.asyncio
async def test_bulk_sign_overwrite_supersedes_existing():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, pids = await _seed_sandbox(db, num_teams=2, roster_size=2)

    await m.sandbox_bulk_sign_contracts(
        league_id, m.BulkSignContractsRequest(years=3), _StubReq(),
    )
    r2 = await m.sandbox_bulk_sign_contracts(
        league_id,
        m.BulkSignContractsRequest(years=6, overwrite_existing=True),
        _StubReq(),
    )
    assert r2["contracts_created"] == 4
    assert r2["contracts_superseded"] == 4
    # Old contracts marked superseded, new ones active with years=6.
    superseded = await db.contracts.count_documents({
        "league_id": league_id, "status": "superseded",
    })
    active = await db.contracts.count_documents({
        "league_id": league_id, "status": "active",
    })
    assert superseded == 4
    assert active == 4
    active_docs = await db.contracts.find({
        "league_id": league_id, "status": "active",
    }).to_list(20)
    assert all(c["years"] == 6 for c in active_docs)

    await _cleanup(db, league_id, admin_id, pids)

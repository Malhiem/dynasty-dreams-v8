"""Iter 232N.84 — Salary Cap rollover during Roll to Next Season.
Verifies:
  1. Active contract → player.cap_hit stays synced to contract.aav
     across the roll boundary. Counter `contracts_synced` reports it.
  2. Expired contract (end_year < new_year) → contract.status flips
     to "expired", player.cap_hit + salary drop to 0 (player becomes
     a free agent — the follow-up signing updates cap_hit).
  3. Free-agent players (no active contract) are NOT touched.
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
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


class _StubReq:
    def __init__(self):
        self.headers = {}
        self.cookies = {}


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n84_{str(uid)[:6]}@iter.test",
        "name": "N84 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=2, roster_spots=2):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N84 Cap Roll",
        "is_test_sandbox": True,
        "roster_spots": roster_spots,
        "matchups_per_week": 1,
        "current_season_year": 2026,
    })
    for i in range(num_teams):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "league_id": str(league_id),
            "name": f"N84 Team {i}",
            "created_at": datetime.now(timezone.utc),
            "roster": [],
        })
    return str(league_id)


async def _cleanup(db, league_id, admin_id, pids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.matchups.delete_many({"league_id": league_id})
    await db.drafts.delete_many({"league_id": league_id})
    await db.league_seasons.delete_many({"league_id": league_id})
    await db.contracts.delete_many({"league_id": league_id})
    if pids:
        await db.players.delete_many({"_id": {"$in": pids}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Full cap rollover: active + expired + free agent ─────────────

@pytest.mark.asyncio
async def test_cap_rollover_syncs_active_and_expires_stale():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_sandbox(db, num_teams=2, roster_spots=2)

    prefix = f"n84-{league_id[:6]}"
    p_active = ObjectId()
    p_expired = ObjectId()
    p_free = ObjectId()
    await db.players.insert_many([
        {"_id": p_active, "name": "Active Star",
         "nhl_id": f"{prefix}-a", "position": "C",
         "team": "TOR", "league": "NHL", "age": 25,
         "is_prospect": False,
         "cap_hit": 8_000_000, "salary": 8_000_000,
         "season_stats": {"points": 90}},
        {"_id": p_expired, "name": "Expiring Vet",
         "nhl_id": f"{prefix}-b", "position": "D",
         "team": "MTL", "league": "NHL", "age": 34,
         "is_prospect": False,
         "cap_hit": 6_000_000, "salary": 6_000_000,
         "season_stats": {"points": 40}},
        {"_id": p_free, "name": "Free Agent",
         "nhl_id": f"{prefix}-c", "position": "LW",
         "team": None, "league": "NHL", "age": 30,
         "is_prospect": False,
         "cap_hit": 5_000_000, "salary": 5_000_000,
         "season_stats": {"points": 30}},
    ])
    # Assign the first two players to a roster; free-agent player
    # sits off-roster (should not be touched by the cap rollover).
    teams = await db.teams.find({"league_id": league_id}).to_list(4)
    await db.teams.update_one(
        {"_id": teams[0]["_id"]},
        {"$set": {"roster": [str(p_active), str(p_expired)]}},
    )

    # Active contract: end_year = 2028 (still valid after roll to 2027).
    await db.contracts.insert_one({
        "league_id": league_id, "team_id": str(teams[0]["_id"]),
        "player_id": str(p_active), "aav": 9_500_000,
        "start_year": 2025, "end_year": 2028,
        "status": "active",
    })
    # Expiring contract: end_year = 2026 (< new_year 2027 → expires).
    await db.contracts.insert_one({
        "league_id": league_id, "team_id": str(teams[0]["_id"]),
        "player_id": str(p_expired), "aav": 6_500_000,
        "start_year": 2024, "end_year": 2026,
        "status": "active",
    })

    # Fake progression + champion so roll succeeds.
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "sandbox_last_sim_week": 3,
            "sandbox_playoff_champion_team_id": str(teams[0]["_id"]),
            "sandbox_playoffs_seeded_at": datetime.now(timezone.utc).isoformat(),
            "sandbox_playoff_season_year": 2026,
        }},
    )

    res = await m.sandbox_roll_to_next_season(
        league_id, m.RollNextSeasonRequest(age_players_by_birthday=False), _StubReq(),
    )
    assert res["new_season_year"] == 2027
    assert res["contracts_synced"] == 1
    assert res["contracts_expired"] == 1

    # Active player: cap_hit synced to contract.aav.
    active_after = await db.players.find_one({"_id": p_active})
    assert active_after["cap_hit"] == 9_500_000

    # Expired player: cap_hit + salary cleared.
    expired_after = await db.players.find_one({"_id": p_expired})
    assert expired_after["cap_hit"] == 0
    assert expired_after["salary"] == 0
    expired_contract = await db.contracts.find_one({"player_id": str(p_expired)})
    assert expired_contract["status"] == "expired"

    # Off-roster free agent: untouched.
    free_after = await db.players.find_one({"_id": p_free})
    assert free_after["cap_hit"] == 5_000_000

    await _cleanup(db, league_id, admin_id, [p_active, p_expired, p_free])

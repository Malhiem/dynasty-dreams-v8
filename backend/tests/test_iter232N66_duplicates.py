"""Iter 232N.66 — Duplicate detection + merge pytest suite.

Covers:
  1. `find_db_duplicates` clusters same-name rows by name+birth_date
     (strong match) and by name-only when at least one sibling has a
     birth_date and no sibling has a conflicting DOB (Adam Fantilli
     pattern: Michigan row has no DOB, CBJ row has DOB → weak match).
  2. Rows with two different DOBs under the same name split into
     per-DOB sub-clusters (Sebastian Aho C vs Sebastian Aho D case).
  3. Standalone `POST /admin/players/duplicates/merge` deletes the drop
     rows and repoints any roster entries + contract stamps to the
     survivor.
  4. NHL sync `build_diff` surfaces a `duplicates` bucket when a
     candidate matches an existing stale row by (name+birth_date)
     under a different nhl_id.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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
        "_id": uid, "email": f"n66_{str(uid)[:6]}@iter.test",
        "name": "N66 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id: str):
    from routes import admin_players as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


# ── find_db_duplicates unit tests ─────────────────────────────────

def test_find_duplicates_fantilli_name_only_when_one_row_missing_dob():
    from services.nhl_sync import find_db_duplicates
    rows = [
        {"_id": "a", "name": "Adam Fantilli", "team": "CBJ",
         "nhl_id": "8484166", "birth_date": "2004-10-12", "league": None},
        {"_id": "b", "name": "adam fantilli",  # different casing
         "team": "Michigan", "nhl_id": "-4023003",
         "birth_date": None, "league": None},
    ]
    clusters = find_db_duplicates(rows)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["match_reason"] == "name+birth_date"  # DOB inferred from sibling
    assert c["birth_date"] == "2004-10-12"
    # Keep candidate should be the real-nhl_id row (CBJ).
    assert c["rows"][0]["nhl_id"] == "8484166"
    assert c["rows"][1]["nhl_id"] == "-4023003"


def test_find_duplicates_splits_on_conflicting_dobs():
    from services.nhl_sync import find_db_duplicates
    rows = [
        # Two real Sebastian Ahos with different DOBs.
        {"_id": "a", "name": "Sebastian Aho", "team": "CAR",
         "nhl_id": "8478427", "birth_date": "1997-07-26"},
        {"_id": "b", "name": "Sebastian Aho", "team": "NYI",
         "nhl_id": "8480222", "birth_date": "1996-02-17"},
        # A third row without DOB — should be dropped from both
        # sub-clusters (ambiguous).
        {"_id": "c", "name": "Sebastian Aho", "team": "?",
         "nhl_id": "-99", "birth_date": None},
        # A fourth row duplicating one of the real ones.
        {"_id": "d", "name": "Sebastian Aho", "team": "CAR",
         "nhl_id": "-4023111", "birth_date": "1997-07-26"},
    ]
    clusters = find_db_duplicates(rows)
    # We expect one cluster (the 1997 one has 2 rows), the 1996 has 1
    # so it doesn't surface.
    assert len(clusters) == 1
    c = clusters[0]
    assert c["birth_date"] == "1997-07-26"
    assert len(c["rows"]) == 2
    ids = [r["id"] for r in c["rows"]]
    assert "a" in ids and "d" in ids and "c" not in ids


def test_find_duplicates_singleton_returns_empty():
    from services.nhl_sync import find_db_duplicates
    rows = [
        {"_id": "a", "name": "Solo Guy", "nhl_id": "8484100",
         "birth_date": "2000-01-01"},
    ]
    assert find_db_duplicates(rows) == []


# ── build_diff duplicate bucket during sync ───────────────────────

def test_build_diff_flags_fantilli_style_stale_row_as_duplicate():
    from services.nhl_sync import build_diff
    existing = [
        {"_id": "michigan", "nhl_id": "-4023003", "name": "Adam Fantilli",
         "team": "Michigan", "birth_date": "2004-10-12"},
    ]
    candidates = [
        {"nhl_id": "8484166", "name": "Adam Fantilli", "team": "CBJ",
         "birth_date": "2004-10-12", "age": 21, "position": "C",
         "is_prospect": False},
    ]
    diff = build_diff(existing, candidates)
    # The stale row should NOT show under `removed` — it's a duplicate.
    assert diff["counts"]["removed"] == 0
    assert diff["counts"]["new_players"] == 1
    assert diff["counts"]["duplicates"] == 1
    dup = diff["duplicates"][0]
    assert dup["stale_nhl_id"] == "-4023003"
    assert dup["fresh_nhl_id"] == "8484166"
    assert dup["stale_team"] == "Michigan"
    assert dup["fresh_team"] == "CBJ"


# ── Standalone merge endpoint ────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_endpoint_drops_duplicate_and_repoints_roster():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    # Seed: 2 rows for one player, one on a fake roster.
    keep_r = await db.players.insert_one({
        "name": "Test Merge Guy", "nhl_id": "8481000",
        "team": "TOR", "birth_date": "2003-05-05",
    })
    drop_r = await db.players.insert_one({
        "name": "Test Merge Guy", "nhl_id": "-999999",
        "team": "Marlies", "birth_date": None,
    })
    team_id = ObjectId()
    await db.teams.insert_one({
        "_id": team_id, "name": "TestMergeTeam",
        "roster": [str(drop_r.inserted_id)],
    })
    await db.contracts.insert_one({
        "player_id": str(drop_r.inserted_id),
        "aav": 950_000,
    })

    res = await m.admin_merge_duplicates(
        m.DedupeMergeRequest(merges=[{
            "keep_id": str(keep_r.inserted_id),
            "drop_ids": [str(drop_r.inserted_id)],
        }]),
        _StubReq(),
    )
    assert res["ok"] is True
    assert res["merged"] == 1

    # Stale row deleted; survivor kept.
    assert await db.players.count_documents({"_id": drop_r.inserted_id}) == 0
    assert await db.players.count_documents({"_id": keep_r.inserted_id}) == 1

    # Roster was repointed to the survivor.
    team = await db.teams.find_one({"_id": team_id})
    assert str(keep_r.inserted_id) in team["roster"]
    assert str(drop_r.inserted_id) not in team["roster"]

    # Contract was repointed too.
    ct = await db.contracts.find_one({"aav": 950_000})
    assert ct["player_id"] == str(keep_r.inserted_id)

    # Cleanup
    await db.players.delete_one({"_id": keep_r.inserted_id})
    await db.teams.delete_one({"_id": team_id})
    await db.contracts.delete_many({"player_id": str(keep_r.inserted_id)})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


@pytest.mark.asyncio
async def test_duplicates_scan_endpoint_returns_clusters():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    # Seed 2 clusters worth of data with unique names so we don't
    # collide with the live DB.
    a = await db.players.insert_one({
        "name": "N66 Scan Alpha", "nhl_id": "8485001",
        "team": "TOR", "birth_date": "2005-01-01",
    })
    b = await db.players.insert_one({
        "name": "N66 Scan Alpha", "nhl_id": "-4029001",
        "team": "OHL Team", "birth_date": None,
    })
    c = await db.players.insert_one({
        "name": "N66 Scan Beta", "nhl_id": "8485002",
        "team": "MTL", "birth_date": "2004-04-04",
    })
    d = await db.players.insert_one({
        "name": "N66 Scan Beta", "nhl_id": "-4029002",
        "team": "QMJHL Team", "birth_date": "2004-04-04",
    })

    res = await m.admin_scan_duplicates(_StubReq(), limit=500)
    # We only care that our two seeded clusters appear — real DB may
    # have many more.
    ours = [c for c in res["clusters"]
            if c["name"] in ("N66 Scan Alpha", "N66 Scan Beta")]
    assert len(ours) == 2
    for cl in ours:
        assert len(cl["rows"]) == 2
        # Survivor priority should elect the real-nhl_id row (8485xxx)
        assert cl["rows"][0]["nhl_id"].startswith("8485")

    # Cleanup
    for pid in (a.inserted_id, b.inserted_id, c.inserted_id, d.inserted_id):
        await db.players.delete_one({"_id": pid})
    await db.users.delete_one({"_id": ObjectId(admin_id)})

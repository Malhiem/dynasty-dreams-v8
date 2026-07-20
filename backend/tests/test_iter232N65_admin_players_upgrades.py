"""Iter 232N.65 — Admin Player DB upgrades pytest suite.

Covers the four new capabilities layered on top of 232N.64:

  1. NHL API dry-run sync produces a valid diff structure + a
     `sync_token` that survives a follow-up selective apply.
  2. NHL API sync/apply respects the selected `apply_*` picks and
     rejects an unknown / cross-admin sync_token.
  3. CSV preview validates rows (missing name+team, invalid position,
     out-of-range age) without touching Mongo; commit path only writes
     the selected valid rows and skips invalid ones.
  4. Bulk actions: `mark_prospect` toggles is_prospect, `unmark_prospect`
     reverts it, and `delete` skips players on active rosters (409-safe).
"""
from __future__ import annotations

import io
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException, UploadFile

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
        "_id": uid, "email": f"n65_{str(uid)[:6]}@iter.test",
        "name": "N65 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id: str):
    from routes import admin_players as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


# ── Fake NHL API candidates so tests don't hit the network ──────────
_FAKE_CANDIDATES = [
    {"nhl_id": "n65_new_1", "name": "New Rookie",  "position": "C",
     "team": "TOR", "league": "NHL", "age": 21, "is_prospect": False},
    {"nhl_id": "n65_age_1", "name": "Aging Star",  "position": "LW",
     "team": "TOR", "league": "NHL", "age": 30, "is_prospect": False},
    {"nhl_id": "n65_team_1","name": "Traded Guy",   "position": "D",
     "team": "MTL", "league": "NHL", "age": 27, "is_prospect": False},
    # note: n65_removed_1 exists in DB but is intentionally absent here
    # so it lands in the "removed" bucket.
]


@pytest.mark.asyncio
async def test_nhl_sync_dry_run_produces_diff_token():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    # Seed existing rows so diff has content in every bucket.
    await db.players.insert_many([
        {"nhl_id": "n65_age_1",  "name": "Aging Star", "team": "TOR", "age": 29, "position": "LW"},
        {"nhl_id": "n65_team_1", "name": "Traded Guy", "team": "OTT", "age": 27, "position": "D"},
        {"nhl_id": "n65_removed_1", "name": "Old NHL Guy", "team": "TOR"},
    ])
    ids_to_clean = [ObjectId()]  # placeholder

    with patch("routes.admin_players.nhl_sync.fetch_all_players",
               new=AsyncMock(return_value=(_FAKE_CANDIDATES, []))):
        req = _StubReq()
        payload = m.SyncRequest(dry_run=True)
        res = await m.admin_sync_from_nhl(payload, req)

    assert res["ok"] is True
    assert res["dry_run"] is True
    token = res["sync_token"]
    assert token and isinstance(token, str)
    counts = res["diff"]["counts"]
    assert counts["new_players"] == 1
    assert counts["age_changes"] == 1
    assert counts["team_changes"] == 1
    assert counts["removed"] >= 1

    # Nothing should be written by dry-run.
    assert await db.players.count_documents({"nhl_id": "n65_new_1"}) == 0

    # Cleanup
    await db.players.delete_many({"nhl_id": {"$regex": "^n65_"}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})
    m._sync_previews.pop(token, None)


@pytest.mark.asyncio
async def test_nhl_sync_apply_selective_and_rejects_unknown_token():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    await db.players.insert_many([
        {"nhl_id": "n65_age_1", "name": "Aging Star", "team": "TOR", "age": 29, "position": "LW"},
        {"nhl_id": "n65_team_1","name": "Traded Guy",  "team": "OTT", "age": 27, "position": "D"},
    ])

    with patch("routes.admin_players.nhl_sync.fetch_all_players",
               new=AsyncMock(return_value=(_FAKE_CANDIDATES, []))):
        req = _StubReq()
        dry = await m.admin_sync_from_nhl(m.SyncRequest(dry_run=True), req)

    # Apply only the age change; leave team alone.
    apply_res = await m.admin_sync_apply(
        m.SyncApplyRequest(
            sync_token=dry["sync_token"],
            apply_new=["n65_new_1"],
            apply_age=["n65_age_1"],
            apply_team=[],
            apply_position=[],
            apply_prospect=[],
            apply_removed=[],
        ),
        _StubReq(),
    )

    assert apply_res["ok"] is True
    assert apply_res["inserted"] == 1
    assert apply_res["updated_age"] == 1
    assert apply_res["updated_team"] == 0

    updated_age = await db.players.find_one({"nhl_id": "n65_age_1"})
    assert updated_age["age"] == 30
    kept_team = await db.players.find_one({"nhl_id": "n65_team_1"})
    assert kept_team["team"] == "OTT"       # unchanged (not applied)
    new_row = await db.players.find_one({"nhl_id": "n65_new_1"})
    assert new_row is not None and new_row["name"] == "New Rookie"

    # Token is single-use — second apply should 410.
    with pytest.raises(HTTPException) as exc:
        await m.admin_sync_apply(
            m.SyncApplyRequest(sync_token=dry["sync_token"]),
            _StubReq(),
        )
    assert exc.value.status_code == 410

    # Cleanup
    await db.players.delete_many({"nhl_id": {"$regex": "^n65_"}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


@pytest.mark.asyncio
async def test_csv_preview_validates_rows_and_commit_writes_only_selected():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    csv_body = (
        "name,team,position,age,is_prospect,nhl_id\n"
        "Valid One,TOR,C,25,false,csv_valid_1\n"
        "Bad Position,MTL,ZZ,26,false,csv_bad_pos\n"
        ",,,,,\n"                            # empty row → invalid (no id/name+team)
        "Age Range,BOS,D,99,false,csv_bad_age\n"
        "Valid Two,VAN,D,22,true,csv_valid_2\n"
    )

    # Build a minimal UploadFile stand-in.
    upload = UploadFile(filename="preview.csv", file=io.BytesIO(csv_body.encode()))
    req = _StubReq()
    preview = await m.admin_csv_preview(req, file=upload)

    assert preview["ok"] is True
    assert preview["totals"]["valid"] == 2
    assert preview["totals"]["errors"] == 3
    # First row is valid.
    row0 = preview["rows"][0]
    assert row0["valid"] is True and row0["errors"] == []
    # Bad position row flags the position error.
    row1 = preview["rows"][1]
    assert row1["valid"] is False
    assert any("position" in e for e in row1["errors"])

    # Nothing written yet.
    assert await db.players.count_documents({"nhl_id": {"$regex": "^csv_"}}) == 0

    # Commit only the first valid row.
    commit = await m.admin_csv_commit(
        m.CsvCommitRequest(preview_token=preview["preview_token"], apply_indices=[0]),
        _StubReq(),
    )
    assert commit["upserted"] == 1
    assert await db.players.count_documents({"nhl_id": "csv_valid_1"}) == 1
    assert await db.players.count_documents({"nhl_id": "csv_valid_2"}) == 0  # not applied

    # Second commit with same token must fail (410).
    with pytest.raises(HTTPException) as exc:
        await m.admin_csv_commit(
            m.CsvCommitRequest(preview_token=preview["preview_token"]),
            _StubReq(),
        )
    assert exc.value.status_code == 410

    # Cleanup
    await db.players.delete_many({"nhl_id": {"$regex": "^csv_"}})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


@pytest.mark.asyncio
async def test_bulk_mark_and_delete_respects_roster_safety():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    ids = []
    for i in range(3):
        r = await db.players.insert_one({
            "nhl_id": f"n65_bulk_{i}",
            "name": f"Bulk Guy {i}", "team": "TOR", "position": "C",
            "is_prospect": False,
        })
        ids.append(str(r.inserted_id))

    # Put the middle player on a fake roster so delete must skip him.
    await db.teams.insert_one({"_id": ObjectId(), "name": "T", "roster": [ids[1]]})

    # 1) mark_prospect on all three
    res = await m.admin_bulk_action(
        m.BulkActionRequest(action="mark_prospect", player_ids=ids),
        _StubReq(),
    )
    assert res["affected"] == 3
    marked = await db.players.count_documents({
        "_id": {"$in": [ObjectId(x) for x in ids]},
        "is_prospect": True,
    })
    assert marked == 3

    # 2) unmark_prospect on same set
    res = await m.admin_bulk_action(
        m.BulkActionRequest(action="unmark_prospect", player_ids=ids),
        _StubReq(),
    )
    assert res["affected"] == 3
    still_marked = await db.players.count_documents({
        "_id": {"$in": [ObjectId(x) for x in ids]},
        "is_prospect": True,
    })
    assert still_marked == 0

    # 3) delete — roster-locked player is skipped
    res = await m.admin_bulk_action(
        m.BulkActionRequest(action="delete", player_ids=ids),
        _StubReq(),
    )
    assert res["affected"] == 2
    assert res["skipped_on_roster"] == 1
    remaining = await db.players.count_documents({
        "_id": {"$in": [ObjectId(x) for x in ids]},
    })
    assert remaining == 1   # only the rostered one survived

    # Cleanup
    await db.players.delete_many({"nhl_id": {"$regex": "^n65_bulk_"}})
    await db.teams.delete_many({"name": "T"})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Unit tests for the diff builder (no Mongo, no network) ──────────

def test_build_diff_categorizes_new_age_team_removed():
    from services.nhl_sync import build_diff

    existing = [
        {"_id": "a1", "nhl_id": "x1", "name": "A", "team": "TOR", "age": 25, "position": "C"},
        {"_id": "a2", "nhl_id": "x2", "name": "B", "team": "MTL", "age": 27, "position": "D"},
        {"_id": "a3", "nhl_id": "x3", "name": "C (gone)", "team": "BOS"},
        {"_id": "a4", "nhl_id": "admin_kept", "name": "Admin add", "team": "AHL"},
    ]
    candidates = [
        {"nhl_id": "x1", "name": "A",  "team": "TOR", "age": 26, "position": "C", "is_prospect": False},
        {"nhl_id": "x2", "name": "B",  "team": "OTT", "age": 27, "position": "D", "is_prospect": False},
        {"nhl_id": "x4", "name": "D (new)", "team": "VAN", "age": 20, "position": "LW", "is_prospect": True},
    ]

    diff = build_diff(existing, candidates)
    assert diff["counts"]["new_players"] == 1
    assert diff["counts"]["age_changes"] == 1
    assert diff["counts"]["team_changes"] == 1
    assert diff["counts"]["removed"] == 1  # only x3, not admin_kept
    assert diff["new_players"][0]["nhl_id"] == "x4"
    assert diff["age_changes"][0]["old_age"] == 25 and diff["age_changes"][0]["new_age"] == 26
    assert diff["team_changes"][0]["new_team"] == "OTT"
    removed_ids = [r["nhl_id"] for r in diff["removed"]]
    assert "x3" in removed_ids and "admin_kept" not in removed_ids

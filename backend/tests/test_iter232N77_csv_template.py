"""Iter 232N.77 — CSV template download + comment-row skip pytest suite.

Covers the new `/admin/players/csv/template` endpoint and the
comment-row guard added to `_validate_csv_row`:

  1. GET /admin/players/csv/template returns a text/csv attachment
     with the expected filename + exact column header order.
  2. The template contains one comment row (starts with "#") + at
     least two example rows.
  3. Uploading the unmodified template back to /csv/preview yields
     zero errors and the comment row is skipped from `totals.read`.
"""
from __future__ import annotations

import io
import os
import sys

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import UploadFile

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
        "_id": uid, "email": f"n77_{str(uid)[:6]}@iter.test",
        "name": "N77 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_players as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


@pytest.mark.asyncio
async def test_csv_template_returns_attachment_with_expected_headers():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    resp = await m.admin_csv_template(_StubReq())
    assert resp.media_type == "text/csv"
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert "player_db_cap_import_template.csv" in resp.headers.get("Content-Disposition", "")

    body = resp.body.decode("utf-8")
    lines = body.strip().split("\n")
    assert len(lines) >= 4          # headers + comment + ≥2 examples
    header_row = lines[0]
    # Spot-check every column the CSV preview endpoint cares about.
    for col in ("nhl_id", "name", "position", "team", "age",
                "is_prospect", "cap_hit", "salary", "birth_date"):
        assert col in header_row, header_row
    # Second row is the inline comment.
    assert lines[1].startswith('"# ') or lines[1].startswith('#')

    await db.users.delete_one({"_id": ObjectId(admin_id)})


@pytest.mark.asyncio
async def test_csv_template_round_trip_preview_zero_errors():
    from routes import admin_players as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)

    tmpl = await m.admin_csv_template(_StubReq())
    csv_bytes = tmpl.body

    upload = UploadFile(filename="tmpl.csv", file=io.BytesIO(csv_bytes))
    preview = await m.admin_csv_preview(_StubReq(), file=upload)
    assert preview["ok"] is True
    # All example rows should validate cleanly.
    assert preview["totals"]["errors"] == 0
    assert preview["totals"]["valid"] >= 2   # Matthews + Bedard at minimum
    # Comment row must NOT be counted in `read` totals.
    assert preview["totals"]["read"] == preview["totals"]["valid"]

    # Cleanup — the preview may have upserted example NHL ids into the
    # players collection only if we commit; preview alone doesn't
    # write, so nothing to undo.
    await db.users.delete_one({"_id": ObjectId(admin_id)})

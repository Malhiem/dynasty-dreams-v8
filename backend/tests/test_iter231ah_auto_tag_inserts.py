"""Iter 231ah — Auto-tagging verification.

Verifies the conftest monkey-patches inject `_test_seed: True` into
every Mongo insert against the 9 polluted collections — both
PyMongo (sync) and Motor (async) paths — without the test file
having to set the field manually.

This is the proof that legacy tests don't need to be migrated
one-by-one — the conftest handles it transparently.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sync_db():
    return MongoClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


def _async_db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


def test_sync_insert_auto_tags():
    """PyMongo `Collection.insert_one` on a polluted collection must
    auto-inject `_test_seed: True` — no manual tagging needed."""
    db = _sync_db()
    suffix = uuid.uuid4().hex[:8]
    doc = {
        "name": f"iter231ah-sync-{suffix}",
        "nhl_id": int(uuid.uuid4().int % 1_000_000) + 700_000_000,
    }
    r = db.players.insert_one(doc)
    try:
        stored = db.players.find_one({"_id": r.inserted_id})
        assert stored is not None
        # Conftest auto-tagger added the marker.
        assert stored.get("_test_seed") is True, \
            f"Auto-tagger didn't fire — stored doc: {stored}"
    finally:
        db.players.delete_one({"_id": r.inserted_id})


def test_sync_insert_many_auto_tags():
    db = _sync_db()
    suffix = uuid.uuid4().hex[:8]
    docs = [
        {"name": f"iter231ah-many-1-{suffix}", "nhl_id": int(uuid.uuid4().int % 1_000_000) + 700_000_000},
        {"name": f"iter231ah-many-2-{suffix}", "nhl_id": int(uuid.uuid4().int % 1_000_000) + 700_000_000},
    ]
    r = db.players.insert_many(docs)
    try:
        for ins_id in r.inserted_ids:
            stored = db.players.find_one({"_id": ins_id})
            assert stored.get("_test_seed") is True
    finally:
        db.players.delete_many({"_id": {"$in": list(r.inserted_ids)}})


@pytest.mark.asyncio
async def test_async_insert_auto_tags():
    """Motor `AsyncIOMotorCollection.insert_one` on a polluted
    collection must auto-inject `_test_seed: True`."""
    db = _async_db()
    suffix = uuid.uuid4().hex[:8]
    doc = {
        "name": f"iter231ah-async-{suffix}",
        "nhl_id": int(uuid.uuid4().int % 1_000_000) + 700_000_000,
    }
    r = await db.players.insert_one(doc)
    try:
        stored = await db.players.find_one({"_id": r.inserted_id})
        assert stored is not None
        assert stored.get("_test_seed") is True
    finally:
        await db.players.delete_one({"_id": r.inserted_id})


@pytest.mark.asyncio
async def test_async_insert_respects_explicit_false():
    """If a test explicitly sets `_test_seed: False`, the auto-tagger
    must NOT clobber the value (some integration tests rely on
    untagged docs to validate the conftest sweep itself)."""
    db = _async_db()
    suffix = uuid.uuid4().hex[:8]
    doc = {
        "name": f"iter231ah-explicit-{suffix}",
        "_test_seed": False,
        "nhl_id": int(uuid.uuid4().int % 1_000_000) + 700_000_000,
    }
    r = await db.players.insert_one(doc)
    try:
        stored = await db.players.find_one({"_id": r.inserted_id})
        # Explicit False must survive.
        assert stored.get("_test_seed") is False
    finally:
        await db.players.delete_one({"_id": r.inserted_id})


def test_sync_insert_skips_non_polluted_collections():
    """Auto-tagger only targets the 9 polluted collections. Other
    collections (e.g. `chat_messages`, `audit_log`) must NOT get the
    marker — keeps the DB schema clean for production-shape data."""
    db = _sync_db()
    suffix = uuid.uuid4().hex[:8]
    # `chat_messages` is NOT in the auto-seed list.
    r = db.chat_messages.insert_one({"text": f"iter231ah-chat-{suffix}"})
    try:
        stored = db.chat_messages.find_one({"_id": r.inserted_id})
        # Auto-tagger must NOT have added the marker on this collection.
        assert "_test_seed" not in stored
    finally:
        db.chat_messages.delete_one({"_id": r.inserted_id})

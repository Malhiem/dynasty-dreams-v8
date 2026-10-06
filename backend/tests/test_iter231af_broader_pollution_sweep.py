"""Iter 231af — Regression guards for the broader pollution sweep.

User reported AGAIN (after iter231ac wiped ForceP/FutureP/WaiverTarget):
"Still seeing test pollution players, please ensure that the player pool
is accurate without test pollution." — screenshot showed:

    NHL Veteran Forward d8ef9452
    Minor Eligible Forward d8ef9452
    NHL Veteran Forward 6f3c616a
    ...

Source: `test_iter228n_draft_edit_upcoming_filters.py` (HTTP-mode test)
seeded these names via `db.players.insert_one` AND created leagues via
HTTP `POST /api/leagues` named `i228n-{hex}` — both untagged + with
zero teardown. Over time leaked **78 polluting players + 284 ephemeral
leagues + 6,135 `@example.com` test users + 2,677 orphan leagues +
4,974 teams + 1,400 drafts**.

This guard:
  1. Live preview DB has ZERO of the named pollution patterns.
  2. Live preview DB has ZERO `@example.com` user accounts.
  3. The global conftest sweeps the new patterns (regex + email
     cascade) and the iter228n test file tags every seeded doc with
     `_test_seed: True`.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _src(p: str) -> str:
    return Path(p).read_text()


# ─── Source guards ─────────────────────────────────────────────────


def test_iter228n_tags_test_seed():
    """Every `db.players.insert_one` in test_iter228n must include the
    `_test_seed: True` marker so the conftest auto-sweep finds it."""
    src = _src("/app/backend/tests/test_iter228n_draft_edit_upcoming_filters.py")
    assert '"_test_seed": True' in src
    # Each of the 3 insert_one calls in that file must tag the row.
    assert src.count('"_test_seed": True') >= 3


def test_conftest_covers_new_patterns():
    src = _src("/app/backend/tests/conftest.py")
    # Player regex now catches the iter228n names.
    assert "NHL Veteran Forward" in src
    assert "Minor Eligible Forward" in src
    assert "Repeat Pick" in src
    # League regex now catches `i228n-` (3-digit year-marker).
    assert r"\d{3}" in src
    # Email domain sweep on @example.com.
    assert "@example" in src
    # Cascade: leagues owned by test users get nuked too.
    assert "commissioner_id" in src
    assert "owned_leagues" in src


# ─── Functional guards (live DB) ───────────────────────────────────


@pytest.mark.asyncio
async def test_no_named_pollution_in_player_pool():
    """Live preview DB must contain ZERO of the iter228n-pattern
    polluting players. If this fails, run the iter231af cleanup
    script (in PRD changelog)."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]
    pattern = re.compile(
        r"^(NHL Veteran Forward|Minor Eligible Forward|Repeat Pick|"
        r"ForceP|FutureP|WaiverTarget)",
        re.IGNORECASE,
    )
    count = await db.players.count_documents({"name": {"$regex": pattern}})
    assert count == 0, (
        f"Found {count} polluting players in the live pool. "
        "The conftest sweep should be catching these — verify autouse fixture is running."
    )


@pytest.mark.asyncio
async def test_no_example_com_users_in_live_db():
    """Live preview DB must contain ZERO @example.com user accounts.
    @example.com is the RFC-reserved test domain."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]
    count = await db.users.count_documents({
        "email": {"$regex": "@example\\.com$", "$options": "i"}
    })
    assert count == 0, (
        f"Found {count} @example.com test users in the live users collection. "
        "The conftest sweep should be deleting these."
    )


@pytest.mark.asyncio
async def test_no_ephemeral_iter228n_leagues():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]
    count = await db.leagues.count_documents({"name": {"$regex": "^i228n-", "$options": "i"}})
    assert count == 0

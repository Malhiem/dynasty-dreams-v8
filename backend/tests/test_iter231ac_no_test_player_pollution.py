"""Iter 231ac — Regression guard: test-pollution players (ForceP-*,
FutureP-*, WaiverTarget-*) must NEVER leak into the live `players`
collection on the shared preview DB.

User reported 7+ test-seeded players showing in the live waiver
wire / player pool screens. Root cause: `test_iter228_waiver_engine.py`
called `_seed_player(...)` with random-suffixed test names but never
torn them down — so every CI run left 3 more `ForceP-*` / `FutureP-*`
/ `WaiverTarget-*` rows behind. Over ~22 runs this accumulated to 65
polluting players, 89 polluted team rosters, 86 orphan waiver_claims
(including 24 affected TFHL teams).

This guard:
  1. Asserts `_seed_player` tags every seeded player with
     `iter228_test_seed: True`.
  2. Asserts the autouse cleanup fixture exists in the test file.
  3. Asserts the current DB has zero matching pollution (i.e. the
     iter231ac repair script ran successfully).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _src() -> str:
    return Path("/app/backend/tests/test_iter228_waiver_engine.py").read_text()


def test_seed_player_tags_test_seed():
    """Every player inserted by `_seed_player` must carry the
    `iter228_test_seed: True` marker so the autouse cleanup sweep
    (and emergency repair scripts) can find them."""
    src = _src()
    assert "iter228_test_seed" in src
    assert '"iter228_test_seed": True' in src


def test_autouse_cleanup_fixture_present():
    """The test module must declare an autouse cleanup fixture that
    sweeps polluted artefacts before AND after each test."""
    src = _src()
    assert "autouse=True" in src
    assert "_cleanup_iter228_pollution" in src
    # Sweep must hit BOTH players (with marker + legacy regex) AND the
    # ephemeral iter228-* leagues so we don't keep accreting empty
    # league shells across runs.
    assert "ForceP|FutureP|WaiverTarget" in src
    assert '"name": {"$regex": "^iter228-"}' in src


@pytest.mark.asyncio
async def test_no_polluting_players_in_live_db():
    """Live preview DB must currently contain ZERO ForceP/FutureP/
    WaiverTarget rows. Failures here mean a recent run polluted again
    AND the cleanup didn't catch it — re-run the iter231ac repair."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]
    pattern = re.compile(r"^(ForceP|FutureP|WaiverTarget)", re.IGNORECASE)
    count = await db.players.count_documents({"name": {"$regex": pattern}})
    assert count == 0, (
        f"Found {count} polluting test players in the live players collection. "
        "Run the iter231ac cleanup script and check the autouse fixture is firing."
    )


@pytest.mark.asyncio
async def test_no_iter228_ephemeral_leagues_in_live_db():
    """Live preview DB must contain ZERO `iter228-*` ephemeral leagues."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]
    count = await db.leagues.count_documents({"name": {"$regex": "^iter228-"}})
    assert count == 0, (
        f"Found {count} iter228-* test leagues in the live leagues collection. "
        "These should be deleted after each test run by the autouse fixture."
    )

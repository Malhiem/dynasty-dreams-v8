"""Iter 192 — 32-team entry-draft league bootstrap.

Confirms the cloning script created the league with the right shape:
  * 32 teams, no rosters, no owners
  * 1440 picks (45 rounds × 32 teams)
  * Reverse-serpentine draft order: odd rounds 1..32, even rounds 32..1
  * Cloned settings (scoring/format/sport) from Ice Kings Head-to-Head
"""
from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def db():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    yield cli[os.environ["DB_NAME"]]
    cli.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_new_league_exists():
    async def go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        league = await db.leagues.find_one({"name": "Ice Kings 32 Entry Draft"})
        cli.close()
        return league
    league = _run(go())
    assert league is not None, "Iter 192 cloning script must have run"
    assert league["max_teams"] == 32
    assert league["current_teams"] == 32
    assert league.get("scoring_format") == "head_to_head"
    assert league.get("format") == "redraft"
    assert league.get("status") == "active"
    # Iter 191 review settings applied.
    assert league.get("draft_trade_review_minutes") == 30
    assert league.get("draft_trade_post_delay_action") == "auto_execute"


def test_new_league_has_32_teams_no_rosters():
    async def go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        league = await db.leagues.find_one({"name": "Ice Kings 32 Entry Draft"})
        teams = await db.teams.find({"league_id": str(league["_id"])}).to_list(None)
        cli.close()
        return teams
    teams = _run(go())
    assert len(teams) == 32
    # No rosters, no owners — entry draft is pending.
    for t in teams:
        assert t.get("roster_players") in ([], None)
        assert t.get("owner_id") in (None, "")
        assert t.get("is_pending") is True


def test_draft_has_1440_picks_reverse_serpentine():
    async def go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        league = await db.leagues.find_one({"name": "Ice Kings 32 Entry Draft"})
        lid = str(league["_id"])
        total = await db.draft_picks.count_documents({"league_id": lid})
        # Sample odd/even rounds + a deep round to prove the snake.
        rows = {}
        for r in (1, 2, 3, 44, 45):
            picks = await db.draft_picks.find({"league_id": lid, "round": r}).sort("pick_number", 1).to_list(None)
            rows[r] = [p["original_team_abbr"] for p in picks]
        cli.close()
        return total, rows
    total, rows = _run(go())
    assert total == 45 * 32 == 1440
    # Round 1: 1..32 order
    assert len(rows[1]) == 32
    # Round 2 must be the reverse of round 1
    assert rows[2] == list(reversed(rows[1]))
    # Round 3 mirrors round 1
    assert rows[3] == rows[1]
    # Round 44 (even) reverses; Round 45 (odd) does NOT.
    assert rows[44] == list(reversed(rows[1]))
    assert rows[45] == rows[1]

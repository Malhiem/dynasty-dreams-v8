"""Iter 231x — Production-safety fixes from the TFHL Inaugural Draft incident.

Three issues found + fixed:

  1. **Test isolation bug**: `services/draft_pick_timer_worker.run_once`
     scanned ALL active drafts in the DB. The iter231q tests called
     `run_once(db)` against the real DB while production drafts had
     expired clocks → the test's "Iter231q Player N" pollution rows
     (points=100, higher than real NHLers) ranked first in the
     eligible-players sort and got picked into 84 real production
     pick slots. Test cleanup then deleted the test players, leaving
     orphan player_id references. **Fix**: `run_once` now accepts a
     `draft_ids_filter` kwarg. Production loop passes None (unchanged
     behaviour); tests MUST pass a scoped list to prevent pollution.

  2. **Duplicate-pick race**: `perform_one_auto_pick` `$push`'d to
     `draft.picks` without a compare-and-set guard. Two concurrent
     invocations (timer worker + manual UI auto-pick, or two timer
     ticks) both read `current_pick=N`, both pushed `overall=N` →
     duplicate picks. TFHL had duplicates at #78, #575, #598. **Fix**:
     update query now matches on `{current_pick == N, status ==
     "active"}` so the second writer's match_count is 0 and a 409 is
     raised cleanly.

  3. **Draft Board column mismatch**: drafts created when teams had
     `name=None` stored `team_abbrs: ["TBD", "TBD2", ...]`. Frontend
     now derives column abbrs from current `logo_abbr` (e.g. "OS5",
     "OS9", "OS1") so the pick lookup `pick.team === teamAbbr`
     leaves cells blank. **Fix**: pick lookup now ALSO matches on
     `pick.team_id === boardEntry.id` (canonical id, stamped on every
     pick by the auto-pick worker since iter 170j).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.draft_pick_timer_worker import run_once


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


# ─── Source-grep guards ────────────────────────────────────────────


def test_run_once_accepts_draft_ids_filter():
    from pathlib import Path
    src = Path("/app/backend/services/draft_pick_timer_worker.py").read_text()
    assert "draft_ids_filter: list[str] | None = None" in src
    assert 'query["_id"] = {"$in":' in src
    # Comment must explain the test-isolation purpose so future agents
    # understand WHY the filter exists (to prevent re-introducing the
    # iter231q pollution).
    assert "Iter 231x test-isolation hook" in src


def test_perform_one_auto_pick_has_concurrency_guard():
    """`perform_one_auto_pick` must condition the picks `$push` on the
    current_pick value matching N (compare-and-set). Prevents the
    duplicate-pick race seen in TFHL."""
    from pathlib import Path
    src = Path("/app/backend/routes/draft_helpers.py").read_text()
    assert '"current_pick": current_pick, "status": "active"' in src
    # Must check matched_count == 0 and raise 409.
    assert "result.matched_count == 0" in src
    assert "status_code=409" in src


def test_draft_board_matches_picks_by_team_id_fallback():
    """The DraftBoard frontend pick-lookup must fall back to matching
    `pick.team_id === boardEntry.id` when the team_abbr drifts (e.g.
    legacy TBD/TBD2/.. picks vs current OS5/OS9/.. column headers)."""
    from pathlib import Path
    src = Path("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx").read_text()
    # The new lookup explicitly checks team_id BEFORE falling back to abbr.
    assert "p.team_id" in src
    assert "boardEntry.id" in src
    # And the comment explains the iter229b rename context so future
    # devs know why this guard exists.
    assert "Iter 231x" in src


# ─── Functional tests ──────────────────────────────────────────────


async def _seed_minimal_draft(db, started_at):
    """Seeds a fresh league + 3 teams + 5 players + 1 active draft.
    Returns (draft_id, league_id, owners, team_ids, player_ids)."""
    suffix = uuid.uuid4().hex[:8]
    uids = []
    for i in range(3):
        uid = ObjectId()
        await db.users.insert_one({"_id": uid, "email": f"i231x_o{i}_{suffix}@example.com",
                                    "username": f"i231x_{i}_{suffix}"[:24], "name": f"i231x {i}"})
        uids.append(str(uid))

    league_id = ObjectId()
    await db.leagues.insert_one({"_id": league_id, "name": f"i231x League {suffix}",
                                  "commissioner_id": uids[0], "status": "active"})

    team_ids, abbrs = [], []
    team_map = {}
    for i, uid in enumerate(uids):
        t_id = ObjectId()
        await db.teams.insert_one({"_id": t_id, "name": f"i231x Team {i+1}",
                                    "league_id": str(league_id), "owner_id": uid,
                                    "roster": [], "draft_queue": []})
        abbr = f"T{i+1}"
        team_ids.append(str(t_id))
        abbrs.append(abbr)
        team_map[abbr] = {"id": str(t_id), "name": f"i231x Team {i+1}"}

    pids = []
    for i in range(5):
        p_id = ObjectId()
        await db.players.insert_one({"_id": p_id, "nhl_id": f"i231x-{p_id}",
                                      "name": f"i231x Player {i+1}", "position": "C",
                                      "team": "TOR", "team_name": "Toronto",
                                      "points": 100 - i, "games_played": 82, "player_type": "skater"})
        pids.append(str(p_id))

    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": str(league_id), "name": "i231x Draft",
        "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "pick_time_seconds": 60, "current_pick": 1,
        "team_abbrs": abbrs, "team_map": team_map, "picks": [], "chat_messages": [],
        "current_pick_started_at": started_at, "started_at": started_at,
    })
    return str(draft_id), str(league_id), uids, team_ids, pids


async def _cleanup_seed(db, league_id, uids, pids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}})


def _wire_deps(db):
    from routes import draft_helpers
    draft_helpers._deps["db"] = db


@pytest.mark.asyncio
async def test_run_once_with_filter_scopes_to_seeded_draft_only():
    """Critical regression guard: with `draft_ids_filter=[seeded_id]`,
    run_once MUST NOT touch any other active draft in the DB. This is
    the contract that prevents iter231q-style pollution."""
    db = _db()
    _wire_deps(db)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id, league_id, uids, team_ids, pids = await _seed_minimal_draft(db, past)
    try:
        # Snapshot picks count of every OTHER active draft in the DB.
        other_drafts = []
        async for d in db.drafts.find({"status": "active", "_id": {"$ne": ObjectId(draft_id)}}):
            other_drafts.append((str(d["_id"]), len(d.get("picks") or [])))

        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["checked"] == 1, f"Expected to scan only the seeded draft; checked={counts['checked']}"
        assert counts["picked"] == 1

        # Verify NO other draft got touched.
        for other_id, prior_count in other_drafts:
            d = await db.drafts.find_one({"_id": ObjectId(other_id)}, {"picks": 1})
            assert len(d.get("picks") or []) == prior_count, (
                f"Other draft {other_id} was modified! "
                f"Was {prior_count} picks, now {len(d.get('picks') or [])}"
            )
    finally:
        await _cleanup_seed(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_concurrent_auto_picks_do_not_produce_duplicates():
    """Two concurrent perform_one_auto_pick invocations on the same
    draft must NOT both push a pick at `overall=N`. The second one
    should 409. This is the regression guard for the TFHL duplicate
    picks at #78, #575, #598."""
    from routes.draft_helpers import perform_one_auto_pick
    from fastapi import HTTPException

    db = _db()
    _wire_deps(db)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id, league_id, uids, team_ids, pids = await _seed_minimal_draft(db, past)
    try:
        # Fire 5 concurrent auto-picks against current_pick=1.
        # Only ONE should succeed; the other 4 should raise 409.
        results = await asyncio.gather(
            *[perform_one_auto_pick(draft_id, source="timeout") for _ in range(5)],
            return_exceptions=True,
        )
        successes = [r for r in results if not isinstance(r, Exception)]
        conflicts = [r for r in results if isinstance(r, HTTPException) and r.status_code == 409]
        assert len(successes) == 1, f"Expected exactly 1 success; got {len(successes)}"
        assert len(conflicts) == 4, f"Expected 4 conflicts; got {len(conflicts)}: {results}"

        # Verify no duplicates in the picks array.
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        overalls = [p.get("overall") for p in refreshed.get("picks") or []]
        assert overalls == [1], f"Expected exactly one pick at overall=1; got {overalls}"
    finally:
        await _cleanup_seed(db, league_id, uids, pids)

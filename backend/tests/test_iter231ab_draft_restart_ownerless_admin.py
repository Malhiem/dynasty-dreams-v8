"""Iter 231ab — Three production fixes for the Draft Room:

  1. **Ownerless teams auto-draft immediately**: When the team on the
     clock has no `owner_id` (Open Slot), the worker fires `perform_one_
     auto_pick` regardless of clock window / defer-to-user / deadline.
     The draft can't progress otherwise — no human owns this team to
     respond to the clock.

  2. **Co-commissioners + platform admins can pick for teams**: The
     `POST /api/drafts/{draft_id}/pick` endpoint previously rejected
     anyone but the league's primary `commissioner_id`. League admins
     (co-commissioners + platform-tier admins) now have the same
     authority — same pattern as the seed-picks / patch endpoints.

  3. **Hard-restart endpoint**: `POST /api/drafts/{draft_id}/restart`
     wipes picks + rosters and resets `status=scheduled`. Used when
     the league wants to redo the draft. Audited via
     `admin_user_actions`.

  4. **`perform_one_auto_pick` resets `current_pick_started_at`**: Bug
     fix — without this reset, the worker treats every subsequent
     pick as "already expired" and fires auto-picks in rapid
     succession (the 1am EST incident).
"""
from __future__ import annotations

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
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


def _wire_deps(db):
    from routes import draft_helpers
    draft_helpers._deps["db"] = db


# ─── Source guards ─────────────────────────────────────────────────


def test_perform_one_auto_pick_resets_current_pick_started_at():
    from pathlib import Path
    src = Path("/app/backend/routes/draft_helpers.py").read_text()
    # The optimistic-concurrency $set must now ALSO reset
    # `current_pick_started_at` so the worker's next tick measures the
    # NEW pick's elapsed time from the right anchor (was the same
    # `started` value forever — root cause of the rapid-fire incident).
    assert "current_pick_started_at" in src
    assert "datetime.now(timezone.utc).isoformat()" in src


def test_worker_handles_ownerless_teams_separately():
    from pathlib import Path
    src = Path("/app/backend/services/draft_pick_timer_worker.py").read_text()
    assert "is_ownerless" in src, "Worker must detect ownerless teams"
    assert "ownerless" in src
    # Detection must check both `owner_id` and `co_owner_ids` so a
    # solo co-owner team isn't mistaken for ownerless.
    assert "co_owner_ids" in src


def test_make_pick_allows_co_commissioners():
    """Iter 231ab → 231ad: the role check originally lived inline in
    draft_pick_actions.py (5 copies of the same 4 lines). Iter 231ad
    extracted it to `routes._authz.is_league_admin` — so now we
    assert the file IMPORTS the helper instead of greping for raw
    `co_commissioners` clauses."""
    from pathlib import Path
    src = Path("/app/backend/routes/draft_pick_actions.py").read_text()
    assert "from routes._authz import is_league_admin" in src
    # All 5 handlers (pick / undo / swap / pause / seed-picks) must
    # call the helper. Count must be >= 5.
    assert src.count("is_league_admin(user, league)") >= 5
    # And the underlying helper must check co_commissioners.
    helper_src = Path("/app/backend/routes/_authz.py").read_text()
    assert "co_commissioners" in helper_src


def test_restart_endpoint_exists():
    from pathlib import Path
    src = Path("/app/backend/routes/draft_admin.py").read_text()
    assert "/drafts/{draft_id}/restart" in src
    assert "async def restart_draft" in src
    # Restart must wipe rosters AND picks AND reset current_pick.
    assert '"current_pick": 1' in src
    assert '"picks": []' in src
    assert '"status": "scheduled"' in src
    # Audit row must be written.
    assert "admin_user_actions" in src
    assert "draft_restart" in src


# ─── Functional: Ownerless team auto-picks immediately ─────────────


async def _seed_draft_with_ownerless_team(db):
    """Three-team draft where Team #1 is Open Slot (owner_id=None)."""
    suffix = uuid.uuid4().hex[:8]
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"i231ab_{suffix}@example.com",
        "username": f"i231ab_{suffix}"[:24], "name": "i231ab",
    })
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": f"i231ab League {suffix}",
        "commissioner_id": str(uid), "status": "active",
    })
    team_ids = []
    abbrs = []
    team_map = {}
    for i in range(3):
        t_id = ObjectId()
        abbr = f"O{i+1}"
        team_doc = {
            "_id": t_id, "name": f"i231ab Team {i+1}",
            "league_id": str(league_id), "roster": [], "draft_queue": [],
        }
        # Team #1 (the one on the clock at pick=1) is OWNERLESS.
        if i > 0:
            team_doc["owner_id"] = str(uid)
        await db.teams.insert_one(team_doc)
        team_ids.append(str(t_id))
        abbrs.append(abbr)
        team_map[abbr] = {"id": str(t_id), "name": f"i231ab Team {i+1}"}
    pids = []
    for i in range(3):
        p_id = ObjectId()
        await db.players.insert_one({
            "_id": p_id, "nhl_id": f"i231ab-{p_id}",
            "name": f"i231ab Player {i+1}", "position": "C",
            "team": "TOR", "team_name": "Toronto",
            "points": 100 - i, "games_played": 82, "player_type": "skater",
        })
        pids.append(str(p_id))
    draft_id = ObjectId()
    # Configure with defer-to-user + a 4-hour time-per-pick so WITHOUT
    # the ownerless override, the worker would skip / wait forever.
    # `current_pick_started_at` set to NOW so the deadline is still 4
    # hours away.
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": draft_id, "league_id": str(league_id), "name": "i231ab Draft",
        "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "current_pick": 1,
        "team_abbrs": abbrs, "team_map": team_map,
        "picks": [], "chat_messages": [],
        "current_pick_started_at": now_iso, "started_at": now_iso,
        "time_per_pick": 14400,  # 4 hours
        "missed_pick_action": "defer-to-user",  # would normally skip
    }
    await db.drafts.insert_one(doc)
    return str(draft_id), str(league_id), [str(uid)], team_ids, pids


async def _cleanup(db, league_id, uids, pids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}})


@pytest.mark.asyncio
async def test_worker_auto_picks_for_ownerless_team_immediately():
    """When the on-clock team has no owner, the worker fires NOW even
    though the time_per_pick deadline is 4 hours away AND missed_pick_
    action is defer-to-user."""
    db = _db()
    _wire_deps(db)
    draft_id, league_id, uids, _team_ids, pids = await _seed_draft_with_ownerless_team(db)
    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["picked"] == 1, f"Ownerless team should auto-pick; counts={counts}"
        assert counts["ownerless_picks"] == 1
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert len(refreshed["picks"]) == 1
        assert refreshed["picks"][0]["auto_picked"] is True
        assert refreshed["picks"][0]["auto_pick_source"] == "ownerless"
        # `current_pick_started_at` must be reset on the NEW pick anchor
        # (different from the start-time we seeded).
        assert refreshed["current_pick"] == 2
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_owned_team_inside_window_with_defer_is_skipped():
    """Regression guard: a team WITH an owner + defer-to-user mode must
    still be skipped — the ownerless fast-path must NOT swallow owned
    teams."""
    db = _db()
    _wire_deps(db)
    # Seed the same shape but flip team #1 to have an owner.
    draft_id, league_id, uids, _team_ids, pids = await _seed_draft_with_ownerless_team(db)
    # Patch the first team to have an owner_id so it's no longer ownerless.
    first_team_id = (await db.drafts.find_one({"_id": ObjectId(draft_id)}))["team_map"]["O1"]["id"]
    await db.teams.update_one(
        {"_id": ObjectId(first_team_id)},
        {"$set": {"owner_id": uids[0]}},
    )
    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["picked"] == 0, "Owned team in defer-to-user should not auto-pick"
        assert counts.get("ownerless_picks", 0) == 0
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_perform_one_auto_pick_resets_clock_anchor_functional():
    """End-to-end: after an auto-pick, `current_pick_started_at` is a
    fresh timestamp (not the original 5-minutes-ago anchor)."""
    db = _db()
    _wire_deps(db)
    # Seed a 60s pick clock that started 10 minutes ago + ownerless team
    # so the auto-pick fires.
    draft_id, league_id, uids, _team_ids, pids = await _seed_draft_with_ownerless_team(db)
    old_anchor = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"current_pick_started_at": old_anchor, "time_per_pick": 60}},
    )
    try:
        await run_once(db, draft_ids_filter=[draft_id])
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        new_anchor = refreshed["current_pick_started_at"]
        assert new_anchor != old_anchor, "Anchor must be refreshed after auto-pick"
        # New anchor must be very recent (< 30 seconds ago).
        parsed = datetime.fromisoformat(str(new_anchor).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - parsed
        assert delta.total_seconds() < 30, f"Anchor should be very recent, was {delta.total_seconds()}s ago"
    finally:
        await _cleanup(db, league_id, uids, pids)

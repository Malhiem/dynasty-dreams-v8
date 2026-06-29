"""Iter 231ad / 231ae — Combined tests for:

  • Shared `routes._authz.is_league_admin` helper.
  • Rate-limited ownerless auto-picks (max 1 per draft per worker tick).
  • Archive-before-restart: `draft_restart_log` collection populated.
  • Admin-managed team toggle (`POST /leagues/{lid}/teams/{tid}/admin-managed`).
  • Pending-invites count exposed on `GET /leagues/{lid}/pending-team-invites`.
  • Worker skips ownerless fast-path when `team.admin_managed == True`.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


# ─── Source guards ─────────────────────────────────────────────────


def test_is_league_admin_helper_exists():
    src = Path("/app/backend/routes/_authz.py").read_text()
    assert "def is_league_admin" in src
    # Must check ALL three role paths.
    assert "commissioner_id" in src
    assert "co_commissioners" in src
    assert 'role") == "admin"' in src


def test_draft_pick_actions_uses_shared_helper():
    """The 5 endpoint handlers in draft_pick_actions.py must import
    + use `is_league_admin` instead of inlining the 4-line check."""
    src = Path("/app/backend/routes/draft_pick_actions.py").read_text()
    assert "from routes._authz import is_league_admin" in src
    # No lingering inline `co_commissioners` clauses in this file.
    # (We allow `co_commissioners` to appear inside the helper module,
    # but not in route handler bodies — they must defer to the helper.)
    assert "co_commissioners or [])\n        or user.get(\"role\") == \"admin\"" not in src


def test_draft_admin_uses_shared_helper():
    src = Path("/app/backend/routes/draft_admin.py").read_text()
    assert "from routes._authz import is_league_admin" in src
    # `restart_draft` must use the helper, not inline the 4-line check.
    assert "if not is_league_admin(user, league)" in src


def test_restart_archives_picks():
    """The restart_draft endpoint must write a `draft_restart_log`
    document with the full picks payload BEFORE wiping the draft."""
    src = Path("/app/backend/routes/draft_admin.py").read_text()
    assert "draft_restart_log" in src
    assert '"picks": picks' in src


def test_worker_rate_limit_and_admin_managed():
    """Worker comments must call out the rate-limit + admin-managed
    behaviour so future agents don't regress them."""
    src = Path("/app/backend/services/draft_pick_timer_worker.py").read_text()
    assert "admin_managed" in src
    # `continue` short-circuit on admin_managed must NOT trigger an
    # auto-pick — verify the skip path increments only `skipped`.
    assert 'counts["skipped"] += 1' in src


def test_admin_managed_endpoint_exists():
    src = Path("/app/backend/routes/team_invites.py").read_text()
    assert "/admin-managed" in src
    assert "AdminManagedToggleRequest" in src
    assert "team_admin_managed_toggle" in src  # audit row action label.


def test_pending_invites_count_exposed():
    src = Path("/app/backend/routes/league_invites.py").read_text()
    assert "pending_invite_count" in src
    assert '"admin_managed"' in src


def test_teamstab_renders_chip_and_checkbox():
    src = Path("/app/frontend/src/lovable/components/admin/TeamsTab.tsx").read_text()
    assert "teams-tab-pending-chip-" in src
    assert "teams-tab-admin-managed-toggle-" in src
    assert "teams-tab-admin-managed-badge-" in src
    assert "League admin runs this team" in src
    # The toggle handler must POST to the correct endpoint.
    assert "/admin-managed" in src


def test_conftest_global_sweep_exists():
    src = Path("/app/backend/tests/conftest.py").read_text()
    assert "def _global_pollution_sweep" in src
    assert "autouse=True" in src
    assert "_test_seed" in src
    assert "pytest_configure" in src


# ─── Functional: shared helper ─────────────────────────────────────


def test_is_league_admin_truth_table():
    from routes._authz import is_league_admin

    user_a = {"_id": "uA"}
    user_b = {"_id": "uB"}
    user_admin = {"_id": "uAdmin", "role": "admin"}
    league = {
        "commissioner_id": "uA",
        "co_commissioners": ["uB"],
    }
    assert is_league_admin(user_a, league) is True
    assert is_league_admin(user_b, league) is True  # co-commish
    assert is_league_admin(user_admin, league) is True  # platform admin
    assert is_league_admin({"_id": "uC"}, league) is False
    assert is_league_admin(None, league) is False
    assert is_league_admin(user_a, None) is False
    # No `co_commissioners` field at all → don't crash.
    assert is_league_admin(user_a, {"commissioner_id": "uA"}) is True
    assert is_league_admin(user_b, {"commissioner_id": "uA"}) is False


# ─── Functional: admin_managed + worker fast-path skip ─────────────


async def _seed_ownerless_draft(db, *, admin_managed=False):
    """Seed a draft where Team #1 is ownerless. Optionally tag with
    admin_managed=True so the worker should NOT fire."""
    suffix = uuid.uuid4().hex[:8]
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"i231ae_{suffix}@example.com",
        "username": f"i231ae_{suffix}"[:24], "name": "i231ae",
        "_test_seed": True,
    })
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": f"i231ae League {suffix}",
        "commissioner_id": str(uid), "status": "active",
        "_test_seed": True,
    })
    team_ids = []
    abbrs = []
    team_map = {}
    for i in range(2):
        t_id = ObjectId()
        abbr = f"A{i+1}"
        team_doc = {
            "_id": t_id, "name": f"i231ae Team {i+1}",
            "league_id": str(league_id), "roster": [], "draft_queue": [],
            "_test_seed": True,
        }
        if i == 0 and admin_managed:
            team_doc["admin_managed"] = True
        elif i > 0:
            team_doc["owner_id"] = str(uid)
        await db.teams.insert_one(team_doc)
        team_ids.append(str(t_id))
        abbrs.append(abbr)
        team_map[abbr] = {"id": str(t_id), "name": f"i231ae Team {i+1}"}
    pids = []
    for i in range(2):
        p_id = ObjectId()
        await db.players.insert_one({
            "_id": p_id, "nhl_id": f"i231ae-{p_id}",
            "name": f"i231ae Player {i+1}", "position": "C",
            "team": "TOR", "team_name": "Toronto",
            "points": 100 - i, "games_played": 82, "player_type": "skater",
            "_test_seed": True,
        })
        pids.append(str(p_id))
    draft_id = ObjectId()
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": str(league_id), "name": "i231ae Draft",
        "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "current_pick": 1,
        "team_abbrs": abbrs, "team_map": team_map,
        "picks": [], "chat_messages": [],
        "current_pick_started_at": now_iso, "started_at": now_iso,
        "time_per_pick": 60,
        "missed_pick_action": "auto-best",
        "_test_seed": True,
    })
    return str(draft_id), str(league_id), [str(uid)], team_ids, pids


@pytest.mark.asyncio
async def test_worker_skips_admin_managed_ownerless_team():
    """Owner-removal continuity: when commissioner has flagged the
    team `admin_managed`, the worker must NOT auto-pick BPA. The
    admin will pick manually."""
    db = _db()
    from routes import draft_helpers
    draft_helpers._deps["db"] = db
    from services.draft_pick_timer_worker import run_once

    draft_id, league_id, uids, _tids, pids = await _seed_ownerless_draft(db, admin_managed=True)
    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["picked"] == 0
        # Skipped should be incremented (the admin_managed branch).
        assert counts["skipped"] >= 1
        # No ownerless_picks counter bump.
        assert counts.get("ownerless_picks", 0) == 0
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
    finally:
        await db.drafts.delete_many({"_id": ObjectId(draft_id)})
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})
        await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
        await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}})


@pytest.mark.asyncio
async def test_worker_still_autopicks_when_admin_managed_false():
    """Regression: when team has NO `admin_managed` flag, the original
    ownerless fast-path must still fire."""
    db = _db()
    from routes import draft_helpers
    draft_helpers._deps["db"] = db
    from services.draft_pick_timer_worker import run_once

    draft_id, league_id, uids, _tids, pids = await _seed_ownerless_draft(db, admin_managed=False)
    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["picked"] == 1
        assert counts.get("ownerless_picks", 0) == 1
    finally:
        await db.drafts.delete_many({"_id": ObjectId(draft_id)})
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})
        await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
        await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}})


# ─── Functional: restart archives picks ───────────────────────────


@pytest.mark.asyncio
async def test_restart_writes_to_draft_restart_log():
    """Restart endpoint must write a draft_restart_log row with full
    picks payload before wiping."""
    db = _db()
    from routes import draft_admin
    draft_admin._deps["db"] = db
    # Stub get_current_user + broadcast (the deps map is shared globally).
    suffix = uuid.uuid4().hex[:6]
    uid = ObjectId()
    user_doc = {
        "_id": uid, "email": f"i231ad_{suffix}@example.com",
        "username": f"i231ad_{suffix}"[:24], "name": "i231ad",
        "role": "admin", "_test_seed": True,
    }
    await db.users.insert_one(user_doc)

    async def _stub_user(req): return user_doc
    async def _noop_broadcast(*a, **k): return None
    draft_admin._deps["get_current_user"] = _stub_user
    draft_admin._deps["broadcast_to_room"] = _noop_broadcast

    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": f"i231ad League {suffix}",
        "commissioner_id": str(uid), "_test_seed": True,
    })
    team_id = ObjectId()
    await db.teams.insert_one({
        "_id": team_id, "name": "i231ad Team",
        "league_id": str(league_id), "roster": ["pX"], "_test_seed": True,
    })
    draft_id = ObjectId()
    seed_picks = [
        {"overall": 1, "round": 1, "team": "T1", "team_id": str(team_id),
         "player_id": "pX", "player_name": "X", "timestamp": "2026-01-01T00:00:00+00:00"},
    ]
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": str(league_id), "name": "i231ad Draft",
        "status": "active", "current_pick": 2, "picks": seed_picks,
        "team_map": {"T1": {"id": str(team_id), "name": "T"}},
        "team_abbrs": ["T1"], "snake_draft": True, "total_rounds": 1,
        "_test_seed": True,
    })
    try:
        # Direct call to the endpoint coroutine (no HTTP layer needed).
        out = await draft_admin.restart_draft(str(draft_id), request=None)
        assert out["picks_wiped"] == 1
        log_row = await db.draft_restart_log.find_one({"draft_id": str(draft_id)})
        assert log_row is not None
        assert log_row["picks_wiped"] == 1
        assert len(log_row["picks"]) == 1
        assert log_row["picks"][0]["overall"] == 1
        assert log_row["restarted_by"] == str(uid)
    finally:
        await db.drafts.delete_many({"_id": ObjectId(draft_id)})
        await db.draft_restart_log.delete_many({"draft_id": str(draft_id)})
        await db.teams.delete_many({"_id": ObjectId(team_id)})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})
        await db.users.delete_one({"_id": uid})
        await db.admin_user_actions.delete_many({"metadata.draft_id": str(draft_id)})

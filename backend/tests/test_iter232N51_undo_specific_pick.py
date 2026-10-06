"""Iter 232N.51 — Targeted single-pick undo endpoint tests.

Covers `POST /api/drafts/{draft_id}/picks/{pick_number}/undo`:

  1. Non-admin rejected 403.
  2. Nonexistent pick_number rejected 404.
  3. Undoing the most-recent pick removes the player from the drafting
     team's roster, resets `current_pick`, refreshes clock, inserts
     audit row, posts a System chat message.
  4. Middle-pick undo without `allow_cascade` returns 409.
  5. Middle-pick undo WITH `allow_cascade=true` unrolls every later
     pick as well.
  6. `draft_picks` collection rows are cleared for the undone slots.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


class _BroadcastLog:
    """Fake broadcast recorder for tests."""
    def __init__(self):
        self.calls = []

    async def __call__(self, room, event, payload):
        self.calls.append({"room": room, "event": event, "payload": payload})


def _wire_deps(db, caller):
    from routes import draft_pick_actions as m
    m._deps.update({
        "db": db,
        "broadcast_to_room": _BroadcastLog(),
    })

    async def _fake_get_user(_request):
        return caller
    m._deps["get_current_user"] = _fake_get_user


async def _seed_user(db, prefix, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n51.test",
        "name": f"iter232n51 {prefix}",
        "role": role,
    })
    return str(uid)


async def _seed_league_teams_draft(db, made_picks: int = 1):
    """Seed a 2-team draft. `made_picks` controls how many picks are
    already in `draft.picks`."""
    uids = [await _seed_user(db, f"u{i}") for i in range(2)]
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "Iter232N51 league",
        "commissioner_id": uids[0], "status": "active",
    })
    team_ids = []
    for i, uid in enumerate(uids):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "name": f"Team {i}", "league_id": str(league_id),
            "owner_id": uid, "co_owner_ids": [], "roster": [],
        })
        team_ids.append(str(tid))

    # Pre-existing player docs so `pull` sees a real removal
    player_ids = []
    for i in range(2):
        pid = ObjectId()
        await db.players.insert_one({
            "_id": pid, "name": f"Player {i}", "position": "C",
            "player_type": "prospect", "points": 100 - i,
            "nhl_id": f"iter232n51-{pid}",
        })
        player_ids.append(str(pid))

    draft_id = ObjectId()
    picks = []
    for i in range(made_picks):
        picks.append({
            "overall": i + 1,
            "round": 1,
            "pick_in_round": i + 1,
            "team": ["AAA", "BBB"][i % 2],
            "team_id": team_ids[i % 2],
            "player_id": player_ids[i % 2],
            "player": {"name": f"Player {i}", "position": "C"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Roster contains what was picked
        await db.teams.update_one(
            {"_id": ObjectId(team_ids[i % 2])},
            {"$addToSet": {"roster": player_ids[i % 2]}},
        )
        # Seed matching draft_picks row
        await db.draft_picks.insert_one({
            "draft_id": str(draft_id),
            "league_id": str(league_id),
            "pick_number": i + 1,
            "round": 1,
            "team_abbr": ["AAA", "BBB"][i % 2],
            "team_id": team_ids[i % 2],
            "player_id": player_ids[i % 2],
            "player_name": f"Player {i}",
        })

    await db.drafts.insert_one({
        "_id": draft_id, "league_id": str(league_id),
        "name": "Iter232N51 draft", "status": "active",
        "draft_started": True, "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60,
        "current_pick": made_picks + 1,
        "team_abbrs": ["AAA", "BBB"],
        "team_map": {
            "AAA": {"id": team_ids[0], "name": "Team 0"},
            "BBB": {"id": team_ids[1], "name": "Team 1"},
        },
        "picks": picks, "chat_messages": [],
        "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
    })
    return str(league_id), uids, team_ids, player_ids, str(draft_id)


async def _cleanup(db, league_id, uids, player_ids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.draft_picks.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in player_ids]}})
    await db.draft_undo_audit.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_undo_specific_pick_rejects_non_admin():
    from routes.draft_pick_actions import undo_specific_pick, UndoSinglePickRequest
    from fastapi import HTTPException

    db = _db()
    league_id, uids, team_ids, pids, draft_id = await _seed_league_teams_draft(db, made_picks=1)
    outsider = await _seed_user(db, "outsider", role="user")
    _wire_deps(db, {"_id": outsider, "role": "user"})

    try:
        with pytest.raises(HTTPException) as exc:
            await undo_specific_pick(
                draft_id, 1, UndoSinglePickRequest(), None,
            )
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, league_id, uids + [outsider], pids)


@pytest.mark.asyncio
async def test_undo_specific_pick_returns_404_for_missing_pick():
    from routes.draft_pick_actions import undo_specific_pick, UndoSinglePickRequest
    from fastapi import HTTPException

    db = _db()
    league_id, uids, _, pids, draft_id = await _seed_league_teams_draft(db, made_picks=1)
    _wire_deps(db, {"_id": uids[0], "role": "user"})

    try:
        with pytest.raises(HTTPException) as exc:
            await undo_specific_pick(
                draft_id, 99, UndoSinglePickRequest(), None,
            )
        assert exc.value.status_code == 404
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_undo_last_pick_full_teardown():
    """Undoing the most recent pick — the primary happy path. Verifies
    roster, current_pick, draft_picks collection, audit row, and system
    chat message all get updated atomically."""
    from routes.draft_pick_actions import undo_specific_pick, UndoSinglePickRequest

    db = _db()
    league_id, uids, team_ids, pids, draft_id = await _seed_league_teams_draft(db, made_picks=1)
    _wire_deps(db, {"_id": uids[0], "role": "user", "name": "TheCommish"})

    try:
        result = await undo_specific_pick(
            draft_id, 1,
            UndoSinglePickRequest(reason="misclick"),
            None,
        )
        assert result["ok"] is True
        assert result["removed_count"] == 1
        assert result["cascade"] is False
        assert result["current_pick"] == 1
        assert result["clock_reset_at"]

        # 1) Roster cleared
        t = await db.teams.find_one({"_id": ObjectId(team_ids[0])})
        assert pids[0] not in (t.get("roster") or [])
        # 2) draft.picks cleared, current_pick rewound
        d = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert d["picks"] == []
        assert d["current_pick"] == 1
        # 3) draft_picks collection slot cleared (row still exists but
        #    player fields blanked so the Draft Board renders empty)
        dp = await db.draft_picks.find_one({"draft_id": draft_id, "pick_number": 1})
        assert dp is not None
        assert dp["player_id"] is None
        assert dp["player_name"] is None
        # 4) Audit row persisted
        audit = await db.draft_undo_audit.find_one({
            "draft_id": draft_id, "pick_number": 1,
        })
        assert audit is not None
        assert audit["reason"] == "misclick"
        assert audit["commissioner_name"] == "TheCommish"
        assert audit["removed_count"] == 1
        # 5) System chat message pushed
        chat = d.get("chat_messages") or []
        assert len(chat) == 1
        assert "TheCommish undid pick #1" in chat[0]["text"]
        assert 'reason: "misclick"' in chat[0]["text"]
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_undo_middle_pick_without_cascade_returns_409():
    from routes.draft_pick_actions import undo_specific_pick, UndoSinglePickRequest
    from fastapi import HTTPException

    db = _db()
    league_id, uids, _, pids, draft_id = await _seed_league_teams_draft(db, made_picks=2)
    _wire_deps(db, {"_id": uids[0], "role": "user"})

    try:
        with pytest.raises(HTTPException) as exc:
            # Pick #1 has pick #2 after it — cascade required.
            await undo_specific_pick(
                draft_id, 1, UndoSinglePickRequest(), None,
            )
        assert exc.value.status_code == 409
        assert "allow_cascade" in exc.value.detail
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_undo_middle_pick_with_cascade_unrolls_all_later_picks():
    from routes.draft_pick_actions import undo_specific_pick, UndoSinglePickRequest

    db = _db()
    league_id, uids, team_ids, pids, draft_id = await _seed_league_teams_draft(db, made_picks=2)
    _wire_deps(db, {"_id": uids[0], "role": "user", "name": "TheCommish"})

    try:
        result = await undo_specific_pick(
            draft_id, 1,
            UndoSinglePickRequest(allow_cascade=True),
            None,
        )
        assert result["ok"] is True
        assert result["removed_count"] == 2  # picks #1 AND #2
        assert result["cascade"] is True
        assert result["current_pick"] == 1

        d = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert d["picks"] == []
        # Both rosters emptied
        t0 = await db.teams.find_one({"_id": ObjectId(team_ids[0])})
        t1 = await db.teams.find_one({"_id": ObjectId(team_ids[1])})
        assert pids[0] not in (t0.get("roster") or [])
        assert pids[1] not in (t1.get("roster") or [])
        # System message reflects the cascade count
        chat = d.get("chat_messages") or []
        assert len(chat) == 1
        assert "1 pick(s) after it" in chat[0]["text"]
    finally:
        await _cleanup(db, league_id, uids, pids)

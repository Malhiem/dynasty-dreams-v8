"""Iter 232N.47 — Commissioner ping-offline-owner endpoint tests.

Covers `POST /api/leagues/{league_id}/drafts/{draft_id}/ping-owner`:

  • Non-commissioner rejected 403.
  • Non-owner target rejected 400 (can't ping arbitrary users).
  • Successful ping fires in_app + email + socket; audit row inserted.
  • 429 rate limit: second ping within 5 minutes rejected.
  • Archived / non-active-scheduled drafts rejected.
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


class _CallLog:
    """Captures every notify/email/broadcast call so tests can assert
    which channels fired without hitting SendGrid or Socket.IO for real."""
    def __init__(self):
        self.notify_calls = []
        self.email_calls = []
        self.broadcast_calls = []

    async def notify(self, user_id, notif_type, title, message,
                     league_id=None, link=None, reason=None):
        doc = {
            "_id": str(ObjectId()),
            "user_id": user_id, "type": notif_type, "title": title,
            "message": message, "league_id": league_id, "link": link,
            "reason": reason,
        }
        self.notify_calls.append(doc)
        return doc

    def email(self, to_email, subject, html):
        self.email_calls.append({"to": to_email, "subject": subject, "html": html})
        return {"status": "sent", "to": to_email}

    async def broadcast(self, room, event, payload):
        self.broadcast_calls.append({"room": room, "event": event, "payload": payload})


def _wire_deps(db, log: _CallLog):
    """Reset draft_ops deps + rate-limit cache between tests."""
    from routes import draft_ops as draft_ops_module
    draft_ops_module._deps.update({
        "db": db,
        "create_notification": log.notify,
        "send_sendgrid_email": log.email,
        "broadcast_to_room": log.broadcast,
    })

    async def _fake_get_user(_request):
        return draft_ops_module._deps.get("_test_user")
    draft_ops_module._deps["get_current_user"] = _fake_get_user
    # Clear rate-limit dict so parallel tests don't stomp each other.
    draft_ops_module._PING_LAST_FIRED.clear()


async def _seed_user(db, prefix, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n47.test",
        "name": f"iter232n47 {prefix}",
        "username": f"{prefix}_{str(uid)[:6]}",
        "role": role,
    })
    return str(uid)


async def _seed_league_teams_draft(db, n_teams=2):
    uids = [await _seed_user(db, f"u{i}") for i in range(n_teams)]
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "Iter232N47 league",
        "commissioner_id": uids[0], "status": "active",
    })
    team_ids = []
    for i, uid in enumerate(uids):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "name": f"Team {i}",
            "league_id": str(league_id), "owner_id": uid,
            "co_owner_ids": [],
        })
        team_ids.append(str(tid))
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": str(league_id),
        "name": "Iter232N47 draft", "status": "active",
        "total_rounds": 2, "time_per_pick": 60, "current_pick": 1,
        "team_abbrs": ["AAA", "BBB"], "snake_draft": True,
        "team_map": {
            "AAA": {"id": team_ids[0], "name": "Team 0", "owner_id": uids[0]},
            "BBB": {"id": team_ids[1], "name": "Team 1", "owner_id": uids[1]},
        },
        "picks": [],
    })
    return str(league_id), uids, team_ids, str(draft_id)


async def _cleanup(db, league_id, uids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    await db.commissioner_pings.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_ping_rejects_non_admin():
    from routes.draft_ops import ping_offline_owner, PingOwnerRequest
    from routes import draft_ops as draft_ops_module
    from fastapi import HTTPException

    db = _db()
    log = _CallLog()
    _wire_deps(db, log)
    league_id, uids, _, draft_id = await _seed_league_teams_draft(db, 2)
    outsider = await _seed_user(db, "outsider")
    draft_ops_module._deps["_test_user"] = {"_id": outsider, "role": "user"}

    try:
        with pytest.raises(HTTPException) as exc:
            await ping_offline_owner(
                league_id, draft_id,
                PingOwnerRequest(user_id=uids[1]),
                None,
            )
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, league_id, uids + [outsider])


@pytest.mark.asyncio
async def test_ping_rejects_non_owner_target():
    from routes.draft_ops import ping_offline_owner, PingOwnerRequest
    from routes import draft_ops as draft_ops_module
    from fastapi import HTTPException

    db = _db()
    log = _CallLog()
    _wire_deps(db, log)
    league_id, uids, _, draft_id = await _seed_league_teams_draft(db, 2)
    bystander = await _seed_user(db, "bystander")
    draft_ops_module._deps["_test_user"] = {"_id": uids[0], "role": "user"}

    try:
        with pytest.raises(HTTPException) as exc:
            await ping_offline_owner(
                league_id, draft_id,
                PingOwnerRequest(user_id=bystander),
                None,
            )
        assert exc.value.status_code == 400
        assert "not an owner" in exc.value.detail.lower()
    finally:
        await _cleanup(db, league_id, uids + [bystander])


@pytest.mark.asyncio
async def test_ping_fires_notification_email_and_socket():
    from routes.draft_ops import ping_offline_owner, PingOwnerRequest
    from routes import draft_ops as draft_ops_module

    db = _db()
    log = _CallLog()
    _wire_deps(db, log)
    league_id, uids, _, draft_id = await _seed_league_teams_draft(db, 2)
    draft_ops_module._deps["_test_user"] = {
        "_id": uids[0], "role": "user", "name": "Commish",
    }

    try:
        result = await ping_offline_owner(
            league_id, draft_id,
            PingOwnerRequest(user_id=uids[1], message="Pick already!"),
            None,
        )
        assert result["ok"] is True
        assert "in_app" in result["channels_fired"]
        assert "email" in result["channels_fired"]
        assert "socket" in result["channels_fired"]
        assert result["cooldown_seconds"] == 300
        assert result["next_ping_at"]  # ISO timestamp when unlocked

        # Notification content includes commissioner name + custom
        # message.
        assert len(log.notify_calls) == 1
        n = log.notify_calls[0]
        assert n["user_id"] == uids[1]
        assert n["type"] == "draft_commissioner_ping"
        assert "Commish" in n["message"]
        assert "Pick already!" in n["message"]
        # Email envelope hits the target's email.
        assert len(log.email_calls) == 1
        assert log.email_calls[0]["to"].endswith("@iter232n47.test")
        # Socket broadcast lands on the user_{id} personal room.
        assert len(log.broadcast_calls) == 1
        b = log.broadcast_calls[0]
        assert b["room"] == f"user_{uids[1]}"
        assert b["event"] == "commissioner_ping"
        assert b["payload"]["draft_id"] == draft_id
        # Audit row persisted.
        audit = await db.commissioner_pings.find_one({
            "league_id": league_id, "draft_id": draft_id,
            "target_user_id": uids[1],
        })
        assert audit is not None
        assert audit["custom_message"] == "Pick already!"
        assert "in_app" in (audit["channels_fired"] or [])
    finally:
        await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_ping_rate_limits_second_call_within_window():
    from routes.draft_ops import ping_offline_owner, PingOwnerRequest
    from routes import draft_ops as draft_ops_module
    from fastapi import HTTPException

    db = _db()
    log = _CallLog()
    _wire_deps(db, log)
    league_id, uids, _, draft_id = await _seed_league_teams_draft(db, 2)
    draft_ops_module._deps["_test_user"] = {"_id": uids[0], "role": "user"}

    try:
        first = await ping_offline_owner(
            league_id, draft_id,
            PingOwnerRequest(user_id=uids[1]),
            None,
        )
        assert first["ok"] is True

        with pytest.raises(HTTPException) as exc:
            await ping_offline_owner(
                league_id, draft_id,
                PingOwnerRequest(user_id=uids[1]),
                None,
            )
        assert exc.value.status_code == 429
        assert "again in" in exc.value.detail
    finally:
        await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_ping_rejects_completed_draft():
    from routes.draft_ops import ping_offline_owner, PingOwnerRequest
    from routes import draft_ops as draft_ops_module
    from fastapi import HTTPException

    db = _db()
    log = _CallLog()
    _wire_deps(db, log)
    league_id, uids, _, draft_id = await _seed_league_teams_draft(db, 2)
    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"status": "completed"}},
    )
    draft_ops_module._deps["_test_user"] = {"_id": uids[0], "role": "user"}

    try:
        with pytest.raises(HTTPException) as exc:
            await ping_offline_owner(
                league_id, draft_id,
                PingOwnerRequest(user_id=uids[1]),
                None,
            )
        assert exc.value.status_code == 400
    finally:
        await _cleanup(db, league_id, uids)

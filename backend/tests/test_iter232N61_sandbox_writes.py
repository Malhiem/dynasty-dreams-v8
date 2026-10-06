"""Iter 232N.61 — Sandbox-mode impersonation + Admin-prefixed commissioner.

Covers:
  1. `create_impersonation_token(mode='sandbox')` produces a token whose
     decoded payload carries `mode=sandbox`.
  2. `impersonate_start` mints a sandbox-mode token with a 12h+ expiry
     and returns `mode=sandbox` in the response.
  3. `impersonate_start` writes `mode=sandbox` into the audit trail.
  4. Sandbox mode allows writes — `get_current_user` no longer returns
     403 for POST requests when the token mode is `sandbox` (only
     `read_only` blocks writes).
  5. Newly created sandbox league sets Test User 1 (with "(Admin) " name
     prefix) as commissioner instead of the platform admin.
  6. Test User 1's team is flagged `is_commissioner_team=true`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


class _StubReq:
    def __init__(self, body: dict | None = None, cookies: dict | None = None,
                 method: str = "GET"):
        self._body = body or {}
        self.cookies = cookies or {}
        self.method = method
        self.headers = {}

    async def json(self):
        return self._body


class _StubResp:
    def __init__(self):
        self.cookies_set: dict = {}

    def set_cookie(self, key, value, **_):
        self.cookies_set[key] = value

    def delete_cookie(self, *a, **_):
        pass


def _fake_hash(pw: str) -> str:
    return f"hashed:{pw}"


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n61admin_{str(uid)[:6]}@iter.test",
        "name": "N61 Admin", "role": "admin",
        "password_hash": _fake_hash("Admin!"),
    })
    return str(uid)


def _wire_admin(admin_id: str):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(admin_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user
    m._deps["hash_password"] = _fake_hash
    return m


@pytest.mark.asyncio
async def test_create_impersonation_token_sandbox_mode_encoded():
    import jwt
    from server import (
        create_impersonation_token, get_jwt_secret, JWT_ALGORITHM,
    )
    tok = create_impersonation_token(
        target_user_id="u1", target_email="u@test",
        impersonator_id="a1", impersonator_email="a@test",
        minutes=12 * 60, mode="sandbox",
    )
    payload = jwt.decode(tok, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    assert payload["mode"] == "sandbox"
    assert payload["type"] == "impersonation"


@pytest.mark.asyncio
async def test_impersonate_start_mints_sandbox_mode_long_expiry():
    import jwt
    from routes import auth as auth_m
    from server import (
        create_impersonation_token, get_jwt_secret, JWT_ALGORITHM,
    )
    db = _db()
    admin = await _seed_admin(db)
    # Create a sandbox test user
    target = await db.users.insert_one({
        "email": "test_sandbox_target@iter.test",
        "name": "Sandbox Target", "role": "user",
        "is_test_account": True, "created_at": datetime.now(timezone.utc),
    })
    tid = str(target.inserted_id)

    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(admin)})

    auth_m._deps.update({
        "db": db,
        "get_current_user": _fake_user,
        "create_impersonation_token": create_impersonation_token,
        "COOKIE_SECURE": False, "COOKIE_SAMESITE": "lax",
    })

    resp = _StubResp()
    try:
        result = await auth_m.impersonate_start(
            _StubReq(body={"target_user_id": tid, "reason": "n61 sandbox test"}),
            resp,
        )
        assert result["ok"] is True
        assert result["mode"] == "sandbox"
        # Decode the token cookie set on the response
        tok = resp.cookies_set.get("access_token")
        assert tok, "access_token cookie should be set"
        payload = jwt.decode(tok, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        assert payload["mode"] == "sandbox"

        # 12h expiry (allow some fuzz)
        from datetime import datetime as _dt, timezone as _tz
        exp_dt = _dt.fromtimestamp(payload["exp"], tz=_tz.utc)
        remaining = (exp_dt - _dt.now(_tz.utc)).total_seconds()
        assert remaining > 11 * 3600, f"Expected ~12h expiry, got {remaining}s"

        # Audit entry
        audit = await db.impersonation_audit.find_one({"target_user_id": tid})
        assert audit is not None
        assert audit["mode"] == "sandbox"
    finally:
        await db.users.delete_many({
            "_id": {"$in": [ObjectId(admin), ObjectId(tid)]}
        })
        await db.impersonation_audit.delete_many({"target_user_id": tid})


@pytest.mark.asyncio
async def test_sandbox_league_sets_test_user_1_as_admin_commissioner():
    """Test User 1 should be the league commissioner AND have '(Admin)'
    prefix in their display name."""
    from routes.admin_test_sandbox import (
        create_test_league, delete_test_league, CreateTestLeagueRequest,
    )
    db = _db()
    admin = await _seed_admin(db)
    _wire_admin(admin)
    r = None
    try:
        r = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_redraft_12", num_teams=6),
            _StubReq(),
        )
        # First team's owner should have (Admin) prefix.
        first_team = r["teams"][0]
        assert first_team["owner_name"].startswith("(Admin) "), \
            f"Expected (Admin) prefix, got {first_team['owner_name']!r}"

        # League doc commissioner must be Test User 1
        lg = await db.leagues.find_one({"_id": ObjectId(r["league_id"])})
        assert lg["commissioner_id"] == first_team["owner_user_id"]
        assert lg["commissioner_name"].startswith("(Admin) ")
        # The platform admin should NOT be the commissioner
        assert lg["commissioner_id"] != admin

        # Team flagged as commissioner_team
        team_doc = await db.teams.find_one(
            {"_id": ObjectId(first_team["id"])}
        )
        assert team_doc["is_commissioner_team"] is True

        # The other 5 teams must NOT be commissioner teams
        for t in r["teams"][1:]:
            other = await db.teams.find_one({"_id": ObjectId(t["id"])})
            assert other["is_commissioner_team"] is False

        # All 6 users are flagged is_test_account
        for t in r["teams"]:
            u = await db.users.find_one({"_id": ObjectId(t["owner_user_id"])})
            assert u["is_test_account"] is True
    finally:
        if r:
            await delete_test_league(r["league_id"], _StubReq())
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_get_current_user_allows_writes_in_sandbox_mode():
    """The single most important behaviour change: sandbox mode is
    write-capable, unlike the pre-existing read_only mode."""
    import jwt
    from server import (
        create_impersonation_token, get_current_user as _get_cu,
        get_jwt_secret, JWT_ALGORITHM,
    )
    db = _db()
    import server
    server.db = db
    # Seed a real user to impersonate
    target = await db.users.insert_one({
        "email": "n61write@iter.test", "name": "Writer",
        "role": "user", "is_test_account": True,
        "created_at": datetime.now(timezone.utc),
    })
    tid = str(target.inserted_id)

    # Build a sandbox-mode token
    tok = create_impersonation_token(
        target_user_id=tid, target_email="n61write@iter.test",
        impersonator_id="admin1", impersonator_email="admin@test",
        minutes=720, mode="sandbox",
    )

    class _R:
        def __init__(self, method):
            self.method = method
            self.headers = {"Authorization": f"Bearer {tok}"}
            self.cookies = {}

    try:
        # Sandbox mode: writes must NOT raise
        for m in ("POST", "PUT", "PATCH", "DELETE"):
            u = await _get_cu(_R(m))
            assert u["_impersonation_mode"] == "sandbox"

        # Read-only mode: writes MUST raise 403
        tok_ro = create_impersonation_token(
            target_user_id=tid, target_email="n61write@iter.test",
            impersonator_id="admin1", impersonator_email="admin@test",
            minutes=15, mode="read_only",
        )
        class _R2:
            def __init__(self, method):
                self.method = method
                self.headers = {"Authorization": f"Bearer {tok_ro}"}
                self.cookies = {}
        for m in ("POST", "DELETE"):
            with pytest.raises(HTTPException) as exc:
                await _get_cu(_R2(m))
            assert exc.value.status_code == 403
    finally:
        await db.users.delete_one({"_id": ObjectId(tid)})

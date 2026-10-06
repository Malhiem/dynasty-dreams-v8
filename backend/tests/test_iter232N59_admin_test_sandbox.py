"""Iter 232N.59 — Admin Test Sandbox pytest suite.

Covers:
  1. Presets endpoint requires admin and returns 3 canonical presets.
  2. Create league seeds N users + N teams flagged as test artifacts.
  3. Create league honours num_teams override within the preset cap.
  4. Create league rejects num_teams above the preset cap.
  5. List sandbox leagues returns only `is_test_sandbox=true` docs.
  6. Add-test-user attaches a new user + team + bumps current_teams.
  7. List test users optionally filters by league_id.
  8. Delete league cascades: removes teams + test users +
     league_id-keyed rows across dependent collections.
  9. Delete keeps test users that own a team in a DIFFERENT sandbox
     league.
 10. Non-admin caller gets 403 on every endpoint.
 11. Impersonation start now rejects non-test-account targets with
     403 (integration with `/auth/impersonate-start`).
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
    def __init__(self, body: dict | None = None, cookies: dict | None = None):
        self._body = body or {}
        self.cookies = cookies or {}

    async def json(self):
        return self._body


def _fake_hash(pw: str) -> str:
    return f"hashed:{pw}"


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n59admin_{str(uid)[:6]}@iter.test",
        "name": "N59 Admin", "role": "admin",
        "password_hash": _fake_hash(os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")),
    })
    return str(uid)


async def _seed_user(db, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n59_{str(uid)[:6]}@iter.test",
        "name": "N59 User", "role": role,
        "password_hash": _fake_hash("User123!"),
    })
    return str(uid)


def _wire(admin_id: str, role: str = "admin"):
    """Install fake deps for the admin_test_sandbox router."""
    from routes import admin_test_sandbox as m
    db = _db()

    async def _fake_user(_r):
        u = await db.users.find_one({"_id": ObjectId(admin_id)})
        return u
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user
    m._deps["hash_password"] = _fake_hash
    return m


async def _cleanup(db, league_ids: list[str], user_ids: list[str]):
    for lid in league_ids:
        try:
            await db.leagues.delete_one({"_id": ObjectId(lid)})
        except Exception:
            pass
        await db.teams.delete_many({"league_id": lid})
        for coll in ["waiver_claims", "chat_messages", "drafts", "trades",
                     "draft_picks", "matchups", "roster_slots"]:
            try:
                await db[coll].delete_many({"league_id": lid})
            except Exception:
                pass
    if user_ids:
        try:
            await db.users.delete_many({
                "_id": {"$in": [ObjectId(u) for u in user_ids]},
            })
        except Exception:
            pass


# ─────────────────────── Endpoint tests ─────────────────────────────


@pytest.mark.asyncio
async def test_presets_requires_admin():
    from routes.admin_test_sandbox import list_presets
    db = _db()
    caller = await _seed_user(db, role="user")
    m = _wire(caller, role="user")
    try:
        with pytest.raises(HTTPException) as exc:
            await list_presets(_StubReq())
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, [], [caller])


@pytest.mark.asyncio
async def test_presets_returns_three_canonical_presets():
    from routes.admin_test_sandbox import list_presets
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    try:
        r = await list_presets(_StubReq())
        keys = [p["key"] for p in r["presets"]]
        assert set(keys) == {"nhl_redraft_12", "nhl_dynasty_16", "nhl_keeper_10"}
        for p in r["presets"]:
            for f in ("label", "sport", "format", "scoring_format",
                      "default_teams", "max_teams_supported"):
                assert f in p
        assert r["shared_password"]
    finally:
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_create_league_seeds_users_teams_and_flags():
    from routes.admin_test_sandbox import create_test_league, CreateTestLeagueRequest
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    try:
        r = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_redraft_12"),
            _StubReq(),
        )
        assert r["num_teams"] == 12
        assert len(r["teams"]) == 12
        # League flagged
        lg = await db.leagues.find_one({"_id": ObjectId(r["league_id"])})
        assert lg["is_test_sandbox"] is True
        assert lg["sandbox_preset_key"] == "nhl_redraft_12"
        # Every team flagged is_test_team, every owner user flagged is_test_account
        for t in r["teams"]:
            team = await db.teams.find_one({"_id": ObjectId(t["id"])})
            assert team["is_test_team"] is True
            u = await db.users.find_one({"_id": ObjectId(t["owner_user_id"])})
            assert u["is_test_account"] is True
            assert u["role"] == "user"
            assert u["email"].endswith("@sandbox.local")
    finally:
        # Full delete via endpoint cascade
        from routes.admin_test_sandbox import delete_test_league
        await delete_test_league(r["league_id"], _StubReq())
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_create_league_num_teams_override_and_cap():
    from routes.admin_test_sandbox import create_test_league, CreateTestLeagueRequest
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    created_id = None
    try:
        # Custom size within cap
        r = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_dynasty_16", num_teams=8),
            _StubReq(),
        )
        assert r["num_teams"] == 8
        assert len(r["teams"]) == 8
        created_id = r["league_id"]

        # Above cap → 400. nhl_redraft_12 now supports up to 32 teams
        # (iter 232N.82 bumped H2H presets to the platform ceiling), so
        # test the cap with a value above 32 that still fits within
        # pydantic's outer ge=4, le=32 validator.
        # Use 32 here — the preset explicitly caps at 32.
        with pytest.raises(HTTPException) as exc:
            await create_test_league(
                CreateTestLeagueRequest(preset_key="nhl_redraft_12", num_teams=33),
                _StubReq(),
            )
        assert exc.value.status_code == 400
    finally:
        if created_id:
            from routes.admin_test_sandbox import delete_test_league
            await delete_test_league(created_id, _StubReq())
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_list_sandbox_leagues_filters_by_flag():
    from routes.admin_test_sandbox import (
        create_test_league,
        list_test_leagues,
        delete_test_league,
        CreateTestLeagueRequest,
    )
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    r = None
    try:
        # Seed one sandbox + one non-sandbox league
        r = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_keeper_10", num_teams=6),
            _StubReq(),
        )
        non_sandbox = await db.leagues.insert_one({
            "name": "Real League", "sport": "nhl",
            "format": "redraft", "scoring_format": "head_to_head",
            "commissioner_id": admin, "commissioner_name": "N",
            "is_test_sandbox": False,
            "created_at": datetime.now(timezone.utc),
        })

        result = await list_test_leagues(_StubReq())
        ids = [x["id"] for x in result["leagues"]]
        assert r["league_id"] in ids
        assert str(non_sandbox.inserted_id) not in ids
        # Shape includes counts
        row = next(x for x in result["leagues"] if x["id"] == r["league_id"])
        assert row["current_teams"] == 6
        assert row["preset_key"] == "nhl_keeper_10"

        await db.leagues.delete_one({"_id": non_sandbox.inserted_id})
    finally:
        if r:
            await delete_test_league(r["league_id"], _StubReq())
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_add_test_user_bumps_teams():
    from routes.admin_test_sandbox import (
        create_test_league,
        add_test_user,
        AddTestUserRequest,
        delete_test_league,
        CreateTestLeagueRequest,
    )
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    r = None
    try:
        r = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_redraft_12", num_teams=4),
            _StubReq(),
        )
        added = await add_test_user(
            r["league_id"], AddTestUserRequest(name="Extra Manager"),
            _StubReq(),
        )
        assert added["name"] == "Extra Manager"
        assert added["team_name"].startswith("Extra Manager")
        # league now has 5 teams
        count = await db.teams.count_documents({"league_id": r["league_id"]})
        assert count == 5
    finally:
        if r:
            await delete_test_league(r["league_id"], _StubReq())
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_list_test_users_filters_by_league():
    from routes.admin_test_sandbox import (
        create_test_league, list_test_users, delete_test_league,
        CreateTestLeagueRequest,
    )
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    lg_a = None
    lg_b = None
    try:
        lg_a = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_redraft_12", num_teams=4),
            _StubReq(),
        )
        lg_b = await create_test_league(
            CreateTestLeagueRequest(preset_key="nhl_keeper_10", num_teams=5),
            _StubReq(),
        )

        # Global list — every test user across sandboxes
        r_all = await list_test_users(_StubReq())
        assert len(r_all["users"]) >= 9

        # Filtered to lg_b — only 5
        r_b = await list_test_users(_StubReq(), league_id=lg_b["league_id"])
        assert len(r_b["users"]) == 5
        for u in r_b["users"]:
            assert u["league_id"] == lg_b["league_id"]
            assert u["team_name"]
    finally:
        for lg in (lg_a, lg_b):
            if lg:
                await delete_test_league(lg["league_id"], _StubReq())
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_delete_cascade_removes_dependents():
    from routes.admin_test_sandbox import (
        create_test_league, delete_test_league, CreateTestLeagueRequest,
    )
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    r = await create_test_league(
        CreateTestLeagueRequest(preset_key="nhl_redraft_12", num_teams=5),
        _StubReq(),
    )
    lid = r["league_id"]
    owner_ids = [t["owner_user_id"] for t in r["teams"]]

    # Sprinkle some dependent docs
    await db.chat_messages.insert_one({"league_id": lid, "content": "hi"})
    await db.trades.insert_one({"league_id": lid, "status": "executed"})
    await db.matchups.insert_one({"league_id": lid, "week": 1})

    try:
        result = await delete_test_league(lid, _StubReq())
        assert result["ok"] is True
        assert result["teams_deleted"] == 5
        assert result["test_users_deleted"] == 5
        # League gone
        assert await db.leagues.find_one({"_id": ObjectId(lid)}) is None
        # Every dependent gone
        for coll in ["teams", "chat_messages", "trades", "matchups"]:
            assert await db[coll].count_documents({"league_id": lid}) == 0
        # Every test user gone
        for uid in owner_ids:
            assert await db.users.find_one({"_id": ObjectId(uid)}) is None
    finally:
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_delete_preserves_test_user_shared_across_leagues():
    """If a test user happens to have a test team in ANOTHER sandbox,
    deleting one league must NOT delete the user (they'd disappear from
    the other league too)."""
    from routes.admin_test_sandbox import (
        create_test_league, delete_test_league, CreateTestLeagueRequest,
    )
    db = _db()
    admin = await _seed_admin(db)
    _wire(admin)
    lg_a = await create_test_league(
        CreateTestLeagueRequest(preset_key="nhl_redraft_12", num_teams=4),
        _StubReq(),
    )
    lg_b = await create_test_league(
        CreateTestLeagueRequest(preset_key="nhl_keeper_10", num_teams=4),
        _StubReq(),
    )
    # Manually attach lg_a's first user to lg_b too (simulates a shared
    # user).
    shared_uid = lg_a["teams"][0]["owner_user_id"]
    await db.teams.insert_one({
        "league_id": lg_b["league_id"], "owner_id": shared_uid,
        "name": "Shared Team",
        "is_test_team": True,
        "roster": [], "lineup": {},
        "created_at": datetime.now(timezone.utc),
    })

    try:
        # Delete lg_a — shared user must survive because they still own
        # a team in lg_b.
        result = await delete_test_league(lg_a["league_id"], _StubReq())
        assert result["test_users_deleted"] == 3  # 4 owners, 1 shared kept
        surviving = await db.users.find_one({"_id": ObjectId(shared_uid)})
        assert surviving is not None
    finally:
        await delete_test_league(lg_b["league_id"], _StubReq())
        await _cleanup(db, [], [admin])


@pytest.mark.asyncio
async def test_endpoints_reject_non_admin():
    from routes.admin_test_sandbox import (
        list_presets, list_test_leagues, list_test_users,
    )
    db = _db()
    caller = await _seed_user(db, role="user")
    _wire(caller, role="user")
    try:
        for fn in (list_presets, list_test_leagues, list_test_users):
            with pytest.raises(HTTPException) as exc:
                await fn(_StubReq())
            assert exc.value.status_code == 403
    finally:
        await _cleanup(db, [], [caller])


@pytest.mark.asyncio
async def test_impersonate_start_rejects_non_test_account():
    """Integration test — the 232N.59 hardening: impersonation may only
    target `is_test_account=true` users."""
    from routes import auth as auth_m
    db = _db()
    admin = await _seed_admin(db)
    victim = await _seed_user(db, role="user")  # NOT a test account

    async def _fake_user(_r):
        u = await db.users.find_one({"_id": ObjectId(admin)})
        return u

    def _fake_imp_token(**kwargs):
        return "imp.token.stub"

    class _StubResp:
        def set_cookie(self, **kwargs): pass
        def delete_cookie(self, *a, **kw): pass

    auth_m._deps.update({
        "db": db,
        "get_current_user": _fake_user,
        "create_impersonation_token": _fake_imp_token,
        "COOKIE_SECURE": False, "COOKIE_SAMESITE": "lax",
    })

    try:
        with pytest.raises(HTTPException) as exc:
            await auth_m.impersonate_start(
                _StubReq(body={"target_user_id": victim, "reason": "test"}),
                _StubResp(),
            )
        assert exc.value.status_code == 403
        assert "test-sandbox" in exc.value.detail.lower()
    finally:
        await _cleanup(db, [], [admin, victim])

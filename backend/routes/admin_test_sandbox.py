"""Iter 232N.59 — Admin Test Sandbox router.

Lets platform admins spin up throwaway test leagues + test users with a
single API call, then hop between those test-user accounts via the
existing `/auth/impersonate-start` machinery so admins can experience
the app exactly as a manager, commissioner, or free-agent-hunter would.

Auth: platform admin only. All test users get `is_test_account=true`
so the existing impersonation start endpoint (which is now guarded
against non-test targets — see `auth.py`) admits them freely.

Endpoints:
  • GET  /api/admin/test-sandbox/presets
        → { presets: [...] }  static list, no DB access
  • POST /api/admin/test-sandbox/leagues
        Body: { preset_key, name?, num_teams?, seed_full? }
        → { league_id, teams: [{id, name, owner_user_id, owner_email}], user_password }
  • GET  /api/admin/test-sandbox/leagues
        → { leagues: [...] }  every league flagged is_test_sandbox
  • DELETE /api/admin/test-sandbox/leagues/{league_id}
        → cascade-deletes the league, its teams, its test users (only
          those NOT co-owning another test league), and every dependent
          collection row keyed off league_id.
  • POST /api/admin/test-sandbox/leagues/{league_id}/add-test-user
        Body: { email?, name? }
        → { user_id, email, team_id }
  • GET  /api/admin/test-sandbox/test-users?league_id={optional}
        → { users: [{id, email, name, team_id, team_name, league_id, league_name}] }
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


async def _require_admin(request: Request):
    user = await _get_user(request)
    if (
        not user
        or (user.get("role") != "admin"
            and user.get("permission_tier") not in ("admin", "senior_admin"))
    ):
        raise HTTPException(status_code=403, detail="Platform admin only")
    return user


# ─── Presets ─────────────────────────────────────────────────────────

# Format max-teams (from LeagueCreate ge=4, le=32). We publish a per-preset
# `max_teams_supported` so the UI's "max teams for this format" shortcut
# can populate the field without guessing.
_PRESETS: list[dict] = [
    {
        "key": "nhl_redraft_12",
        "label": "NHL Redraft 12",
        "description": "12-team head-to-head redraft; classic season sandbox.",
        "sport": "nhl",
        "format": "redraft",
        "scoring_format": "head_to_head",
        "draft_type": "snake",
        "default_teams": 12,
        "max_teams_supported": 20,
        "roster_spots": 20,
        "keepers_allowed": 0,
        "salary_cap_enabled": False,
    },
    {
        "key": "nhl_dynasty_16",
        "label": "NHL Dynasty 16",
        "description": "16-team dynasty with cap; long-horizon roster building.",
        "sport": "nhl",
        "format": "dynasty",
        "scoring_format": "head_to_head",
        "draft_type": "snake",
        "default_teams": 16,
        "max_teams_supported": 32,
        "roster_spots": 30,
        "keepers_allowed": 10,
        "salary_cap_enabled": True,
        "salary_cap": 90_000_000,
    },
    {
        "key": "nhl_keeper_10",
        "label": "NHL Keeper 10",
        "description": "10-team keeper league with 3 protected assets per year.",
        "sport": "nhl",
        "format": "keeper",
        "scoring_format": "head_to_head",
        "draft_type": "snake",
        "default_teams": 10,
        "max_teams_supported": 20,
        "roster_spots": 20,
        "keepers_allowed": 3,
        "salary_cap_enabled": False,
    },
]

# Default password every test user shares — trivially rotatable if we
# ever ship this outside dev. Documented in `/app/memory/test_credentials.md`.
_TEST_USER_PASSWORD = "TestUser2026!"


@router.get("/admin/test-sandbox/presets")
async def list_presets(request: Request):
    await _require_admin(request)
    return {"presets": _PRESETS, "shared_password": _TEST_USER_PASSWORD}


def _find_preset(key: str) -> dict:
    for p in _PRESETS:
        if p["key"] == key:
            return p
    raise HTTPException(status_code=400, detail=f"Unknown preset '{key}'")


# ─── Create league ───────────────────────────────────────────────────


class CreateTestLeagueRequest(BaseModel):
    preset_key: str
    name: Optional[str] = None
    num_teams: Optional[int] = Field(default=None, ge=4, le=32)


async def _make_test_user(db, admin_id: str, league_id_hint: str = "pending", idx: int = 1) -> dict:
    hash_password = _deps["hash_password"]
    suffix = secrets.token_hex(3)
    email = f"testuser{idx}_{suffix}@sandbox.local"
    # `username` has a unique index — include the suffix so we can host
    # multiple sandbox leagues concurrently without collisions.
    username = f"Test User {idx} ({suffix})"
    name = f"Test User {idx}"
    doc = {
        "email": email,
        "name": name,
        "username": username,
        "password_hash": hash_password(_TEST_USER_PASSWORD),
        "role": "user",
        "is_test_account": True,
        "created_by_admin_id": admin_id,
        "test_league_hint": league_id_hint,
        "created_at": datetime.now(timezone.utc),
    }
    r = await db.users.insert_one(doc)
    doc["_id"] = r.inserted_id
    return doc


@router.post("/admin/test-sandbox/leagues")
async def create_test_league(input: CreateTestLeagueRequest, request: Request):
    admin = await _require_admin(request)
    preset = _find_preset(input.preset_key)
    db = _db()

    num_teams = int(input.num_teams or preset["default_teams"])
    if num_teams < 4 or num_teams > int(preset["max_teams_supported"]):
        raise HTTPException(
            status_code=400,
            detail=f"num_teams must be between 4 and {preset['max_teams_supported']}",
        )
    league_name = (input.name or "").strip() or f"{preset['label']} Sandbox"

    # Iter 232N.61 — Test User 1 becomes the league commissioner
    # (not the platform admin). The platform admin can't do
    # commissioner-scoped actions while acting as a manager, so we
    # promote a test user to the commissioner slot and prefix their
    # name with "(Admin)" so admins can spot them in the switcher.
    # We create Test User 1 first, then use them as commissioner_id.
    admin_user = await _make_test_user(
        db, str(admin["_id"]), league_id_hint="pending", idx=1,
    )
    # Rename to "(Admin) Test User 1" so the switcher makes the role
    # obvious at a glance.
    admin_display_name = f"(Admin) {admin_user['name']}"
    await db.users.update_one(
        {"_id": admin_user["_id"]},
        {"$set": {"name": admin_display_name}},
    )
    admin_user["name"] = admin_display_name

    league_doc = {
        "name": league_name,
        "sport": preset["sport"],
        "format": preset["format"],
        "scoring_format": preset["scoring_format"],
        "max_teams": num_teams,
        "current_teams": num_teams,
        "commissioner_id": str(admin_user["_id"]),
        "commissioner_name": admin_user["name"],
        "salary_cap_enabled": bool(preset.get("salary_cap_enabled")),
        "salary_cap": preset.get("salary_cap"),
        "draft_type": preset["draft_type"],
        "roster_spots": preset["roster_spots"],
        "keepers_allowed": preset.get("keepers_allowed", 0),
        "is_private": True,
        "invite_code": secrets.token_urlsafe(8),
        "matchups_per_week": 1,
        "status": "setup",
        # 232N.59 — sandbox markers
        "is_test_sandbox": True,
        "sandbox_created_by": str(admin["_id"]),
        "sandbox_preset_key": preset["key"],
        # 232N.62 — draft cap view defaults (2026 NHL CBA minimum)
        "default_rookie_aav": 950_000,
        "minors_cap_treatment": "full",
        "created_at": datetime.now(timezone.utc),
    }
    lg = await db.leagues.insert_one(league_doc)
    league_id = str(lg.inserted_id)
    # Backfill the correct league_hint on the freshly-minted admin user.
    await db.users.update_one(
        {"_id": admin_user["_id"]},
        {"$set": {"test_league_hint": league_id}},
    )

    teams: list[dict] = []
    # Create the admin's team first
    admin_team_name = f"{admin_user['name']}'s Team"
    r0 = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": str(admin_user["_id"]),
        "owner_name": admin_user["name"],
        "name": admin_team_name,
        "roster": [], "lineup": {},
        "is_commissioner_team": True,
        "is_test_team": True,
        "created_at": datetime.now(timezone.utc),
    })
    teams.append({
        "id": str(r0.inserted_id),
        "name": admin_team_name,
        "owner_user_id": str(admin_user["_id"]),
        "owner_email": admin_user["email"],
        "owner_name": admin_user["name"],
    })
    # Remaining N-1 test users get plain manager roles.
    for i in range(2, num_teams + 1):
        user = await _make_test_user(db, str(admin["_id"]), league_id, i)
        team_name = f"Test User {i}'s Team"
        team_doc = {
            "league_id": league_id,
            "owner_id": str(user["_id"]),
            "owner_name": user["name"],
            "name": team_name,
            "roster": [],
            "lineup": {},
            "is_commissioner_team": False,
            "is_test_team": True,
            "created_at": datetime.now(timezone.utc),
        }
        r = await db.teams.insert_one(team_doc)
        teams.append({
            "id": str(r.inserted_id),
            "name": team_name,
            "owner_user_id": str(user["_id"]),
            "owner_email": user["email"],
            "owner_name": user["name"],
        })

    return {
        "league_id": league_id,
        "league_name": league_name,
        "preset_key": preset["key"],
        "num_teams": num_teams,
        "teams": teams,
        "user_password": _TEST_USER_PASSWORD,
    }


# ─── List sandbox leagues ────────────────────────────────────────────


@router.get("/admin/test-sandbox/leagues")
async def list_test_leagues(request: Request):
    await _require_admin(request)
    db = _db()
    out: list[dict] = []
    async for lg in db.leagues.find({"is_test_sandbox": True}).sort("created_at", -1):
        lid = str(lg["_id"])
        team_count = await db.teams.count_documents({"league_id": lid})
        out.append({
            "id": lid,
            "name": lg.get("name"),
            "preset_key": lg.get("sandbox_preset_key"),
            "format": lg.get("format"),
            "scoring_format": lg.get("scoring_format"),
            "max_teams": lg.get("max_teams"),
            "current_teams": team_count,
            "status": lg.get("status"),
            "sandbox_created_by": lg.get("sandbox_created_by"),
            "created_at": (
                lg.get("created_at").isoformat()
                if isinstance(lg.get("created_at"), datetime)
                else lg.get("created_at")
            ),
        })
    return {"leagues": out}


# ─── Add an extra test user to an existing sandbox league ────────────


class AddTestUserRequest(BaseModel):
    name: Optional[str] = None


@router.post("/admin/test-sandbox/leagues/{league_id}/add-test-user")
async def add_test_user(league_id: str, input: AddTestUserRequest, request: Request):
    admin = await _require_admin(request)
    db = _db()
    try:
        lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        lg = None
    if not lg or not lg.get("is_test_sandbox"):
        raise HTTPException(status_code=404, detail="Test sandbox league not found")

    existing = await db.teams.count_documents({"league_id": league_id})
    idx = existing + 1
    user = await _make_test_user(db, str(admin["_id"]), league_id, idx)
    if input.name:
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"name": input.name}})
        user["name"] = input.name

    team_name = f"{user['name']}'s Team"
    r = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": str(user["_id"]),
        "owner_name": user["name"],
        "name": team_name,
        "roster": [], "lineup": {},
        "is_test_team": True,
        "created_at": datetime.now(timezone.utc),
    })
    await db.leagues.update_one(
        {"_id": lg["_id"]},
        {"$inc": {"current_teams": 1}, "$max": {"max_teams": idx}},
    )
    return {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "name": user["name"],
        "team_id": str(r.inserted_id),
        "team_name": team_name,
    }


# ─── Delete a sandbox league (cascade) ───────────────────────────────


@router.delete("/admin/test-sandbox/leagues/{league_id}")
async def delete_test_league(league_id: str, request: Request):
    await _require_admin(request)
    db = _db()
    try:
        lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        lg = None
    if not lg or not lg.get("is_test_sandbox"):
        raise HTTPException(status_code=404, detail="Test sandbox league not found")

    # Collect owner ids of every test team in this league so we can
    # cascade-delete the test users too (but only if the user isn't
    # attached to another sandbox league).
    team_ids: list[str] = []
    owner_ids: set[str] = set()
    async for t in db.teams.find({"league_id": league_id}):
        team_ids.append(str(t["_id"]))
        oid = t.get("owner_id")
        if oid:
            owner_ids.add(str(oid))

    # Cascade-clean every collection keyed by league_id / team_id / draft.
    dependents = [
        "teams",
        "rosters",
        "waiver_claims",
        "waiver_budgets",
        "chat_messages",
        "chat_channels",
        "chat_reads",
        "trade_block",
        "trade_locks",
        "trades",
        "draft_picks",
        "drafts",
        "draft_undo_audit",
        "commissioner_pings",
        "matchups",
        "week_summaries",
        "league_invites",
        "notifications",
    ]
    deleted_counts: dict[str, int] = {}
    for coll in dependents:
        try:
            r = await db[coll].delete_many({"league_id": league_id})
            if r.deleted_count:
                deleted_counts[coll] = r.deleted_count
        except Exception as e:
            logger.debug(f"cascade delete {coll} skipped: {e}")

    # Remove any team-keyed docs the above missed.
    if team_ids:
        try:
            await db.roster_slots.delete_many({"team_id": {"$in": team_ids}})
        except Exception:
            pass

    # Delete test users that were seeded ONLY for this league (i.e.
    # have no other test-team elsewhere).
    users_deleted = 0
    for uid in owner_ids:
        u = await db.users.find_one({"_id": ObjectId(uid), "is_test_account": True})
        if not u:
            continue
        # Check for another team belonging to this user in any OTHER
        # sandbox league. If found, keep the user.
        other_teams = await db.teams.count_documents({
            "owner_id": uid,
            "league_id": {"$ne": league_id},
            "is_test_team": True,
        })
        if other_teams == 0:
            await db.users.delete_one({"_id": ObjectId(uid)})
            users_deleted += 1

    await db.leagues.delete_one({"_id": ObjectId(league_id)})

    return {
        "ok": True,
        "league_id": league_id,
        "teams_deleted": len(team_ids),
        "test_users_deleted": users_deleted,
        "collections_cleaned": deleted_counts,
    }


# ─── List available test users (for the impersonation dropdown) ──────


@router.get("/admin/test-sandbox/test-users")
async def list_test_users(request: Request, league_id: Optional[str] = None):
    await _require_admin(request)
    db = _db()

    league_filter = {}
    if league_id:
        league_filter["league_id"] = league_id

    out: list[dict] = []
    # Gather teams (with league_id), join to users.
    league_names: dict[str, str] = {}
    async for t in db.teams.find({"is_test_team": True, **league_filter}):
        uid = t.get("owner_id")
        if not uid:
            continue
        try:
            u = await db.users.find_one({"_id": ObjectId(uid), "is_test_account": True})
        except Exception:
            u = None
        if not u:
            continue
        lid = t.get("league_id")
        if lid and lid not in league_names:
            try:
                lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            except Exception:
                lg = None
            league_names[lid] = (lg or {}).get("name") or "(unknown)"
        out.append({
            "id": str(u["_id"]),
            "email": u.get("email"),
            "name": u.get("name"),
            "team_id": str(t["_id"]),
            "team_name": t.get("name"),
            "league_id": lid,
            "league_name": league_names.get(lid),
        })

    out.sort(key=lambda x: (x.get("league_name") or "", x.get("name") or ""))
    return {"users": out}

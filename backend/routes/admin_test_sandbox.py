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
            "sandbox_last_sim_week": lg.get("sandbox_last_sim_week") or 0,
            "sandbox_playoff_champion_team_id": lg.get("sandbox_playoff_champion_team_id"),
            "sandbox_playoffs_seeded_at": lg.get("sandbox_playoffs_seeded_at"),
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



# ─── Iter 232N.79 — Sandbox progression status ────────────────────


async def _draft_status_for_league(db, league_id: str) -> str:
    """Return the highest-priority draft state for this league:
      • "completed" if any real draft has finished (rosters exist)
      • "active" / "in_progress" if a draft is running
      • "scheduled" if one exists but hasn't started
      • "none" otherwise (no real draft doc, or only orphan stubs)
    """
    priority = ["completed", "active", "in_progress", "paused", "scheduled"]
    async for d in db.drafts.find({"league_id": league_id}):
        s = (d.get("status") or "").lower()
        if s == "completed":
            return "completed"
    async for d in db.drafts.find({"league_id": league_id}):
        s = (d.get("status") or "").lower()
        if s in priority and s != "completed":
            return s
    return "none"


async def _sandbox_status(db, league_id: str) -> dict:
    """4-step progression state used by the top bar rail."""
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("is_test_sandbox"):
        raise HTTPException(status_code=400, detail="Not a sandbox league")

    roster_spots = int(league.get("roster_spots") or 0)
    matchups_per_week = int(league.get("matchups_per_week") or 0)
    team_count = await db.teams.count_documents({"league_id": league_id})
    has_settings = bool(
        roster_spots > 0 and matchups_per_week > 0 and team_count >= 2
    )

    draft_status = await _draft_status_for_league(db, league_id)
    draft_done = draft_status == "completed"
    last_sim_week = int(league.get("sandbox_last_sim_week") or 0)
    playoffs_seeded = bool(league.get("sandbox_playoff_champion_team_id"))

    # Which step is the "active" one? (first not-yet-complete)
    if not has_settings:
        active_step = 1
    elif not draft_done:
        active_step = 2
    elif not playoffs_seeded and last_sim_week < 17:
        active_step = 3
    elif not playoffs_seeded:
        active_step = 3  # still regular season UI, but ready to advance
    else:
        active_step = 4

    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "has_settings": has_settings,
        "team_count": team_count,
        "roster_spots": roster_spots,
        "matchups_per_week": matchups_per_week,
        "draft_status": draft_status,
        "draft_done": draft_done,
        "last_sim_week": last_sim_week,
        "playoffs_seeded": playoffs_seeded,
        "champion_team_id": league.get("sandbox_playoff_champion_team_id"),
        "active_step": active_step,
    }


@router.get("/admin/test-sandbox/leagues/{league_id}/status")
async def sandbox_status(league_id: str, request: Request):
    await _require_admin(request)
    return await _sandbox_status(_db(), league_id)


# ─── Iter 232N.79 — One-click "simulate draft" ────────────────────


class SimulateDraftRequest(BaseModel):
    # How many players per team to fill. Defaults to league.roster_spots.
    picks_per_team: Optional[int] = Field(None, ge=1, le=50)


@router.post("/admin/test-sandbox/leagues/{league_id}/simulate-draft")
async def sandbox_simulate_draft(
    league_id: str,
    input: SimulateDraftRequest,
    request: Request,
):
    """Auto-draft every roster in the sandbox via a deterministic snake
    order using the top N players from the DB (non-prospects first,
    ranked by season points DESC then age ASC).

    On success:
      • Every team's `roster` is populated with `picks_per_team` player_ids
      • A `drafts` doc is inserted with `status="completed"` so the
        real-draft guard (`_looks_like_real_draft`) accepts it and the
        `draft_done` gate on simulate-week flips true
      • Idempotent: replaying wipes any prior sandbox-simulated draft
        + resets rosters + re-runs the pick order
    """
    admin = await _require_admin(request)
    db = _db()

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("is_test_sandbox"):
        raise HTTPException(
            status_code=400,
            detail="simulate-draft is only available on sandbox test leagues",
        )

    teams = await db.teams.find(
        {"league_id": league_id},
        sort=[("created_at", 1), ("_id", 1)],
    ).to_list(200)
    if len(teams) < 2:
        raise HTTPException(
            status_code=400, detail="Need at least 2 teams to draft",
        )

    picks_per_team = int(input.picks_per_team or league.get("roster_spots") or 20)
    total_picks = picks_per_team * len(teams)

    # Rank players — non-prospects first, then by season points DESC,
    # then by age ASC. Only pull enough for the draft.
    players = await db.players.find(
        {},
        {"_id": 1, "name": 1, "position": 1, "is_prospect": 1,
         "age": 1, "season_stats": 1},
    ).to_list(max(total_picks * 2, 500))

    def _rank(p):
        pts = float((p.get("season_stats") or {}).get("points", 0) or 0)
        age = int(p.get("age") or 99)
        prospect_penalty = 1 if p.get("is_prospect") else 0
        return (prospect_penalty, -pts, age)

    players.sort(key=_rank)
    pool = players[:total_picks]
    if len(pool) < total_picks:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough players in DB to fill {total_picks} picks "
                f"(need {total_picks}, have {len(pool)}). "
                "Run an NHL sync first."
            ),
        )

    # Wipe any prior simulated draft for this league so replays are clean.
    await db.drafts.delete_many({
        "league_id": league_id, "sandbox_sim_draft": True,
    })

    # Snake-order pick allocation.
    picks: list[dict] = []
    now = datetime.now(timezone.utc)
    # Reset every team's roster first.
    for t in teams:
        await db.teams.update_one(
            {"_id": t["_id"]},
            {"$set": {"roster": [], "lineup": {}}},
        )

    idx = 0
    for rnd in range(1, picks_per_team + 1):
        order = teams if rnd % 2 == 1 else list(reversed(teams))
        for team in order:
            if idx >= len(pool):
                break
            p = pool[idx]
            pid = str(p["_id"])
            await db.teams.update_one(
                {"_id": team["_id"]},
                {"$addToSet": {"roster": pid}},
            )
            picks.append({
                "round": rnd,
                "overall_pick": idx + 1,
                "team_id": str(team["_id"]),
                "team_name": team.get("name"),
                "player_id": pid,
                "player_name": p.get("name"),
                "position": p.get("position"),
            })
            idx += 1

    # Persist a completed draft doc so /leagues/{id}/upcoming-drafts
    # + get_locking_draft see a real, finished draft.
    draft_doc = {
        "league_id": league_id,
        "league_name": league.get("name"),
        "name": f"{league.get('name')} Auto-Draft",
        "draft_type": "snake",
        "total_rounds": picks_per_team,
        "current_pick": total_picks + 1,
        "status": "completed",
        "draft_started": True,
        "picks": picks,
        "pick_order": [str(t["_id"]) for t in teams],
        "started_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "sandbox_sim_draft": True,
        "simulated_by": admin.get("email"),
        "created_at": now,
    }
    r = await db.drafts.insert_one(draft_doc)
    draft_id = str(r.inserted_id)

    return {
        "ok": True,
        "draft_id": draft_id,
        "total_picks": len(picks),
        "picks_per_team": picks_per_team,
        "teams_drafted": len(teams),
        "picks_preview": picks[: min(len(picks), 8)],
    }


# ─── Iter 232N.69 — Simulate week of matchups (sandbox only) ──────


class SimulateWeekRequest(BaseModel):
    # Optional — if omitted we pick "current week + 1", so successive
    # clicks build up a season rather than replaying the same week.
    week: Optional[int] = Field(None, ge=1, le=30)
    # Iter 232N.76 — Sim to any week. When set, we loop from
    # `last_sim_week + 1` through `target_week` (inclusive), so
    # commissioners can jump straight to e.g. Week 10 without clicking
    # nine times. Ignored when `week` is also provided.
    target_week: Optional[int] = Field(None, ge=1, le=30)


@router.post("/admin/test-sandbox/leagues/{league_id}/simulate-week")
async def sandbox_simulate_week(
    league_id: str,
    input: SimulateWeekRequest,
    request: Request,
):
    """Generate a deterministic slate of fake matchup scores for a
    sandbox league so admins can see live-populated standings,
    dashboards, trophies, and streak widgets without waiting for real
    games to be played.

    Rules:
      • Only works on leagues flagged `is_test_sandbox=true` — refuses
        with 400 on real leagues (never mutate production data).
      • Deterministic: same (league_id, week) → same scores. Re-running
        the same week is idempotent (updates existing matchup docs
        rather than double-crediting team records).
      • Round-robin pairing per week based on team insertion order.
        Odd-team-count leagues get a "BYE" for the leftover team.
      • Team W/L/T + points_for + points_against advance by one game.

    Response includes the fresh W-L-T for every team so the UI can
    optimistically refresh without a second /standings round-trip.
    """
    admin = await _require_admin(request)
    db = _db()

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("is_test_sandbox"):
        raise HTTPException(
            status_code=400,
            detail="simulate-week is only available on sandbox test leagues",
        )

    # Iter 232N.79 — Gate on draft completion. Fake matchup scores for
    # teams with empty rosters is misleading; force the admin through
    # the Setup → Draft → Sim progression.
    draft_state = await _draft_status_for_league(db, league_id)
    if draft_state != "completed":
        raise HTTPException(
            status_code=400,
            detail=(
                "Draft not complete — schedule + run a real draft or use "
                "'Simulate draft' before simulating matchups."
            ),
        )

    teams = await db.teams.find(
        {"league_id": league_id},
        sort=[("created_at", 1), ("_id", 1)],
    ).to_list(200)
    if len(teams) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 teams to simulate a matchup",
        )

    # Pick the next week to simulate if the caller didn't specify.
    if input.week is not None:
        week = input.week
    else:
        cur = league.get("sandbox_last_sim_week") or 0
        week = int(cur) + 1

    # If this week has already been simulated, we're re-running for
    # idempotency. Roll back the previous credits from team docs
    # before writing new ones so counts stay consistent.
    prior_matchups = await db.matchups.find({
        "league_id": league_id, "week": week, "sandbox_sim": True,
    }).to_list(None)
    if prior_matchups:
        for m in prior_matchups:
            for side in ("home", "away"):
                tid = m.get(f"{side}_team_id")
                if not tid:
                    continue
                pf = m.get(f"{side}_score", 0) or 0
                pa_side = "away" if side == "home" else "home"
                pa = m.get(f"{pa_side}_score", 0) or 0
                outcome = m.get(f"{side}_outcome")
                inc: dict = {"points_for": -pf, "points_against": -pa}
                if outcome == "W":
                    inc["wins"] = -1
                elif outcome == "L":
                    inc["losses"] = -1
                elif outcome == "T":
                    inc["ties"] = -1
                try:
                    await db.teams.update_one({"_id": ObjectId(tid)}, {"$inc": inc})
                except Exception:
                    continue
        await db.matchups.delete_many({
            "league_id": league_id, "week": week, "sandbox_sim": True,
        })

    # Deterministic RNG seeded on (league_id, week) so re-running
    # produces the same slate — key for tests + reproducing bug reports.
    import random
    rng = random.Random(f"{league_id}:{week}")
    rotated = teams[:]
    # Rotate so week N has a different pairing than week 1.
    if len(rotated) > 2:
        rot = (week - 1) % (len(rotated) - 1)
        # Standard round-robin: fix team 0, rotate the rest.
        rotated = [rotated[0]] + rotated[1:][rot:] + rotated[1:][:rot]

    matchups_out: list[dict] = []
    now = datetime.now(timezone.utc)
    for i in range(0, len(rotated) - 1, 2):
        home_t = rotated[i]
        away_t = rotated[i + 1]
        home_score = rng.randint(75, 145)
        away_score = rng.randint(75, 145)
        if home_score > away_score:
            home_out, away_out = "W", "L"
        elif home_score < away_score:
            home_out, away_out = "L", "W"
        else:
            home_out = away_out = "T"

        matchup_doc = {
            "league_id": league_id,
            "week": week,
            "home_team_id": str(home_t["_id"]),
            "away_team_id": str(away_t["_id"]),
            "home_team_name": home_t.get("name"),
            "away_team_name": away_t.get("name"),
            "home_score": home_score,
            "away_score": away_score,
            "home_outcome": home_out,
            "away_outcome": away_out,
            "status": "final",
            "sandbox_sim": True,
            "simulated_by": admin.get("email"),
            "simulated_at": now,
        }
        await db.matchups.insert_one(matchup_doc)

        # Update team standings counters.
        for tid, pf, pa, out in [
            (home_t["_id"], home_score, away_score, home_out),
            (away_t["_id"], away_score, home_score, away_out),
        ]:
            inc = {"points_for": pf, "points_against": pa}
            if out == "W":
                inc["wins"] = 1
            elif out == "L":
                inc["losses"] = 1
            else:
                inc["ties"] = 1
            await db.teams.update_one({"_id": tid}, {"$inc": inc})

        matchups_out.append({
            "home": home_t.get("name"), "away": away_t.get("name"),
            "home_score": home_score, "away_score": away_score,
            "home_outcome": home_out, "away_outcome": away_out,
        })

    # Handle odd team count — one team gets a BYE for this week.
    bye_team = rotated[-1] if len(rotated) % 2 == 1 else None
    if bye_team:
        matchups_out.append({
            "home": bye_team.get("name"), "away": "BYE",
            "home_score": 0, "away_score": 0,
            "home_outcome": None, "away_outcome": None,
        })

    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"sandbox_last_sim_week": week}},
    )

    fresh_teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "wins": 1, "losses": 1, "ties": 1,
         "points_for": 1, "points_against": 1},
    ).to_list(200)
    return {
        "ok": True,
        "week": week,
        "matchups": matchups_out,
        "teams": [
            {
                "id": str(t["_id"]),
                "name": t.get("name"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "ties": t.get("ties", 0),
                "points_for": t.get("points_for", 0),
                "points_against": t.get("points_against", 0),
            } for t in fresh_teams
        ],
        "replayed": bool(prior_matchups),
    }


@router.post("/admin/test-sandbox/leagues/{league_id}/simulate-to-week")
async def sandbox_simulate_to_week(
    league_id: str,
    input: SimulateWeekRequest,
    request: Request,
):
    """Iter 232N.76 — Simulate every week from `last_sim_week + 1`
    through `input.target_week` (inclusive) in a single call. Reuses
    `sandbox_simulate_week` per iteration so scoring, rollback, and
    audit stay perfectly consistent with the one-off Simulate button.
    Refuses to move backwards (`target_week <= last_sim_week`) so the
    caller has to hit /reset-simulation first if that's the intent.
    """
    await _require_admin(request)
    db = _db()

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("is_test_sandbox"):
        raise HTTPException(
            status_code=400,
            detail="simulate-to-week is only available on sandbox test leagues",
        )
    target = input.target_week
    if target is None:
        raise HTTPException(status_code=400, detail="target_week is required")

    start = int(league.get("sandbox_last_sim_week") or 0) + 1
    if target < start:
        raise HTTPException(
            status_code=400,
            detail=(
                f"target_week ({target}) is not ahead of the current "
                f"last simulated week ({start - 1}). Use /reset-simulation "
                "first to replay from Week 1."
            ),
        )

    weeks_run: list[int] = []
    for wk in range(start, target + 1):
        await sandbox_simulate_week(
            league_id, SimulateWeekRequest(week=wk), request,
        )
        weeks_run.append(wk)

    fresh_teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "wins": 1, "losses": 1, "ties": 1,
         "points_for": 1, "points_against": 1},
    ).to_list(200)
    return {
        "ok": True,
        "target_week": target,
        "weeks_run": weeks_run,
        "teams": [
            {
                "id": str(t["_id"]),
                "name": t.get("name"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "ties": t.get("ties", 0),
                "points_for": t.get("points_for", 0),
                "points_against": t.get("points_against", 0),
            } for t in fresh_teams
        ],
    }


# ─── Iter 232N.78 — Auto-seed playoff bracket ─────────────────────


class SeedPlayoffsRequest(BaseModel):
    # Optional: how many teams make the playoffs. Defaults to 8 (or the
    # league.playoff_teams config if set) with a floor of 4.
    num_playoff_teams: Optional[int] = Field(None, ge=2, le=32)
    # Optional min completed regular-season week gate. Default 17 —
    # matches typical fantasy hockey regular-season length.
    min_week: int = Field(17, ge=1, le=30)


@router.post("/admin/test-sandbox/leagues/{league_id}/seed-playoffs")
async def sandbox_seed_playoffs(
    league_id: str,
    input: SeedPlayoffsRequest,
    request: Request,
):
    """Seed + simulate a single-elimination playoff bracket for a
    sandbox league that has finished its regular season.

    Rules:
      • League must be `is_test_sandbox=true` (400 otherwise).
      • `sandbox_last_sim_week` must be >= `min_week` (default 17).
      • Top `num_playoff_teams` teams by (wins DESC, points_for DESC)
        get in; 1v8 / 2v7 / 3v6 / 4v5 seed → winners meet in the
        semifinals → final. Round scores use the same deterministic
        RNG as `simulate-week` (seeded on `league_id:playoffs:round`)
        so replays are idempotent.
      • Playoff matchups persist to `db.matchups` with
        `sandbox_playoff=true` (distinct from `sandbox_sim=true` so
        `/reset-simulation` still wipes them without collateral damage
        to regular-season matchups when we upgrade that flag later).
      • Team standings counters (`wins/losses/points_for/against`) are
        NOT updated by playoff results — playoffs live in the
        bracket, not the standings.
    """
    admin = await _require_admin(request)
    db = _db()

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("is_test_sandbox"):
        raise HTTPException(
            status_code=400,
            detail="seed-playoffs is only available on sandbox test leagues",
        )
    last_sim = int(league.get("sandbox_last_sim_week") or 0)
    if last_sim < input.min_week:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Regular season must be simulated through at least "
                f"Week {input.min_week} first — currently at Week {last_sim}. "
                f"Use simulate-to-week to advance."
            ),
        )

    # Rank teams for seeding.
    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "wins": 1, "losses": 1, "ties": 1,
         "points_for": 1, "points_against": 1},
    ).to_list(200)
    if len(teams) < 4:
        raise HTTPException(status_code=400,
                            detail="Need at least 4 teams to seed a playoff bracket")

    n_playoff = input.num_playoff_teams or league.get("playoff_teams") or 8
    n_playoff = max(2, min(int(n_playoff), len(teams)))
    # Round DOWN to nearest power of two for a clean single-elim bracket.
    import math
    n_playoff = 2 ** int(math.log2(n_playoff))
    n_playoff = max(2, n_playoff)

    teams.sort(key=lambda t: (
        -(t.get("wins") or 0),
        -(t.get("points_for") or 0),
        (t.get("points_against") or 0),
    ))
    seeds = teams[:n_playoff]

    # Nuke any prior playoff bracket for this league (idempotent replay).
    await db.matchups.delete_many({
        "league_id": league_id, "sandbox_playoff": True,
    })

    # Round-by-round simulation. Round 0 = QF (or R1), then SF, then F.
    import random
    now = datetime.now(timezone.utc)
    bracket: list[dict] = []
    active = seeds[:]
    round_num = 0
    while len(active) > 1:
        round_num += 1
        rng = random.Random(f"{league_id}:playoffs:round:{round_num}")
        # 1 vs last, 2 vs second-last, etc.
        pairs = []
        top, bot = 0, len(active) - 1
        while top < bot:
            pairs.append((active[top], active[bot]))
            top += 1
            bot -= 1
        winners = []
        for home_t, away_t in pairs:
            home_score = rng.randint(80, 150)
            away_score = rng.randint(80, 150)
            if home_score == away_score:      # No ties in playoffs.
                if rng.random() < 0.5:
                    home_score += 1
                else:
                    away_score += 1
            winner = home_t if home_score > away_score else away_t
            loser = away_t if winner is home_t else home_t
            matchup_doc = {
                "league_id": league_id,
                "playoff_round": round_num,
                "home_team_id": str(home_t["_id"]),
                "away_team_id": str(away_t["_id"]),
                "home_team_name": home_t.get("name"),
                "away_team_name": away_t.get("name"),
                "home_score": home_score,
                "away_score": away_score,
                "winner_team_id": str(winner["_id"]),
                "status": "final",
                "is_playoff": True,
                "sandbox_playoff": True,
                "simulated_by": admin.get("email"),
                "simulated_at": now,
            }
            await db.matchups.insert_one(matchup_doc)
            bracket.append({
                "round": round_num,
                "home": home_t.get("name"), "away": away_t.get("name"),
                "home_score": home_score, "away_score": away_score,
                "winner": winner.get("name"),
                "loser": loser.get("name"),
            })
            winners.append(winner)
        active = winners

    champion = active[0] if active else None
    # Iter 232N.79 — Stamp the trophy so it surfaces in the existing
    # `/leagues/{id}/trophy-room` + `/teams/{id}/trophy-room` UIs.
    season_year = int(
        league.get("current_season_year")
        or (str(league.get("season") or "").split("-")[0] or "2026")
        if str(league.get("season") or "2026").split("-")[0].isdigit()
        else 2026
    )
    if champion:
        # Team-level award marker (used by TrophyRoom banners).
        await db.teams.update_one(
            {"_id": champion["_id"]},
            {"$set": {"championship_won_at": now.isoformat()}},
        )
        # league_seasons snapshot — minimal shape that the trophy-room
        # endpoint expects (season_year + teams[].awards).
        teams_snap: list[dict] = []
        for t in teams:
            teams_snap.append({
                "team_id": str(t["_id"]),
                "team_name": t.get("name"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "ties": t.get("ties", 0),
                "points_for": float(t.get("points_for", 0.0) or 0.0),
                "points_against": float(t.get("points_against", 0.0) or 0.0),
                "roster": list(t.get("roster") or []),
                "awards": {
                    "championship_won_at": (
                        now.isoformat()
                        if str(t["_id"]) == str(champion["_id"])
                        else None
                    ),
                },
            })
        await db.league_seasons.update_one(
            {"league_id": league_id, "season_year": season_year,
             "sandbox_sim": True},
            {"$set": {
                "league_id": league_id,
                "season_year": season_year,
                "status": "complete",
                "snapshot_at": now,
                "champion_team_name": champion.get("name"),
                "champion_team_id": str(champion["_id"]),
                "teams": teams_snap,
                "sandbox_sim": True,
                "completed_by": admin.get("email"),
            }},
            upsert=True,
        )
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "sandbox_playoffs_seeded_at": now.isoformat(),
            "sandbox_playoff_champion_team_id": (
                str(champion["_id"]) if champion else None
            ),
            "sandbox_playoff_season_year": season_year,
        }},
    )

    return {
        "ok": True,
        "num_playoff_teams": n_playoff,
        "rounds_played": round_num,
        "champion": champion.get("name") if champion else None,
        "champion_team_id": str(champion["_id"]) if champion else None,
        "seeds": [
            {
                "seed": i + 1,
                "team_id": str(t["_id"]),
                "name": t.get("name"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "points_for": t.get("points_for", 0),
            } for i, t in enumerate(seeds)
        ],
        "bracket": bracket,
    }


@router.post("/admin/test-sandbox/leagues/{league_id}/reset-simulation")
async def sandbox_reset_simulation(league_id: str, request: Request):
    """Wipe every simulated matchup + zero out every team's counters,
    returning the sandbox league to a pristine "no games played" state.
    Useful for testing the empty-standings UI (Iter 232N.68) after
    someone has already simulated a week."""
    await _require_admin(request)
    db = _db()
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not league.get("is_test_sandbox"):
        raise HTTPException(
            status_code=400,
            detail="reset-simulation is only available on sandbox test leagues",
        )
    deleted = await db.matchups.delete_many({
        "league_id": league_id,
        "$or": [{"sandbox_sim": True}, {"sandbox_playoff": True}],
    })
    # Iter 232N.79 — Also wipe the auto-drafted rosters + draft doc and
    # champion award stamps so the sandbox truly returns to "day 1".
    await db.drafts.delete_many({
        "league_id": league_id, "sandbox_sim_draft": True,
    })
    await db.league_seasons.delete_many({
        "league_id": league_id, "sandbox_sim": True,
    })
    await db.teams.update_many(
        {"league_id": league_id},
        {"$set": {"wins": 0, "losses": 0, "ties": 0,
                  "points_for": 0, "points_against": 0,
                  "roster": [], "lineup": {}},
         "$unset": {"championship_won_at": ""}},
    )
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$unset": {
            "sandbox_last_sim_week": "",
            "sandbox_playoffs_seeded_at": "",
            "sandbox_playoff_champion_team_id": "",
            "sandbox_playoff_season_year": "",
        }},
    )
    return {"ok": True, "matchups_deleted": deleted.deleted_count}



# ─── Iter 232N.70 — Orphan draft cleanup ──────────────────────────


@router.post("/admin/drafts/cleanup-orphans")
async def cleanup_orphan_drafts(request: Request, league_id: Optional[str] = None):
    """Scan `db.drafts` for orphan / stub docs that lack any real
    scheduling or ordering signal and delete them. Orphans are typically
    leftover from cancelled setup flows or manual DB pokes and cause
    the "why is there a draft running?" false positive on the FA
    pickup lock (see `utils/draft_lock.py::_looks_like_real_draft`).

    Scoped to a single league when `league_id` is provided, otherwise
    scans platform-wide (admin discretion — every deletion is audited).
    """
    admin = await _require_admin(request)
    db = _db()
    from utils.draft_lock import _looks_like_real_draft

    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    cursor = db.drafts.find(query)
    deleted_ids: list[str] = []
    kept = 0
    async for d in cursor:
        if _looks_like_real_draft(d):
            kept += 1
            continue
        did = d["_id"]
        # Also nuke any dangling draft_picks that referenced the orphan
        # so the DB stays consistent.
        try:
            await db.draft_picks.delete_many({"draft_id": str(did)})
        except Exception:
            pass
        await db.drafts.delete_one({"_id": did})
        deleted_ids.append(str(did))

    if deleted_ids:
        try:
            await db.audit_log.insert_one({
                "action": "draft_orphan_cleanup",
                "actor_email": admin.get("email"),
                "actor_id": str(admin.get("_id")),
                "deleted_draft_ids": deleted_ids,
                "league_id": league_id,
                "at": datetime.now(timezone.utc),
            })
        except Exception:
            pass

    return {
        "ok": True,
        "deleted": len(deleted_ids),
        "kept": kept,
        "deleted_draft_ids": deleted_ids,
    }

"""Iter 231ag — Database Hygiene admin panel.

Surfaces counts of suspect-looking rows (test prefixes, @example.com
users, zombie drafts, orphan leagues, polluting player names) with a
one-click "Sweep now" button so the commissioner can wipe pollution
without pinging the engineering team.

Auth: platform-tier admin only (`user.role == "admin"` OR
`user.email == ADMIN_EMAIL`).

Endpoints:
    GET  /api/admin/db-hygiene/report   — counts only, read-only
    POST /api/admin/db-hygiene/sweep    — actually deletes the rows,
                                          returns before/after counts
                                          + a full audit row.

Pattern parity with `/app/backend/tests/conftest.py` — single source of
truth for "what counts as pollution" lives in this module's regexes;
the conftest re-exports them at test time via `import` so we don't
drift across files.

Patterns swept (all best-effort, no FK enforcement):
    • players: `_test_seed=True` OR legacy regex match
    • leagues: `_test_seed=True` OR regex match (`iter/i\\d{3}` or `TEST_`)
    • users:   `_test_seed=True` OR `@example.com` email domain
    • drafts:  `status=active` AND empty `team_abbrs` (zombie drafts)
    • orphans: leagues whose `commissioner_id` no longer resolves to
               a user; teams whose `league_id` no longer resolves to
               a league.

Cascade: when a polluted league or test user is removed, ALL its
dependents (teams, drafts, waiver_claims, waiver_budgets, team_invites,
league_invites) are removed too.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _is_platform_admin(user: dict) -> bool:
    """Platform-tier admin gate. Two paths:
       • `user.role == "admin"` (explicit role tag).
       • `user.email == ADMIN_EMAIL` env var (site-owner override).
    """
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    return user.get("email") == admin_email


# ─── Canonical pollution patterns ─────────────────────────────────────
# These are the same regexes the global tests/conftest.py uses. Keep them
# in sync — when a new pollution pattern surfaces, update BOTH places.

PLAYER_NAME_REGEX = (
    r"^("
    r"ForceP|FutureP|WaiverTarget|RollbackP|"
    r"[A-Z][a-zA-Z]+P-[a-f0-9]{4,}|"
    r"Iter\s*23\d[a-z]{0,3}\s*Player|"
    r"i\s*23\d[a-z]{0,3}\s*Player|"
    r"i\s*22\d[a-z]{0,3}\s*Player|"
    r"NHL Veteran Forward|Minor Eligible Forward|Repeat Pick|"
    r"TestPlayer|Waiver Player"
    r")"
)
LEAGUE_NAME_REGEX = r"^(iter|i)\s*\d{3}[a-z]{0,3}[-_ ]|^TEST_"
USER_EMAIL_REGEX = r"@example\.com$"


# ─── GET /admin/db-hygiene/report ────────────────────────────────────


@router.get("/admin/db-hygiene/report")
async def db_hygiene_report(request: Request) -> Dict[str, Any]:
    """Read-only inspection — counts of every pollution bucket.

    No deletes. Safe to call frequently. UI polls this every ~5s when
    the panel is open.
    """
    user = await _get_user(request)
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform admin only")
    return await _gather_counts(_db())


# ─── POST /admin/db-hygiene/sweep ────────────────────────────────────


@router.post("/admin/db-hygiene/sweep")
async def db_hygiene_sweep(request: Request) -> Dict[str, Any]:
    """Actually delete everything matching the patterns above.

    Returns before/after counts AND a full per-collection breakdown
    of deletion totals. Writes an `admin_user_actions` audit row.
    """
    user = await _get_user(request)
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform admin only")

    db = _db()
    before = await _gather_counts(db)
    deletions = await _sweep_all(db)
    after = await _gather_counts(db)
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "platform",
        "action": "db_hygiene_sweep",
        "reason": "Platform admin ran one-click DB hygiene sweep.",
        "metadata": {
            "before": before,
            "after": after,
            "deletions": deletions,
        },
        "mocked": False,
        "ts": now_iso,
    })

    return {
        "ran_at": now_iso,
        "ran_by": user.get("email"),
        "before": before,
        "after": after,
        "deletions": deletions,
    }


# ─── Internal helpers ────────────────────────────────────────────────


async def _gather_counts(db) -> Dict[str, int]:
    """Count every pollution bucket. All queries are best-effort —
    a failure on one bucket doesn't poison the rest.

    Iter 231ag note: avoid `$or` over two index-backed clauses (causes
    Mongo to return inflated phantom counts from stale index entries
    when the query planner merges intersections). Count each clause
    separately + dedupe via union of `_id` sets.
    """
    player_pat = re.compile(PLAYER_NAME_REGEX, re.IGNORECASE)
    league_pat = re.compile(LEAGUE_NAME_REGEX, re.IGNORECASE)
    email_pat = re.compile(USER_EMAIL_REGEX, re.IGNORECASE)

    async def _union_count(coll, clauses: List[dict]) -> int:
        ids: set = set()
        for clause in clauses:
            async for doc in coll.find(clause, {"_id": 1}):
                ids.add(doc["_id"])
        return len(ids)

    polluting_players = await _union_count(db.players, [
        {"_test_seed": True},
        {"name": {"$regex": player_pat}},
    ])
    ephemeral_leagues = await _union_count(db.leagues, [
        {"_test_seed": True},
        {"name": {"$regex": league_pat}},
    ])
    test_users = await _union_count(db.users, [
        {"_test_seed": True},
        {"email": {"$regex": email_pat}},
    ])
    zombie_drafts = await db.drafts.count_documents({
        "status": "active",
        "$or": [
            {"team_abbrs": []},
            {"team_abbrs": None},
            {"team_abbrs": {"$exists": False}},
        ],
    })

    # Orphan leagues: commissioner_id no longer in users.
    real_user_ids = set()
    async for u in db.users.find({}, {"_id": 1}):
        real_user_ids.add(str(u["_id"]))
    orphan_leagues = 0
    async for lg in db.leagues.find({}, {"commissioner_id": 1}):
        cid = lg.get("commissioner_id")
        if cid and cid not in real_user_ids:
            orphan_leagues += 1

    # Orphan teams: league_id no longer in leagues.
    real_league_ids = set()
    async for lg in db.leagues.find({}, {"_id": 1}):
        real_league_ids.add(str(lg["_id"]))
    orphan_teams = 0
    async for t in db.teams.find({}, {"league_id": 1}):
        lid = t.get("league_id")
        if lid and lid not in real_league_ids:
            orphan_teams += 1

    # Headline totals (real-data baseline so the UI can show pollution-%).
    return {
        "polluting_players": polluting_players,
        "ephemeral_leagues": ephemeral_leagues,
        "test_users": test_users,
        "zombie_drafts": zombie_drafts,
        "orphan_leagues": orphan_leagues,
        "orphan_teams": orphan_teams,
        "total_players": await db.players.count_documents({}),
        "total_leagues": await db.leagues.count_documents({}),
        "total_users": await db.users.count_documents({}),
        "total_drafts": await db.drafts.count_documents({}),
        "total_teams": await db.teams.count_documents({}),
    }


async def _sweep_all(db) -> Dict[str, int]:
    """Execute every cleanup pass and return a per-collection deletion
    map. Order matters — we delete leaves before parents so referential
    integrity falls through naturally:

        players  → claims  (claims reference player_id)
        leagues  → teams / drafts / claims / budgets / invites
        users    → (cascade to their owned leagues, then the user row)
        drafts   → just status flip on zombies (no cascade needed)
    """
    player_pat = re.compile(PLAYER_NAME_REGEX, re.IGNORECASE)
    league_pat = re.compile(LEAGUE_NAME_REGEX, re.IGNORECASE)
    email_pat = re.compile(USER_EMAIL_REGEX, re.IGNORECASE)

    deletions: Dict[str, int] = {
        "players": 0, "teams_pulled_roster_entries": 0, "waiver_claims": 0,
        "waiver_budgets": 0, "team_invites": 0, "league_invites": 0,
        "leagues": 0, "teams": 0, "drafts": 0, "drafts_archived": 0,
        "users": 0,
    }

    # ── 1. Players ──
    polluted_players = await db.players.find(
        {"$or": [{"_test_seed": True}, {"name": {"$regex": player_pat}}]},
        {"_id": 1},
    ).to_list(None)
    pids = [str(p["_id"]) for p in polluted_players]
    if pids:
        r = await db.teams.update_many(
            {"roster": {"$in": pids}},
            {"$pull": {"roster": {"$in": pids}}},
        )
        deletions["teams_pulled_roster_entries"] = r.modified_count or 0
        r = await db.waiver_claims.delete_many({"player_id": {"$in": pids}})
        deletions["waiver_claims"] += r.deleted_count or 0
        r = await db.players.delete_many({"_id": {"$in": [p["_id"] for p in polluted_players]}})
        deletions["players"] = r.deleted_count or 0

    # ── 2. Ephemeral leagues + their dependents ──
    polluted_leagues = await db.leagues.find(
        {"$or": [{"_test_seed": True}, {"name": {"$regex": league_pat}}]},
        {"_id": 1},
    ).to_list(None)
    lids = [str(lg["_id"]) for lg in polluted_leagues]
    if lids:
        r = await db.teams.delete_many({"league_id": {"$in": lids}})
        deletions["teams"] += r.deleted_count or 0
        r = await db.drafts.delete_many({"league_id": {"$in": lids}})
        deletions["drafts"] += r.deleted_count or 0
        r = await db.waiver_claims.delete_many({"league_id": {"$in": lids}})
        deletions["waiver_claims"] += r.deleted_count or 0
        r = await db.waiver_budgets.delete_many({"league_id": {"$in": lids}})
        deletions["waiver_budgets"] += r.deleted_count or 0
        r = await db.team_invites.delete_many({"league_id": {"$in": lids}})
        deletions["team_invites"] += r.deleted_count or 0
        r = await db.league_invites.delete_many({"league_id": {"$in": lids}})
        deletions["league_invites"] += r.deleted_count or 0
        r = await db.leagues.delete_many({"_id": {"$in": [lg["_id"] for lg in polluted_leagues]}})
        deletions["leagues"] += r.deleted_count or 0

    # ── 3. Test users + their owned leagues ──
    test_users = await db.users.find(
        {"$or": [{"_test_seed": True}, {"email": {"$regex": email_pat}}]},
        {"_id": 1},
    ).to_list(None)
    if test_users:
        uids = [str(u["_id"]) for u in test_users]
        owned_leagues = await db.leagues.find(
            {"commissioner_id": {"$in": uids}}, {"_id": 1},
        ).to_list(None)
        owned_lids = [str(lg["_id"]) for lg in owned_leagues]
        if owned_lids:
            r = await db.teams.delete_many({"league_id": {"$in": owned_lids}})
            deletions["teams"] += r.deleted_count or 0
            r = await db.drafts.delete_many({"league_id": {"$in": owned_lids}})
            deletions["drafts"] += r.deleted_count or 0
            r = await db.waiver_claims.delete_many({"league_id": {"$in": owned_lids}})
            deletions["waiver_claims"] += r.deleted_count or 0
            r = await db.waiver_budgets.delete_many({"league_id": {"$in": owned_lids}})
            deletions["waiver_budgets"] += r.deleted_count or 0
            r = await db.team_invites.delete_many({"league_id": {"$in": owned_lids}})
            deletions["team_invites"] += r.deleted_count or 0
            r = await db.league_invites.delete_many({"league_id": {"$in": owned_lids}})
            deletions["league_invites"] += r.deleted_count or 0
            r = await db.leagues.delete_many({"_id": {"$in": [lg["_id"] for lg in owned_leagues]}})
            deletions["leagues"] += r.deleted_count or 0
        r = await db.teams.delete_many({"owner_id": {"$in": uids}})
        deletions["teams"] += r.deleted_count or 0
        r = await db.users.delete_many({"_id": {"$in": [u["_id"] for u in test_users]}})
        deletions["users"] = r.deleted_count or 0

    # ── 4. Zombie drafts (empty team_abbrs while active) ──
    r = await db.drafts.update_many(
        {
            "status": "active",
            "$or": [
                {"team_abbrs": []},
                {"team_abbrs": None},
                {"team_abbrs": {"$exists": False}},
            ],
        },
        {"$set": {
            "status": "archived",
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_reason": "db_hygiene_sweep_zombie_empty_team_abbrs",
        }},
    )
    deletions["drafts_archived"] = r.modified_count or 0

    # ── 5. Orphan leagues + orphan teams ──
    # Iter 231ag — Catch the long-tail cleanup the test-pollution
    # cascade missed: leagues whose `commissioner_id` no longer
    # resolves to a real user (and teams whose `league_id` no longer
    # resolves to a real league).
    real_user_ids = set()
    async for u in db.users.find({}, {"_id": 1}):
        real_user_ids.add(str(u["_id"]))
    orphan_league_ids: List[str] = []
    async for lg in db.leagues.find({}, {"commissioner_id": 1}):
        cid = lg.get("commissioner_id")
        if cid and cid not in real_user_ids:
            orphan_league_ids.append(str(lg["_id"]))
    if orphan_league_ids:
        r = await db.teams.delete_many({"league_id": {"$in": orphan_league_ids}})
        deletions["teams"] += r.deleted_count or 0
        r = await db.drafts.delete_many({"league_id": {"$in": orphan_league_ids}})
        deletions["drafts"] += r.deleted_count or 0
        r = await db.waiver_claims.delete_many({"league_id": {"$in": orphan_league_ids}})
        deletions["waiver_claims"] += r.deleted_count or 0
        r = await db.waiver_budgets.delete_many({"league_id": {"$in": orphan_league_ids}})
        deletions["waiver_budgets"] += r.deleted_count or 0
        r = await db.team_invites.delete_many({"league_id": {"$in": orphan_league_ids}})
        deletions["team_invites"] += r.deleted_count or 0
        r = await db.league_invites.delete_many({"league_id": {"$in": orphan_league_ids}})
        deletions["league_invites"] += r.deleted_count or 0
        r = await db.leagues.delete_many({"_id": {"$in": [ObjectId(li) for li in orphan_league_ids]}})
        deletions["leagues"] += r.deleted_count or 0

    real_league_ids = set()
    async for lg in db.leagues.find({}, {"_id": 1}):
        real_league_ids.add(str(lg["_id"]))
    orphan_team_ids: List[str] = []
    async for t in db.teams.find({}, {"league_id": 1}):
        lid = t.get("league_id")
        if lid and lid not in real_league_ids:
            orphan_team_ids.append(t["_id"])
    if orphan_team_ids:
        r = await db.teams.delete_many({"_id": {"$in": orphan_team_ids}})
        deletions["teams"] += r.deleted_count or 0

    return deletions

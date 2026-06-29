"""Iter 231ah — Prospect backfill + TTL + module relocation tests.

Coverage:
  1. Prospect backfill — synthetic NHL ID generator is collision-free
     across the 2020-2025 picks. Normalizer produces the canonical
     schema. Idempotent upsert (re-running doesn't duplicate).
  2. Routes — `POST /admin/prospects/backfill` and
     `GET /admin/prospects/stats` exist and are platform-admin gated.
  3. Module relocation — `admin-managed` endpoint moved from
     `team_invites.py` to `teams_admin.py`. URL path unchanged.
  4. TTL index — `draft_restart_log` collection has a 90-day TTL on
     `restarted_at_ts`, and `restart_draft` writes that field.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


# ─── 1. Backfill — synthetic ID + normalizer ──────────────────────


def test_synthetic_nhl_id_collision_free():
    """Across 6 years × 250 picks/year = 1500 ids must all be distinct.
    Regression guard for the negative-id formula."""
    from services.prospect_backfill import _synthetic_nhl_id
    seen: set = set()
    for y in range(2020, 2026):
        for p in range(1, 251):
            sid = _synthetic_nhl_id(y, p)
            assert sid < 0, f"Must be negative (got {sid})"
            assert sid not in seen, f"Collision at year={y}, pick={p}"
            seen.add(sid)
    assert len(seen) == 6 * 250


def test_normalize_pick_schema():
    """Verify the normalizer maps all NHL API fields to our canonical
    `players` schema."""
    from services.prospect_backfill import _normalize_pick
    pick = {
        "firstName": {"default": "Matthew"},
        "lastName": {"default": "Schaefer"},
        "positionCode": "D",
        "overallPick": 1, "round": 1, "pickInRound": 1,
        "teamAbbrev": "NYI", "teamName": {"default": "New York Islanders"},
        "amateurClubName": "Erie", "amateurLeague": "OHL",
        "countryCode": "CAN", "height": 74, "weight": 186,
    }
    out = _normalize_pick(pick, 2025)
    assert out["name"] == "Matthew Schaefer"
    assert out["player_type"] == "prospect"
    assert out["player_status"] == "amateur"
    assert out["position"] == "D"
    assert out["team"] == "Erie"
    assert out["team_name"] == "OHL · Erie"
    assert out["amateur_league"] == "OHL"
    assert out["draft_year"] == 2025
    assert out["season"] == "2024-2025"
    assert out["draft_round"] == 1
    assert out["draft_pick_overall"] == 1
    assert out["drafted_by_team"] == "NYI"
    assert out["country_code"] == "CAN"
    assert out["height_inches"] == 74
    assert out["weight_lbs"] == 186
    assert out["seed_source"] == "nhl_draft_picks_api"
    assert out["nhl_id"] < 0  # synthetic


# ─── 2. Routes registered ─────────────────────────────────────────


def test_prospect_routes_exist():
    src = Path("/app/backend/routes/teams_admin.py").read_text()
    assert "/admin/prospects/backfill" in src
    assert "/admin/prospects/stats" in src
    assert "_is_platform_admin" in src
    # Both endpoints gated.
    assert src.count("Platform admin only") >= 2


def test_teams_admin_wired_in_server():
    src = Path("/app/backend/server.py").read_text()
    assert "teams_admin as teams_admin_routes" in src
    assert "teams_admin_routes.setup(_router_deps)" in src
    assert "api_router.include_router(teams_admin_routes.router)" in src


# ─── 3. Module relocation — admin-managed moved out ───────────────


def test_admin_managed_relocated():
    """The endpoint must now live in `teams_admin.py` and the OLD
    `team_invites.py` must NO LONGER define it (only a docstring
    pointer to the new location)."""
    new_src = Path("/app/backend/routes/teams_admin.py").read_text()
    old_src = Path("/app/backend/routes/team_invites.py").read_text()
    # New file has it.
    assert "/leagues/{league_id}/teams/{team_id}/admin-managed" in new_src
    assert "async def set_team_admin_managed" in new_src
    # Old file does NOT (relocated).
    assert "async def set_team_admin_managed" not in old_src
    assert 'class AdminManagedToggleRequest(BaseModel)' not in old_src
    # Old file has a forwarding comment for future maintainers.
    assert "routes/teams_admin.py" in old_src


# ─── 4. TTL index on draft_restart_log ────────────────────────────


def test_ttl_index_declared_in_server():
    src = Path("/app/backend/server.py").read_text()
    assert "draft_restart_log.create_index" in src
    assert "expireAfterSeconds" in src
    # 90 days = 90 * 24 * 60 * 60 seconds.
    assert "90 * 24 * 60 * 60" in src
    assert "restarted_at_ts" in src


def test_restart_draft_writes_ttl_field():
    """The TTL field `restarted_at_ts` must be a BSON Date (not an ISO
    string) for Mongo's TTL monitor to honour the expiry."""
    src = Path("/app/backend/routes/draft_admin.py").read_text()
    assert '"restarted_at_ts": now_dt' in src
    # Must be a datetime, not a string. Look for the datetime.now(...) ref.
    assert "now_dt = datetime.now(timezone.utc)" in src


# ─── 5. Functional: idempotent upsert ─────────────────────────────


@pytest.mark.asyncio
async def test_backfill_idempotent_upsert():
    """Backfill a single fake year twice — first run inserts, second
    only updates. No duplicate _ids."""
    db = _db()
    from services.prospect_backfill import _synthetic_nhl_id, _normalize_pick

    fake_year = 2099  # Far-future year so we don't collide with real data.
    pick = {
        "firstName": {"default": "iter231ah_test_first"},
        "lastName": {"default": "iter231ah_test_last"},
        "positionCode": "C",
        "overallPick": 1, "round": 1, "pickInRound": 1,
        "teamAbbrev": "XYZ", "teamName": {"default": "Test Team"},
        "amateurClubName": "Test Club", "amateurLeague": "TST",
    }
    doc = _normalize_pick(pick, fake_year)
    doc["_test_seed"] = True  # let conftest sweep us afterwards
    sid = doc["nhl_id"]
    try:
        # First insert.
        r1 = await db.players.update_one(
            {"nhl_id": sid}, {"$set": doc}, upsert=True
        )
        assert r1.upserted_id is not None
        # Second run — same payload, must NOT create a duplicate.
        r2 = await db.players.update_one(
            {"nhl_id": sid}, {"$set": doc}, upsert=True
        )
        assert r2.upserted_id is None  # no new insert
        count = await db.players.count_documents({"nhl_id": sid})
        assert count == 1, f"Idempotency broken — found {count} rows for nhl_id={sid}"
    finally:
        await db.players.delete_many({"nhl_id": sid})


@pytest.mark.asyncio
async def test_prospect_pool_has_full_6_year_classes():
    """Live verification: after the iter231ah backfill, the pool must
    contain rows from all 6 draft years (2020-2025)."""
    db = _db()
    years_present = set()
    async for row in db.players.aggregate([
        {"$match": {"player_type": "prospect", "draft_year": {"$ne": None}}},
        {"$group": {"_id": "$draft_year"}},
    ]):
        years_present.add(row["_id"])
    # Must cover at least 6 years.
    expected = {2020, 2021, 2022, 2023, 2024, 2025}
    missing = expected - years_present
    assert not missing, f"Prospect pool missing draft classes: {missing}"

"""Iter 231ar — Four follow-ups after iter 231aq:

  1. Recent Crashes admin tile.
  2. TFHL League Home matchups still showed "Open Slot N" rows after
     teams had been adopted. Schedules were generated when seats were
     still open; the matchup docs persisted the placeholder team_ids.
     Resolve them at read time (and back-fill TFHL once).
  3. League Administration → "Teams" tab showed `—` for every team's
     abbreviation. The endpoint read `t["abbreviation"]` but storage
     moved to `logo_abbr_override` long ago. Compute the derived
     abbreviation in the endpoint instead.
  4. Rename the sub-tab from "Teams" → "Team and Owner List" so the
     label matches what the panel actually exposes (the table of
     team + owner + invite-email rows).
"""
from tests.source_tree import read_source
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bson import ObjectId
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import league_invites as league_invites_routes  # noqa: E402
from routes import matchups as matchups_routes  # noqa: E402


# ── Frontend artefact guards ────────────────────────────────────────

ADMIN_DASH = Path("/app/frontend/src/lovable/pages/admin/AdminDashboard.tsx")
CRASHES_PANEL = Path("/app/frontend/src/lovable/pages/admin/components/RecentCrashesPanel.tsx")
LEAGUE_ADMIN_TAB = Path("/app/frontend/src/lovable/pages/commissioner/tabs/LeagueAdminTab.tsx")


def test_admin_dashboard_mounts_recent_crashes_tab():
    src = read_source(ADMIN_DASH)
    assert 'import RecentCrashesPanel from "./components/RecentCrashesPanel"' in src
    # Sidebar entry sits next to DB Hygiene as the user requested.
    assert 'value="crashes"' in src
    assert 'label="Recent Crashes"' in src
    assert 'testid="admin-tab-crashes"' in src
    # Content panel is wired to the new component.
    assert "<RecentCrashesPanel />" in src


def test_recent_crashes_panel_hits_admin_endpoint_with_limit_20():
    src = read_source(CRASHES_PANEL)
    # Newest 20 errors per the user's spec.
    assert 'api.get("/client-errors?limit=20")' in src
    # Refresh button + total count badge for at-a-glance triage.
    assert 'data-testid="admin-recent-crashes-refresh"' in src
    assert 'data-testid="admin-recent-crashes-total"' in src
    # Each row exposes a stable testid keyed on the crash id + a
    # toggle for the expanded stack/component-stack/breadcrumbs.
    assert "admin-recent-crashes-row-${r._id}" in src
    assert "admin-recent-crashes-row-${r._id}-toggle" in src
    # Empty-state copy + error-state copy are both data-testid'd so
    # the testing agent can drive both branches.
    assert 'data-testid="admin-recent-crashes-empty"' in src
    assert 'data-testid="admin-recent-crashes-error"' in src


def test_league_admin_subtab_renamed_to_team_and_owner_list():
    src = read_source(LEAGUE_ADMIN_TAB, include_imports=False)
    # New copy + stable testid.
    assert "Team and Owner List" in src
    assert 'data-testid="admin-sub-tab-team-owner-list"' in src
    # Old copy gone (would still be valid as part of the prop value,
    # which we leave alone, but the rendered label is replaced).
    assert ">Teams<" not in src
    assert "Teams\n        </TabsTrigger>" not in src


# ── Backend behaviour ────────────────────────────────────────────────

def _mk_team(league_id, name, pos, _id=None, owner_id=None, logo_override=None):
    return {
        "_id": _id or ObjectId(),
        "league_id": league_id,
        "name": name,
        "draft_position": pos,
        "owner_id": owner_id,
        "owner_name": "owner-" + (name or "x") if owner_id else None,
        "logo_abbr_override": logo_override,
        "created_at": datetime.now(timezone.utc),
    }


async def _seed_league(db, league_id, commissioner_id):
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "Test League",
        "commissioner_id": commissioner_id,
        "max_teams": 4,
    })


@pytest.mark.asyncio
async def test_matchups_resolve_open_slot_to_claimed_team():
    """Schedules generated when seats are open store
    `home_team_id='open_slot_N'`. Once a team is seeded at
    `draft_position=N`, the response must overlay the real id + name —
    no migration / re-generation required."""
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"], maxPoolSize=1)
    dbname = f"dynasty_test_matchresolve_{uuid.uuid4().hex[:8]}"
    db = mongo[dbname]
    try:
        league_id = str(ObjectId())
        commish = str(ObjectId())
        await _seed_league(db, league_id, commish)
        # Three seats: 1 claimed (Houston Aeros @ pos 3), 1 still
        # unclaimed (pos 5 = no team row yet), 1 with a real team
        # but no draft_position (Hamilton Coyotes).
        houston_id = ObjectId()
        await db.teams.insert_one(_mk_team(
            league_id, "Houston Aeros", 3, _id=houston_id,
            owner_id="u1", logo_override="HOU",
        ))
        # Original matchup row references the placeholder.
        await db.matchups.insert_one({
            "league_id": league_id,
            "week": 1,
            "home_team_id": "open_slot_3",
            "home_team_name": "Open Slot 3",
            "away_team_id": "open_slot_5",
            "away_team_name": "Open Slot 5",
            "status": "scheduled",
        })

        async def fake_get_user(_request):
            return {"_id": commish, "email": "commish@example.test"}
        matchups_routes.setup({"db": db, "logger": None, "get_current_user": fake_get_user})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(matchups_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/api/matchups/{league_id}")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        row = rows[0]
        # Claimed seat gets the real team's id + name.
        assert row["home_team_id"] == str(houston_id)
        assert row["home_team_name"] == "Houston Aeros"
        # Unclaimed seat stays as the placeholder so the UI can keep
        # rendering "Open Slot 5".
        assert row["away_team_id"] == "open_slot_5"
        assert row["away_team_name"] == "Open Slot 5"
    finally:
        await mongo.drop_database(dbname)
        mongo.close()


@pytest.mark.asyncio
async def test_pending_team_invites_returns_derived_abbreviation():
    """The endpoint must compute the abbreviation from
    `logo_abbr_override` first, then auto-derive from the team name.
    Reading the legacy `abbreviation` field returned `None` for every
    team because storage migrated to `logo_abbr_override` long ago."""
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"], maxPoolSize=1)
    dbname = f"dynasty_test_abbr_{uuid.uuid4().hex[:8]}"
    db = mongo[dbname]
    try:
        league_id = str(ObjectId())
        commish_id = "test_user_0001"
        await _seed_league(db, league_id, commish_id)

        async def fake_get_user(_request):
            return {"_id": commish_id, "email": "c@example.com"}

        # 3 teams: explicit override, multi-word auto, single-word auto.
        await db.teams.insert_many([
            _mk_team(league_id, "Houston Aeros", 1, owner_id="u1", logo_override="HOU"),
            _mk_team(league_id, "Toronto Singularity", 2, owner_id="u2"),  # no override
            _mk_team(league_id, "Vipers", 3, owner_id="u3"),  # single-word
        ])

        league_invites_routes.setup({"db": db, "get_current_user": fake_get_user})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(league_invites_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/api/leagues/{league_id}/pending-team-invites")
        assert r.status_code == 200, r.text
        teams = {t["team_name"]: t for t in r.json()["teams"] if t["team_name"]}
        assert teams["Houston Aeros"]["abbreviation"] == "HOU"
        assert teams["Toronto Singularity"]["abbreviation"] == "TS"
        assert teams["Vipers"]["abbreviation"] == "VIP"
    finally:
        await mongo.drop_database(dbname)
        mongo.close()


@pytest.mark.asyncio
async def test_pending_team_invites_blanks_abbr_for_unclaimed_open_slot():
    """Open Slot N rows (auto-seeded with name=None) must NOT make up
    an abbreviation — they should report `None` so the UI shows a
    dash. Otherwise we'd return weird strings like `None`.upper() →
    `"NON"` and confuse the commissioner."""
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"], maxPoolSize=1)
    dbname = f"dynasty_test_abbrunclaimed_{uuid.uuid4().hex[:8]}"
    db = mongo[dbname]
    try:
        league_id = str(ObjectId())
        commish_id = "test_user_0001"
        await _seed_league(db, league_id, commish_id)

        async def fake_get_user(_request):
            return {"_id": commish_id, "email": "c@example.com"}

        await db.teams.insert_one({
            "_id": ObjectId(),
            "league_id": league_id,
            "name": None,
            "draft_position": 7,
            "owner_id": None,
            "logo_abbr_override": None,
            "created_by_auto_seed": True,
        })

        league_invites_routes.setup({"db": db, "get_current_user": fake_get_user})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(league_invites_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/api/leagues/{league_id}/pending-team-invites")
        assert r.status_code == 200
        teams = r.json()["teams"]
        # max_teams=4 → endpoint auto-seeds the remaining 3 + our 1 row = 4.
        assert len(teams) == 4
        for t in teams:
            assert t["team_name"] is None
            assert t["abbreviation"] is None
    finally:
        await mongo.drop_database(dbname)
        mongo.close()

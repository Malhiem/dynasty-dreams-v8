"""Focused unit tests for `routes/contracts.py`.

Each test runs against an ephemeral test database created + dropped per
test. No shared state with the live dev DB → zero pollution risk, sub-second
execution.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import contracts as contracts_routes  # noqa: E402

from tests.router_test_utils import (  # noqa: E402
    isolated_router_app,
    seed_league,
    seed_player,
    seed_team,
)


@pytest.mark.asyncio
async def test_get_contracts_empty_returns_empty_list():
    async with isolated_router_app(contracts_routes) as ctx:
        league_id = await seed_league(ctx.db)
        r = await ctx.client.get(f"/api/contracts?league_id={league_id}")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_create_contract_persists_and_returns_payload():
    async with isolated_router_app(contracts_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db, name="McDavid")

        r = await ctx.client.post("/api/contracts", json={
            "league_id": league_id,
            "team_id": team_id,
            "player_id": player_id,
            "aav": 12_500_000,
            "total_value": 100_000_000,
            "signing_bonus": 0,
            "years": 8,
            "start_year": 2025,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player_name"] == "McDavid"
        assert body["aav"] == 12_500_000
        assert body["years"] == 8
        # Free-agency year is derived from start_year + years (terminator
        # column for the cap-hit roster view).
        assert body["free_agency_year"] == 2025 + 8

        # Inserted row exists in the test DB
        count = await ctx.db.contracts.count_documents({"league_id": league_id})
        assert count == 1


@pytest.mark.asyncio
async def test_create_contract_blocked_when_over_cap():
    async with isolated_router_app(contracts_routes) as ctx:
        league_id = await seed_league(ctx.db, salary_cap_enabled=True, salary_cap=10_000_000)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db)

        r = await ctx.client.post("/api/contracts", json={
            "league_id": league_id,
            "team_id": team_id,
            "player_id": player_id,
            "aav": 15_000_000,  # Exceeds the $10M cap on a fresh team.
            "total_value": 15_000_000,
            "years": 1,
            "start_year": 2025,
        })
        assert r.status_code == 400
        assert "salary cap" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_contract_404_when_team_missing():
    async with isolated_router_app(contracts_routes) as ctx:
        league_id = await seed_league(ctx.db)
        player_id = await seed_player(ctx.db)

        r = await ctx.client.post("/api/contracts", json={
            "league_id": league_id,
            "team_id": "69d111111111111111111111",  # Non-existent.
            "player_id": player_id,
            "aav": 1_000_000,
            "total_value": 1_000_000,
            "years": 1,
            "start_year": 2025,
        })
        assert r.status_code == 404
        assert "team" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_contract_blocked_for_non_commissioner():
    """Only the league commissioner can edit contracts."""
    async with isolated_router_app(
        contracts_routes,
        user={"_id": "other_user", "id": "other_user", "name": "Other"},
    ) as ctx:
        league_id = await seed_league(ctx.db, commissioner_id="commish_only")
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db)
        ins = await ctx.db.contracts.insert_one({
            "league_id": league_id, "team_id": team_id, "player_id": player_id,
            "aav": 1_000_000, "status": "active",
        })
        r = await ctx.client.put(
            f"/api/contracts/{ins.inserted_id}", json={"aav": 2_000_000},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_salary_cap_overview_sums_active_contracts():
    """`get_team_cap_used` sums `db.contracts.aav` for active rows."""
    async with isolated_router_app(contracts_routes) as ctx:
        league_id = await seed_league(ctx.db, salary_cap_enabled=True, salary_cap=80_000_000)
        team_id = await seed_team(ctx.db, league_id=league_id)
        p1 = await seed_player(ctx.db)
        p2 = await seed_player(ctx.db)
        await ctx.db.contracts.insert_many([
            {"player_id": p1, "league_id": league_id, "team_id": team_id, "aav": 5_000_000, "status": "active", "player_status": "rfa"},
            {"player_id": p2, "league_id": league_id, "team_id": team_id, "aav": 8_000_000, "status": "active", "player_status": "ufa"},
            # Expired rows must NOT count toward cap usage.
            {"league_id": league_id, "team_id": team_id, "aav": 99_000_000, "status": "expired"},
        ])
        r = await ctx.client.get(f"/api/salary-cap/{league_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["salary_cap"] == 80_000_000
        team_row = next(t for t in body["teams"] if t["team_id"] == team_id)
        assert team_row["cap_used"] == 13_000_000  # 5 + 8, not 5 + 8 + 99
        assert team_row["active_contracts"] == 2
        assert team_row["rfa_count"] == 1
        assert team_row["ufa_count"] == 1


@pytest.mark.asyncio
async def test_expiring_contracts_filters_by_free_agency_year():
    async with isolated_router_app(contracts_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        await ctx.db.contracts.insert_many([
            {"league_id": league_id, "team_id": team_id, "aav": 1_000_000,
             "status": "active", "free_agency_year": 2026, "player_name": "Expires 2026"},
            {"league_id": league_id, "team_id": team_id, "aav": 5_000_000,
             "status": "active", "free_agency_year": 2027, "player_name": "Expires 2027"},
        ])
        r = await ctx.client.get(f"/api/salary-cap/{league_id}/expiring?year=2026")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["player_name"] == "Expires 2026"

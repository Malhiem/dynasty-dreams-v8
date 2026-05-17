"""Focused unit tests for `routes/waivers.py`.

Covers the precheck endpoint introduced in iter 91 (roster/cap/FAAB
blockers, `requires_drop` flag, illegal-placement warnings) plus the
core claim lifecycle (place / cancel) against an ephemeral test db.

The waiver-process endpoint is covered by the existing integration tests
(`test_iteration*`) — too large a surface for a focused router unit test.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import waivers as waivers_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


# ─── Fixtures ────────────────────────────────────────────────────


async def _seed_league(
    db,
    *,
    commissioner_id="test_user_0001",
    salary_cap_enabled=False,
    salary_cap=82_500_000,
    roster_size=23,
    faab=100,
):
    res = await db.leagues.insert_one({
        "name": "Waiver Test League",
        "commissioner_id": commissioner_id,
        "salary_cap_enabled": salary_cap_enabled,
        "salary_cap": salary_cap,
        "roster_size": roster_size,
        "waiver_faab_budget": faab,
        "waiver_period_days": 1,
    })
    return str(res.inserted_id)


async def _seed_team(db, *, league_id, owner_id="test_user_0001", roster=None, lineup=None, salary_used=0):
    res = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": owner_id,
        "owner_name": "Owner",
        "name": "Test Team",
        "roster": roster or [],
        "lineup": lineup or {},
        "salary_used": salary_used,
    })
    return str(res.inserted_id)


async def _seed_player(db, *, name="Connor", position="C", points=85, games_played=40, player_type=None, **extra):
    doc = {
        "name": name, "position": position,
        "team": "EDM", "team_name": "Edmonton",
        "points": points, "goals": int(points * 0.4),
        "assists": int(points * 0.6), "games_played": games_played,
        "player_type": player_type or ("goalie" if position == "G" else "skater"),
    }
    doc.update(extra)
    res = await db.players.insert_one(doc)
    return str(res.inserted_id)


# ─── /waivers/precheck ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_precheck_happy_path_no_blockers():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db, roster_size=23)
        await _seed_team(ctx.db, league_id=league_id, roster=[])
        pid = await _seed_player(ctx.db, points=85)
        r = await ctx.client.get(
            "/api/waivers/precheck",
            params={"league_id": league_id, "player_id": pid, "bid_amount": 5},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["can_claim"] is True
        assert body["requires_drop"] is False
        assert body["roster"]["has_room"] is True
        assert body["cap"]["enabled"] is False
        assert [iss for iss in body["issues"] if iss.get("severity") == "error"] == []


@pytest.mark.asyncio
async def test_precheck_blocks_when_roster_full():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db, roster_size=2)
        # 2 existing players → roster at max
        existing = [
            await _seed_player(ctx.db, name="P1", points=40),
            await _seed_player(ctx.db, name="P2", points=40),
        ]
        await _seed_team(ctx.db, league_id=league_id, roster=existing)
        target = await _seed_player(ctx.db, name="Target", points=80)
        r = await ctx.client.get(
            "/api/waivers/precheck",
            params={"league_id": league_id, "player_id": target, "bid_amount": 1},
        )
        body = r.json()
        assert body["can_claim"] is False
        assert body["requires_drop"] is True
        assert body["roster"]["has_room"] is False
        codes = [iss["code"] for iss in body["issues"]]
        assert "no_roster_space" in codes


@pytest.mark.asyncio
async def test_precheck_blocks_when_cap_exceeded():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(
            ctx.db, salary_cap_enabled=True, salary_cap=10_000_000, roster_size=23,
        )
        # Used $9M already; adding a star will blow past the $10M cap.
        await _seed_team(ctx.db, league_id=league_id, salary_used=9_000_000)
        # Star (100+ pts) → synthesized salary ≥ $11M
        target = await _seed_player(ctx.db, points=110)
        r = await ctx.client.get(
            "/api/waivers/precheck",
            params={"league_id": league_id, "player_id": target, "bid_amount": 1},
        )
        body = r.json()
        assert body["can_claim"] is False
        assert body["requires_drop"] is True
        assert body["cap"]["fits"] is False
        codes = [iss["code"] for iss in body["issues"]]
        assert "insufficient_cap" in codes


@pytest.mark.asyncio
async def test_precheck_blocks_when_faab_overdraft():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db, faab=50)
        team_id = await _seed_team(ctx.db, league_id=league_id)
        # Bid more than the league default FAAB budget
        target = await _seed_player(ctx.db)
        r = await ctx.client.get(
            "/api/waivers/precheck",
            params={"league_id": league_id, "player_id": target, "bid_amount": 999},
        )
        body = r.json()
        assert body["can_claim"] is False
        codes = [iss["code"] for iss in body["issues"]]
        assert "insufficient_faab" in codes


@pytest.mark.asyncio
async def test_precheck_403_when_user_has_no_team_in_league():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        # Team owned by someone else
        await _seed_team(ctx.db, league_id=league_id, owner_id="other_user")
        target = await _seed_player(ctx.db)
        r = await ctx.client.get(
            "/api/waivers/precheck",
            params={"league_id": league_id, "player_id": target},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_precheck_404_when_player_missing():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id)
        r = await ctx.client.get(
            "/api/waivers/precheck",
            params={"league_id": league_id, "player_id": str(ObjectId())},
        )
        assert r.status_code == 404


# ─── /waivers/claim ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_place_claim_creates_pending_row():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id)
        pid = await _seed_player(ctx.db, name="McDavid")
        r = await ctx.client.post(
            "/api/waivers/claim",
            json={"league_id": league_id, "player_id": pid, "bid_amount": 12},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["player_name"] == "McDavid"
        assert body["bid_amount"] == 12
        # FAAB budget should have been auto-created at the league default
        budget = await ctx.db.waiver_budgets.find_one({"league_id": league_id})
        assert budget is not None
        assert budget["remaining"] == 100  # not deducted until process runs


@pytest.mark.asyncio
async def test_place_claim_rejects_duplicate_pending():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id)
        pid = await _seed_player(ctx.db)
        r1 = await ctx.client.post(
            "/api/waivers/claim",
            json={"league_id": league_id, "player_id": pid, "bid_amount": 5},
        )
        assert r1.status_code == 200
        r2 = await ctx.client.post(
            "/api/waivers/claim",
            json={"league_id": league_id, "player_id": pid, "bid_amount": 6},
        )
        assert r2.status_code == 400
        assert "pending claim" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_place_claim_rejects_bid_above_faab():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db, faab=20)
        await _seed_team(ctx.db, league_id=league_id)
        pid = await _seed_player(ctx.db)
        r = await ctx.client.post(
            "/api/waivers/claim",
            json={"league_id": league_id, "player_id": pid, "bid_amount": 9999},
        )
        assert r.status_code == 400


# ─── /waivers/claims/{id} (cancel) ───────────────────────────────


@pytest.mark.asyncio
async def test_cancel_own_pending_claim():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id)
        pid = await _seed_player(ctx.db)
        place = await ctx.client.post(
            "/api/waivers/claim",
            json={"league_id": league_id, "player_id": pid, "bid_amount": 4},
        )
        claim_id = place.json()["_id"]
        r = await ctx.client.delete(f"/api/waivers/claims/{claim_id}")
        assert r.status_code == 200
        doc = await ctx.db.waiver_claims.find_one({"_id": ObjectId(claim_id)})
        assert doc["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_someone_elses_claim_403():
    async with isolated_router_app(waivers_routes) as ctx:
        # Insert a claim owned by another user directly
        res = await ctx.db.waiver_claims.insert_one({
            "league_id": "L",
            "team_id": "T",
            "team_name": "Other",
            "owner_id": "other_user",
            "player_id": "P",
            "player_name": "X",
            "bid_amount": 1,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        r = await ctx.client.delete(f"/api/waivers/claims/{res.inserted_id}")
        assert r.status_code == 403


# ─── /waivers/budget ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_budget_initializes_at_league_default():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db, faab=250)
        await _seed_team(ctx.db, league_id=league_id)
        r = await ctx.client.get(f"/api/waivers/budget?league_id={league_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["total_budget"] == 250
        assert body["remaining"] == 250
        assert body["spent"] == 0


# ─── /waivers/order ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_waiver_order_is_inverse_of_record():
    async with isolated_router_app(waivers_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        # Worst team first (rank 1)
        await ctx.db.teams.insert_many([
            {"league_id": league_id, "owner_id": "u1", "owner_name": "U1",
             "name": "Best",  "wins": 10, "points_for": 800},
            {"league_id": league_id, "owner_id": "u2", "owner_name": "U2",
             "name": "Mid",   "wins": 5,  "points_for": 500},
            {"league_id": league_id, "owner_id": "u3", "owner_name": "U3",
             "name": "Worst", "wins": 1,  "points_for": 100},
        ])
        r = await ctx.client.get(f"/api/waivers/order?league_id={league_id}")
        order = r.json()
        names = [row["team_name"] for row in order]
        assert names == ["Worst", "Mid", "Best"]

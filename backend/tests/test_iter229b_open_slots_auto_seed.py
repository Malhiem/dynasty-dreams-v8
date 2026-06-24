"""Iter 229b — GET /pending-team-invites auto-seeds missing slots.

User-reported gap: TFHL had `max_teams=24` but only 1 team doc in the
`teams` collection, so the Teams & Owners panel only showed 1 row. The
commissioner expected 23 Open Slots so they could mint invites against
each seat.

This test certifies that calling the endpoint:
  • Inserts the missing 23 stubs (one per `draft_position` 2..24).
  • Keeps the existing claimed team unchanged.
  • Is idempotent — a second call doesn't double-seed.
"""
from __future__ import annotations

import pytest
from bson import ObjectId

from routes import league_invites as league_invites_routes
from tests.router_test_utils import isolated_router_app


COMM = {"_id": "comm_001", "id": "comm_001", "name": "Comm One", "email": "comm@example.com"}


@pytest.mark.asyncio
async def test_pending_invites_auto_seeds_missing_slots_to_max_teams():
    async with isolated_router_app(league_invites_routes, user=COMM) as ctx:
        lres = await ctx.db.leagues.insert_one({
            "name": "TFHL",
            "commissioner_id": COMM["_id"],
            "max_teams": 24,
            "current_teams": 1,
        })
        league_id = str(lres.inserted_id)
        # Seed only one claimed team (matches TFHL's actual state).
        await ctx.db.teams.insert_one({
            "league_id": league_id,
            "name": "Hamilton Coyotes",
            "owner_id": "user_chriszarek",
            "owner_name": "chriszarek1",
            "draft_position": 1,
            "is_pending": False,
        })

        r = await ctx.client.get(f"/api/leagues/{league_id}/pending-team-invites")
        assert r.status_code == 200, r.text
        body = r.json()
        teams = body["teams"]
        assert len(teams) == 24, f"expected 24 seats, got {len(teams)}"
        # First row is the claimed Hamilton Coyotes (draft_position 1).
        assert teams[0]["team_name"] == "Hamilton Coyotes"
        assert teams[0]["owner_id"] == "user_chriszarek"
        # Subsequent rows are Open Slots with sequential draft_position.
        for idx, row in enumerate(teams[1:], start=2):
            assert row["owner_id"] is None
            assert row["is_pending"] is True
            assert row["draft_position"] == idx
            assert row["team_name"] is None  # rendered as "Open Slot N" by frontend

        # Idempotency — second call doesn't create duplicates.
        r2 = await ctx.client.get(f"/api/leagues/{league_id}/pending-team-invites")
        assert r2.status_code == 200
        assert len(r2.json()["teams"]) == 24
        # And the DB collection only has 24 docs.
        total_in_db = await ctx.db.teams.count_documents({"league_id": league_id})
        assert total_in_db == 24


@pytest.mark.asyncio
async def test_pending_invites_does_not_pad_when_already_at_max():
    """A league already at max_teams shouldn't have any new docs created."""
    async with isolated_router_app(league_invites_routes, user=COMM) as ctx:
        lres = await ctx.db.leagues.insert_one({
            "name": "Full League",
            "commissioner_id": COMM["_id"],
            "max_teams": 3,
        })
        league_id = str(lres.inserted_id)
        for i in range(1, 4):
            await ctx.db.teams.insert_one({
                "league_id": league_id,
                "name": f"Team {i}",
                "owner_id": f"user_{i}",
                "draft_position": i,
            })

        r = await ctx.client.get(f"/api/leagues/{league_id}/pending-team-invites")
        assert r.status_code == 200
        assert len(r.json()["teams"]) == 3
        total_in_db = await ctx.db.teams.count_documents({"league_id": league_id})
        assert total_in_db == 3


@pytest.mark.asyncio
async def test_pending_invites_fills_gaps_in_draft_position():
    """When non-contiguous draft positions are already used (e.g. 1, 5, 10),
    the auto-seed should fill the remaining 1..max_teams positions."""
    async with isolated_router_app(league_invites_routes, user=COMM) as ctx:
        lres = await ctx.db.leagues.insert_one({
            "name": "Sparse League",
            "commissioner_id": COMM["_id"],
            "max_teams": 6,
        })
        league_id = str(lres.inserted_id)
        # Seed positions 1, 3, 5 — gaps at 2, 4, 6.
        for pos in (1, 3, 5):
            await ctx.db.teams.insert_one({
                "league_id": league_id,
                "name": f"Team {pos}",
                "owner_id": f"user_{pos}",
                "draft_position": pos,
            })
        r = await ctx.client.get(f"/api/leagues/{league_id}/pending-team-invites")
        body = r.json()
        assert len(body["teams"]) == 6
        positions = sorted(t["draft_position"] for t in body["teams"])
        assert positions == [1, 2, 3, 4, 5, 6]

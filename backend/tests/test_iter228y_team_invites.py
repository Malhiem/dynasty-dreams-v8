"""Iter 228y — slot-locked team invite tokens (private league flow).

Covers happy paths + the guardrails the user asked for:
  • Commissioner mints owner / co_owner invites.
  • Email-locked invites reject the wrong user.
  • Single-use semantics — a token can't be redeemed twice.
  • Co-owners support — multiple users can join one team.
  • Revoke + expired states reject acceptance.
  • Listing endpoint filters used invites unless `include_used=true`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from routes import team_invites as team_invites_routes

from tests.router_test_utils import isolated_router_app


COMM = {"_id": "comm_001", "id": "comm_001", "name": "Comm One", "email": "comm@example.com"}
ALICE = {"_id": "alice_001", "id": "alice_001", "name": "Alice", "email": "alice@example.com"}
BOB = {"_id": "bob_001", "id": "bob_001", "name": "Bob", "email": "bob@example.com"}


async def _seed(db, *, commissioner_id="comm_001", current_teams=0):
    lres = await db.leagues.insert_one({
        "name": "TFHL",
        "commissioner_id": commissioner_id,
        "co_commissioners": [],
        "max_teams": 24,
        "current_teams": current_teams,
    })
    league_id = str(lres.inserted_id)
    tres = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": None,
        "name": "Frost Zone",
        "is_pending": True,
    })
    team_id = str(tres.inserted_id)
    return league_id, team_id


@pytest.mark.asyncio
async def test_commissioner_creates_owner_invite_and_user_accepts():
    async with isolated_router_app(team_invites_routes, user=COMM) as ctx:
        league_id, team_id = await _seed(ctx.db)
        # Commissioner mints an email-locked owner invite for Alice.
        r = await ctx.client.post(
            f"/api/leagues/{league_id}/teams/{team_id}/invites",
            json={"email": "alice@example.com", "role": "owner"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        token = body["token"]
        assert body["status"] == "pending"
        assert body["role"] == "owner"
        assert body["email"] == "alice@example.com"
        assert body["invite_url"].endswith(f"/team-invites/{token}")

    # Now swap to Alice's identity and accept.
    async with isolated_router_app(team_invites_routes, user=ALICE) as ctx2:
        # Re-seed identical league/team since each ctx uses a fresh DB.
        league_id2, team_id2 = await _seed(ctx2.db)
        await ctx2.db.team_invites.insert_one({
            "token": "alice_token",
            "league_id": league_id2,
            "team_id": team_id2,
            "email": "alice@example.com",
            "role": "owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "used_at": None,
            "used_by_user_id": None,
            "revoked_at": None,
        })
        r = await ctx2.client.post("/api/team-invites/alice_token/accept")
        assert r.status_code == 200, r.text
        team = await ctx2.db.teams.find_one({"_id": ObjectId(team_id2)})
        assert team["owner_id"] == ALICE["_id"]
        assert team["owner_name"] == ALICE["name"]
        assert team.get("is_pending") is False
        # league.current_teams bumped from 0 → 1
        league = await ctx2.db.leagues.find_one({"_id": ObjectId(league_id2)})
        assert league["current_teams"] == 1
        inv = await ctx2.db.team_invites.find_one({"token": "alice_token"})
        assert inv["used_by_user_id"] == ALICE["_id"]


@pytest.mark.asyncio
async def test_email_locked_invite_rejects_wrong_user():
    """Bob can't redeem an invite locked to alice@example.com."""
    async with isolated_router_app(team_invites_routes, user=BOB) as ctx:
        league_id, team_id = await _seed(ctx.db)
        await ctx.db.team_invites.insert_one({
            "token": "alice_only",
            "league_id": league_id,
            "team_id": team_id,
            "email": "alice@example.com",
            "role": "owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "used_at": None, "used_by_user_id": None, "revoked_at": None,
        })
        r = await ctx.client.post("/api/team-invites/alice_only/accept")
        assert r.status_code == 403
        assert "alice@example.com" in r.json()["detail"]


@pytest.mark.asyncio
async def test_invite_is_single_use():
    """A token can be redeemed exactly once."""
    async with isolated_router_app(team_invites_routes, user=ALICE) as ctx:
        league_id, team_id = await _seed(ctx.db)
        await ctx.db.team_invites.insert_one({
            "token": "once_only",
            "league_id": league_id,
            "team_id": team_id,
            "email": None,
            "role": "owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "used_at": None, "used_by_user_id": None, "revoked_at": None,
        })
        r1 = await ctx.client.post("/api/team-invites/once_only/accept")
        assert r1.status_code == 200, r1.text
        # Second attempt: invite is now "accepted".
        r2 = await ctx.client.post("/api/team-invites/once_only/accept")
        assert r2.status_code == 400
        assert "accepted" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_co_owner_invite_appends_to_co_owner_ids():
    """Multiple users can join one team via co_owner invites."""
    async with isolated_router_app(team_invites_routes, user=BOB) as ctx:
        league_id, team_id = await _seed(ctx.db)
        # Pre-set Alice as the primary owner.
        await ctx.db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {"$set": {"owner_id": ALICE["_id"], "owner_name": ALICE["name"]}},
        )
        await ctx.db.team_invites.insert_one({
            "token": "bob_co",
            "league_id": league_id,
            "team_id": team_id,
            "email": "bob@example.com",
            "role": "co_owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "used_at": None, "used_by_user_id": None, "revoked_at": None,
        })
        r = await ctx.client.post("/api/team-invites/bob_co/accept")
        assert r.status_code == 200, r.text
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        # Alice still primary; Bob is in the co-owner list.
        assert team["owner_id"] == ALICE["_id"]
        assert BOB["_id"] in team["co_owner_ids"]


@pytest.mark.asyncio
async def test_co_owner_double_join_rejected():
    """User can't be appended as a co-owner twice."""
    async with isolated_router_app(team_invites_routes, user=BOB) as ctx:
        league_id, team_id = await _seed(ctx.db)
        await ctx.db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {"$set": {
                "owner_id": ALICE["_id"],
                "owner_name": ALICE["name"],
                "co_owner_ids": [BOB["_id"]],
            }},
        )
        await ctx.db.team_invites.insert_one({
            "token": "bob_again",
            "league_id": league_id,
            "team_id": team_id,
            "email": None,
            "role": "co_owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "used_at": None, "used_by_user_id": None, "revoked_at": None,
        })
        r = await ctx.client.post("/api/team-invites/bob_again/accept")
        assert r.status_code == 400
        assert "already a co-owner" in r.json()["detail"]


@pytest.mark.asyncio
async def test_owner_invite_blocked_when_team_already_owned():
    """Commissioner can't mint a *new owner* invite for a team that has one."""
    async with isolated_router_app(team_invites_routes, user=COMM) as ctx:
        league_id, team_id = await _seed(ctx.db)
        await ctx.db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {"$set": {"owner_id": ALICE["_id"], "owner_name": ALICE["name"]}},
        )
        r = await ctx.client.post(
            f"/api/leagues/{league_id}/teams/{team_id}/invites",
            json={"role": "owner"},
        )
        assert r.status_code == 400
        assert "co_owner" in r.json()["detail"]


@pytest.mark.asyncio
async def test_revoke_invite_blocks_future_accept():
    async with isolated_router_app(team_invites_routes, user=COMM) as ctx:
        league_id, team_id = await _seed(ctx.db)
        # Mint
        m = await ctx.client.post(
            f"/api/leagues/{league_id}/teams/{team_id}/invites",
            json={"role": "owner"},
        )
        invite_id = m.json()["id"]
        token = m.json()["token"]
        # Revoke
        r = await ctx.client.delete(f"/api/team-invites/{invite_id}")
        assert r.status_code == 200
        # Preview still works but reports revoked
        p = await ctx.client.get(f"/api/team-invites/{token}/preview")
        assert p.json()["status"] == "revoked"

    # Try to accept revoked invite (Alice)
    async with isolated_router_app(team_invites_routes, user=ALICE) as ctx2:
        league_id2, team_id2 = await _seed(ctx2.db)
        await ctx2.db.team_invites.insert_one({
            "token": "revoked_token",
            "league_id": league_id2,
            "team_id": team_id2,
            "email": None,
            "role": "owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "used_at": None, "used_by_user_id": None,
            "revoked_at": datetime.now(timezone.utc),
        })
        r = await ctx2.client.post("/api/team-invites/revoked_token/accept")
        assert r.status_code == 400
        assert "revoked" in r.json()["detail"]


@pytest.mark.asyncio
async def test_expired_invite_rejected():
    async with isolated_router_app(team_invites_routes, user=ALICE) as ctx:
        league_id, team_id = await _seed(ctx.db)
        await ctx.db.team_invites.insert_one({
            "token": "stale_token",
            "league_id": league_id,
            "team_id": team_id,
            "email": None,
            "role": "owner",
            "created_by": COMM["_id"],
            "created_at": datetime.now(timezone.utc) - timedelta(days=20),
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
            "used_at": None, "used_by_user_id": None, "revoked_at": None,
        })
        r = await ctx.client.post("/api/team-invites/stale_token/accept")
        assert r.status_code == 400
        assert "expired" in r.json()["detail"]


@pytest.mark.asyncio
async def test_list_endpoint_filters_used_invites_by_default():
    async with isolated_router_app(team_invites_routes, user=COMM) as ctx:
        league_id, team_id = await _seed(ctx.db)
        now = datetime.now(timezone.utc)
        await ctx.db.team_invites.insert_many([
            {
                "token": "pending_t", "league_id": league_id, "team_id": team_id,
                "email": None, "role": "owner", "created_by": COMM["_id"],
                "created_at": now, "expires_at": now + timedelta(days=5),
                "used_at": None, "used_by_user_id": None, "revoked_at": None,
            },
            {
                "token": "accepted_t", "league_id": league_id, "team_id": team_id,
                "email": None, "role": "owner", "created_by": COMM["_id"],
                "created_at": now, "expires_at": now + timedelta(days=5),
                "used_at": now, "used_by_user_id": ALICE["_id"], "revoked_at": None,
            },
        ])
        # Default — accepted hidden.
        r = await ctx.client.get(f"/api/leagues/{league_id}/team-invites")
        body = r.json()
        tokens = [i["token"] for i in body["invites"]]
        assert "pending_t" in tokens
        assert "accepted_t" not in tokens

        # include_used=true — both surfaced.
        r2 = await ctx.client.get(
            f"/api/leagues/{league_id}/team-invites?include_used=true"
        )
        tokens2 = [i["token"] for i in r2.json()["invites"]]
        assert set(tokens2) == {"pending_t", "accepted_t"}


@pytest.mark.asyncio
async def test_non_commissioner_cannot_mint_invites():
    """Random user (Alice) hits the create endpoint — must be denied."""
    async with isolated_router_app(team_invites_routes, user=ALICE) as ctx:
        league_id, team_id = await _seed(ctx.db)  # commissioner is comm_001
        r = await ctx.client.post(
            f"/api/leagues/{league_id}/teams/{team_id}/invites",
            json={"role": "owner"},
        )
        assert r.status_code == 403

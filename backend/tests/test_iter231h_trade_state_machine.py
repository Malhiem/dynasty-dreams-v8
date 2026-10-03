"""Iter 231h — Trade state machine: proposed → accept/reject → pending → executed.

Guards the new recipient-response endpoint and the lifecycle changes:

  • POST /api/trades creates trades in `proposed` (NOT `pending`)
  • `processes_at` is null at creation — only stamped at acceptance
  • POST /api/trades/{id}/respond {action: accept|reject} works for the recipient
  • On accept: status → pending, processes_at = now + review_period_hours
  • On reject: status → rejected; notification fires to proposer
  • POST /api/trades/{id}/cancel works for the proposer
  • Only the recipient team's owner/co-owners may respond; only the proposer may cancel
  • /api/leagues/{id}/pending-trades surfaces both `proposed` and `pending`
"""
import os
import random
import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
pytestmark = pytest.mark.asyncio


async def _register(client, suffix):
    suf = f"{suffix}_{random.randint(10000, 99999)}"
    r = await client.post(
        "/api/auth/register",
        json={"username": f"u_{suf}", "email": f"u_{suf}@example.com", "password": "TestPass123!"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _setup_two_team_league(client):
    """Commissioner + a second team owner sharing one league."""
    token_a, uid_a = await _register(client, "h_propose")
    token_b, uid_b = await _register(client, "h_recipient")

    # Commissioner creates league.
    r = await client.post(
        "/api/leagues",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": f"TEST_Iter231h_{random.randint(10000, 99999)}",
            "season": "2026",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "roster_spots": 10,
        },
    )
    assert r.status_code == 200, r.text
    league_id = r.json()["id"]

    # Reassign one team to user B directly via MongoDB so we don't depend
    # on whatever join/invite endpoint exists.
    mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", os.environ["MONGO_URL"]))
    db = mongo[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    teams = await db.teams.find({"league_id": league_id}).to_list(20)
    assert len(teams) >= 1
    # The commissioner's auto-created team:
    team_a_id = str(teams[0]["_id"])
    # Create a second team owned by user B.
    team_b_id = str(ObjectId())
    await db.teams.insert_one({
        "_id": ObjectId(team_b_id),
        "league_id": league_id,
        "name": "Recipient FC",
        "logo_abbr": "RFC",
        "owner_id": uid_b,
    })
    mongo.close()

    return {
        "league_id": league_id,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "token_a": token_a,
        "token_b": token_b,
        "uid_a": uid_a,
        "uid_b": uid_b,
    }


async def test_proposal_starts_in_proposed_status_with_null_processes_at():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)

        r = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "test proposal",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "proposed", f"new trades must start in 'proposed' (got {body['status']})"
        assert body["processes_at"] is None, "processes_at must be null until recipient accepts"


async def test_recipient_can_accept_advances_to_pending():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "accept me",
            },
        )
        trade_id = r1.json()["_id"]

        # Recipient accepts.
        r2 = await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"action": "accept"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] == "pending"
        assert body["processes_at"] is not None, "processes_at must be stamped on accept"
        assert body["responded_at"] is not None


async def test_recipient_can_reject_with_reason():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "5", "pick_year": 2027}],
                "message": "bad deal",
            },
        )
        trade_id = r1.json()["_id"]

        r2 = await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"action": "reject", "reason": "Pick value mismatch"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] == "rejected"
        assert body["rejected_reason"] == "Pick value mismatch"


async def test_only_recipient_can_respond():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "x",
            },
        )
        trade_id = r1.json()["_id"]

        # Proposer trying to respond to their own trade → 403.
        r2 = await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={"action": "accept"},
        )
        assert r2.status_code == 403


async def test_cannot_respond_twice():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "x",
            },
        )
        trade_id = r1.json()["_id"]
        # Accept once.
        await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"action": "accept"},
        )
        # Accept again → 400 (no longer in proposed).
        r3 = await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"action": "accept"},
        )
        assert r3.status_code == 400


async def test_proposer_can_cancel_their_own_trade():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "x",
            },
        )
        trade_id = r1.json()["_id"]

        # Recipient cannot cancel.
        r2 = await client.post(
            f"/api/trades/{trade_id}/cancel",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        assert r2.status_code == 403

        # Proposer can cancel.
        r3 = await client.post(
            f"/api/trades/{trade_id}/cancel",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["status"] == "cancelled"


async def test_pending_trades_endpoint_includes_proposed():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "in-flight",
            },
        )

        r = await client.get(
            f"/api/leagues/{setup['league_id']}/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] >= 1
        statuses = [t["status"] for t in body["pending_trades"]]
        assert "proposed" in statuses, (
            f"pending-trades endpoint should surface proposed trades; got statuses={statuses}"
        )


async def test_notification_link_points_to_trade_detail_route():
    """The trade-proposed notification must deep-link to the specific
    trade so clicking it opens the proposal."""
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_two_team_league(client)
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={
                "league_id": setup["league_id"],
                "target_team_id": setup["team_b_id"],
                "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
                "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
                "message": "deep-link test",
            },
        )
        trade_id = r1.json()["_id"]

        # Recipient fetches their notifications and finds the proposal.
        r = await client.get(
            "/api/notifications",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        assert r.status_code == 200, r.text
        # Find the trade-proposed one.
        notifs = r.json() if isinstance(r.json(), list) else r.json().get("notifications", [])
        match = next(
            (n for n in notifs if "Trade Proposal" in (n.get("title") or "")),
            None,
        )
        assert match is not None, "trade-proposed notification should exist for the recipient"
        link = match.get("link") or match.get("action_url") or ""
        assert f"/transactions/trade/{trade_id}" in link, (
            f"notification link should deep-link to the trade; got {link!r}"
        )

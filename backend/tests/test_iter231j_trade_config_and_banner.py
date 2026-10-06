"""Iter 231j — Trade config enforcement + cross-league pending trades.

Guards:
  • Max trades per team (from transactions_config.trades.max_trades_per_team)
  • allow_before_draft / allow_during_draft draft-window gating
  • conditional_trades_enabled master toggle
  • GET /api/users/me/pending-trades returns the awaiting_response +
    in_review buckets the dashboard banner consumes.
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


async def _setup_league(client):
    """Two-user league with two teams, the second owned by user B."""
    token_a, uid_a = await _register(client, "j_propose")
    token_b, uid_b = await _register(client, "j_recipient")
    r = await client.post(
        "/api/leagues",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": f"TEST_Iter231j_{random.randint(10000, 99999)}",
            "season": "2026",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "roster_spots": 10,
        },
    )
    assert r.status_code == 200, r.text
    league_id = r.json()["id"]

    mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", os.environ["MONGO_URL"]))
    db = mongo[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    teams = await db.teams.find({"league_id": league_id}).to_list(20)
    team_a_id = str(teams[0]["_id"])
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


async def _set_trades_cfg(league_id, cfg_patch, *, status=None):
    """Direct-DB patch for the league's transactions_config.trades (+ optional
    league.status) so tests don't depend on the full Commissioner PUT flow."""
    mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", os.environ["MONGO_URL"]))
    db = mongo[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    update = {}
    for k, v in cfg_patch.items():
        update[f"transactions_config.trades.{k}"] = v
    if status is not None:
        update["status"] = status
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": update})
    mongo.close()


def _trade_payload(setup, **overrides):
    body = {
        "league_id": setup["league_id"],
        "target_team_id": setup["team_b_id"],
        "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
        "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
        "message": "iter231j test",
    }
    body.update(overrides)
    return body


# ─── Max trades per team ──────────────────────────────────────────


async def test_max_trades_per_team_caps_in_flight_proposals():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        await _set_trades_cfg(setup["league_id"], {"max_trades_per_team": 1})

        # First proposal succeeds.
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(setup),
        )
        assert r1.status_code == 200, r1.text

        # Second proposal between the same two teams must be rejected
        # because team_a (or team_b) already has 1 in-flight trade.
        r2 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(setup),
        )
        assert r2.status_code == 400
        assert "in-flight" in r2.json()["detail"]


async def test_unlimited_max_trades_when_unset():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        # No cfg patch — max_trades_per_team defaults to None (unlimited).
        for _ in range(3):
            r = await client.post(
                "/api/trades",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
                json=_trade_payload(setup),
            )
            assert r.status_code == 200, r.text


# ─── Draft-window gating ──────────────────────────────────────────


async def test_allow_before_draft_false_blocks_in_setup():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        await _set_trades_cfg(
            setup["league_id"],
            {"allow_before_draft": False},
            status="setup",
        )
        r = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(setup),
        )
        assert r.status_code == 400
        assert "before the league's draft" in r.json()["detail"]


async def test_allow_during_draft_false_blocks_in_draft_active():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        await _set_trades_cfg(
            setup["league_id"],
            {"allow_during_draft": False, "allow_before_draft": True},
            status="draft_active",
        )
        r = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(setup),
        )
        assert r.status_code == 400
        assert "during the live draft" in r.json()["detail"]


async def test_allow_during_draft_true_permits_proposal():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        await _set_trades_cfg(
            setup["league_id"],
            {"allow_during_draft": True},
            status="draft_active",
        )
        r = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(setup),
        )
        assert r.status_code == 200, r.text


# ─── Conditional trades master toggle ────────────────────────────


async def test_conditional_trade_blocked_when_disabled():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        # Default: conditional_trades_enabled = False.
        r = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(
                setup,
                conditions=[{
                    "subject_type": "team",
                    "subject": "offered",
                    "metric": "made_playoffs",
                    "operator": "eq",
                    "threshold": 1,
                }],
            ),
        )
        assert r.status_code == 400
        assert "Conditional trades are disabled" in r.json()["detail"]


async def test_conditional_trade_allowed_when_enabled():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)
        await _set_trades_cfg(setup["league_id"], {"conditional_trades_enabled": True})
        r = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(
                setup,
                conditions=[{
                    "subject_type": "team",
                    "subject": "offered",
                    "metric": "made_playoffs",
                    "operator": "eq",
                    "threshold": 1,
                }],
            ),
        )
        assert r.status_code == 200, r.text


# ─── /users/me/pending-trades aggregation ─────────────────────────


async def test_pending_trades_endpoint_buckets_correctly():
    async with AsyncClient(base_url=BASE) as client:
        setup = await _setup_league(client)

        # User A proposes a trade to B → A is proposer, B is recipient.
        r1 = await client.post(
            "/api/trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json=_trade_payload(setup),
        )
        assert r1.status_code == 200
        trade_id = r1.json()["_id"]

        # B (recipient) should see this in `awaiting_response`.
        r2 = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        awaiting_ids = [t["trade_id"] for t in body["awaiting_response"]]
        assert trade_id in awaiting_ids, "recipient should see trade in awaiting_response"
        assert body["in_review"] == []

        # A (proposer) should see nothing yet (status still 'proposed').
        r3 = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )
        assert r3.status_code == 200
        assert r3.json()["awaiting_response"] == []
        assert r3.json()["in_review"] == []

        # B accepts → trade advances to `pending`. Now A (proposer) sees it in_review.
        r4 = await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"action": "accept"},
        )
        assert r4.status_code == 200

        r5 = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )
        assert r5.status_code == 200
        review_ids = [t["trade_id"] for t in r5.json()["in_review"]]
        assert trade_id in review_ids, "proposer should see accepted trade in in_review"


async def test_pending_trades_endpoint_empty_for_new_user():
    async with AsyncClient(base_url=BASE) as client:
        token, _ = await _register(client, "j_new")
        r = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == {"awaiting_response": [], "in_review": []}

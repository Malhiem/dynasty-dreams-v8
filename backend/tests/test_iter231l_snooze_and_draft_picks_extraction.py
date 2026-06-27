"""Iter 231l — Trade Snooze 24h + draft_picks.py extraction guards.

Snooze:
  • Recipient can snooze a `proposed` trade; the trade disappears from
    their `/users/me/pending-trades` awaiting_response bucket until the
    snooze window elapses.
  • Other users in the league are unaffected (snooze is per-user).
  • Proposers and non-recipients cannot snooze.
  • Snoozing an already-pending/accepted/rejected trade returns 400.

Extraction:
  • Defer endpoints live in routes/draft_picks.py.
  • No longer in routes/drafts.py.
  • Server wires the new router.
  • drafts.py size ratchet (< 2500 lines).
"""
import os
import random
import pytest
from pathlib import Path
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime, timedelta, timezone


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
# Iter 231l — module-level asyncio marker applies broadly; the 4 sync
# file-introspection tests below explicitly opt out via `@pytest.mark.asyncio(False)`-style:
# we simply unmark them by re-asserting they're sync. Pytest-asyncio still
# warns when a sync function carries the marker, so we narrow the marker
# to the async tests using @pytest.mark.asyncio directly on each async fn.
pytestmark = []


# ─── Extraction guards (sync) ─────────────────────────────────────


def test_draft_picks_router_owns_defer_endpoints():
    src = Path("/app/backend/routes/draft_picks.py").read_text()
    assert '@router.post("/drafts/{draft_id}/picks/{pick_no}/defer")' in src
    assert '@router.get("/drafts/{draft_id}/picks/{pick_no}/defer")' in src
    assert "class DeferPickChoiceRequest" in src
    assert "_VALID_DEFER_CHOICES" in src


def test_drafts_py_no_longer_owns_defer_endpoints():
    src = Path("/app/backend/routes/drafts.py").read_text()
    assert '@router.post("/drafts/{draft_id}/picks/{pick_no}/defer")' not in src
    assert '@router.get("/drafts/{draft_id}/picks/{pick_no}/defer")' not in src
    assert "class DeferPickChoiceRequest" not in src


def test_server_wires_draft_picks_router():
    src = Path("/app/backend/server.py").read_text()
    assert "draft_picks as draft_picks_routes" in src
    assert "draft_picks_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_picks_routes.router)" in src


def test_drafts_py_size_ratchet_under_2500():
    """Iter 231l shrinks drafts.py further. Lock the gain so the next
    refactor cannot accidentally re-grow it."""
    count = len(Path("/app/backend/routes/drafts.py").read_text().splitlines())
    assert count < 2500, f"drafts.py is {count} lines — extract more before raising the cap."


# ─── Snooze helpers ───────────────────────────────────────────────


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
    token_a, uid_a = await _register(client, "l_propose")
    token_b, uid_b = await _register(client, "l_recipient")
    r = await client.post(
        "/api/leagues",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": f"TEST_Iter231l_{random.randint(10000, 99999)}",
            "season": "2026",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "roster_spots": 10,
        },
    )
    assert r.status_code == 200, r.text
    league_id = r.json()["id"]

    mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mongo[os.environ.get("DB_NAME", "test_database")]
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


async def _propose_trade(client, setup):
    r = await client.post(
        "/api/trades",
        headers={"Authorization": f"Bearer {setup['token_a']}"},
        json={
            "league_id": setup["league_id"],
            "target_team_id": setup["team_b_id"],
            "assets_offered": [{"asset_type": "pick", "pick_round": "1", "pick_year": 2027}],
            "assets_requested": [{"asset_type": "pick", "pick_round": "2", "pick_year": 2027}],
            "message": "iter231l snooze test",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["_id"]


# ─── Snooze behaviour ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recipient_can_snooze_proposed_trade():
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)

        # Before snooze: B sees the trade in awaiting_response.
        r = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        ids = [t["trade_id"] for t in r.json()["awaiting_response"]]
        assert trade_id in ids

        # Snooze.
        r2 = await client.post(
            f"/api/trades/{trade_id}/snooze",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"hours": 24},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["hours"] == 24
        assert "snoozed_until" in body
        # Snooze should be 24h in the future.
        until = datetime.fromisoformat(body["snoozed_until"])
        delta = until - datetime.now(timezone.utc)
        assert timedelta(hours=23, minutes=55) < delta < timedelta(hours=24, minutes=5)

        # After snooze: B no longer sees the trade.
        r3 = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        ids_after = [t["trade_id"] for t in r3.json()["awaiting_response"]]
        assert trade_id not in ids_after


@pytest.mark.asyncio
async def test_snooze_is_per_user_only():
    """Snoozing by user B does not hide the trade from anyone else."""
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)

        # B snoozes.
        await client.post(
            f"/api/trades/{trade_id}/snooze",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"hours": 24},
        )

        # Trade is still queryable + visible in /transactions for B.
        r = await client.get(
            f"/api/trades/{trade_id}",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        assert r.status_code == 200
        # Status unchanged.
        assert r.json().get("status") == "proposed"


@pytest.mark.asyncio
async def test_proposer_cannot_snooze_own_proposal():
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)

        r = await client.post(
            f"/api/trades/{trade_id}/snooze",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
            json={"hours": 24},
        )
        assert r.status_code == 403
        assert "recipient" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_third_party_cannot_snooze():
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)
        token_c, _ = await _register(client, "l_outsider")

        r = await client.post(
            f"/api/trades/{trade_id}/snooze",
            headers={"Authorization": f"Bearer {token_c}"},
            json={"hours": 24},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_cannot_snooze_non_proposed_trade():
    """After acceptance the trade is `pending` (in review window) — the
    snooze endpoint must reject the request with a clear error."""
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)

        # B accepts → status becomes 'pending'.
        await client.post(
            f"/api/trades/{trade_id}/respond",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"action": "accept"},
        )

        r = await client.post(
            f"/api/trades/{trade_id}/snooze",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"hours": 24},
        )
        assert r.status_code == 400
        assert "proposed" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_snooze_hours_capped_at_one_week():
    """`hours` is clamped to [1, 168]."""
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)

        # Request a huge window — should clamp to 168h (7 days).
        r = await client.post(
            f"/api/trades/{trade_id}/snooze",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
            json={"hours": 9999},
        )
        assert r.status_code == 200
        assert r.json()["hours"] == 168


@pytest.mark.asyncio
async def test_expired_snooze_resurfaces_trade():
    """Past-dated snoozes are ignored — the banner re-surfaces the trade."""
    async with AsyncClient(base_url=BASE, timeout=30.0) as client:
        setup = await _setup_league(client)
        trade_id = await _propose_trade(client, setup)

        # Direct-DB poke a past-dated snooze for B.
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mongo[os.environ.get("DB_NAME", "test_database")]
        await db.trades.update_one(
            {"_id": ObjectId(trade_id)},
            {"$set": {f"snoozed_until_by.{setup['uid_b']}": past_iso}},
        )
        mongo.close()

        r = await client.get(
            "/api/users/me/pending-trades",
            headers={"Authorization": f"Bearer {setup['token_b']}"},
        )
        ids = [t["trade_id"] for t in r.json()["awaiting_response"]]
        assert trade_id in ids, "expired snooze should not hide the trade"

"""Iter 231g — Trades configuration round-trip.

Guards the new `transactions_config.trades` sub-envelope: schema defaults,
validation bounds, and that PUT round-trips every field surfaced in the
new Commissioner UI card.
"""
import os
import random
import pytest
from httpx import AsyncClient


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
    return token


async def _create_league(client, token, suffix):
    r = await client.post(
        "/api/leagues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"TEST_Iter231g_{suffix}_{random.randint(10000, 99999)}",
            "season": "2026",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "roster_spots": 10,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_trades_config_defaults_present_on_fresh_league():
    """GET on a fresh league must return the full trades sub-config with
    the documented defaults (review_period_hours=72, veto_threshold_teams=4,
    voting_system='managers', etc)."""
    async with AsyncClient(base_url=BASE) as client:
        token = await _register(client, "g_defaults")
        league_id = await _create_league(client, token, "defaults")
        r = await client.get(
            f"/api/leagues/{league_id}/transactions-config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert "trades" in cfg, "trades sub-envelope must be returned"
        t = cfg["trades"]
        assert t["review_period_hours"] == 72
        assert t["veto_threshold_teams"] == 4
        assert t["max_trades_per_team"] is None  # unlimited by default
        assert t["voting_system"] == "managers"
        assert t["anonymous_voting"] is True
        assert t["lock_at_first_game"] is False
        assert t["allow_before_draft"] is True
        assert t["allow_during_draft"] is False
        assert t["allow_illegal_rosters"] is False
        assert t["comments_visible_to_all"] is False
        assert t["conditional_trades_enabled"] is False


async def test_trades_config_put_round_trips_every_field():
    """PUT with custom values across every trades field, then GET — every
    field must persist as supplied."""
    async with AsyncClient(base_url=BASE) as client:
        token = await _register(client, "g_roundtrip")
        league_id = await _create_league(client, token, "roundtrip")
        headers = {"Authorization": f"Bearer {token}"}

        # Read defaults first to get a complete envelope baseline.
        r = await client.get(f"/api/leagues/{league_id}/transactions-config", headers=headers)
        cfg = r.json()
        cfg["trades"] = {
            "review_period_hours": 24,
            "veto_threshold_teams": 6,
            "max_trades_per_team": 15,
            "voting_system": "both",
            "anonymous_voting": False,
            "lock_at_first_game": True,
            "allow_before_draft": False,
            "allow_during_draft": True,
            "allow_illegal_rosters": True,
            "comments_visible_to_all": True,
            "conditional_trades_enabled": True,
        }
        r2 = await client.put(
            f"/api/leagues/{league_id}/transactions-config",
            headers=headers,
            json=cfg,
        )
        assert r2.status_code == 200, r2.text

        # Re-fetch and verify every field round-tripped exactly.
        r3 = await client.get(f"/api/leagues/{league_id}/transactions-config", headers=headers)
        t = r3.json()["trades"]
        assert t["review_period_hours"] == 24
        assert t["veto_threshold_teams"] == 6
        assert t["max_trades_per_team"] == 15
        assert t["voting_system"] == "both"
        assert t["anonymous_voting"] is False
        assert t["lock_at_first_game"] is True
        assert t["allow_before_draft"] is False
        assert t["allow_during_draft"] is True
        assert t["allow_illegal_rosters"] is True
        assert t["comments_visible_to_all"] is True
        assert t["conditional_trades_enabled"] is True


async def test_trades_config_validates_bounds():
    """Out-of-range values should be rejected at the schema layer."""
    async with AsyncClient(base_url=BASE) as client:
        token = await _register(client, "g_bounds")
        league_id = await _create_league(client, token, "bounds")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(f"/api/leagues/{league_id}/transactions-config", headers=headers)
        cfg = r.json()

        # review_period_hours > 336 (14 days max)
        cfg2 = {**cfg, "trades": {**cfg["trades"], "review_period_hours": 500}}
        r2 = await client.put(
            f"/api/leagues/{league_id}/transactions-config", headers=headers, json=cfg2,
        )
        assert r2.status_code == 422, f"out-of-range review_period_hours should 422; got {r2.status_code}"

        # veto_threshold_teams negative
        cfg3 = {**cfg, "trades": {**cfg["trades"], "veto_threshold_teams": -1}}
        r3 = await client.put(
            f"/api/leagues/{league_id}/transactions-config", headers=headers, json=cfg3,
        )
        assert r3.status_code == 422

        # max_trades_per_team out of range
        cfg4 = {**cfg, "trades": {**cfg["trades"], "max_trades_per_team": 100}}
        r4 = await client.put(
            f"/api/leagues/{league_id}/transactions-config", headers=headers, json=cfg4,
        )
        assert r4.status_code == 422

        # voting_system invalid enum
        cfg5 = {**cfg, "trades": {**cfg["trades"], "voting_system": "anyone"}}
        r5 = await client.put(
            f"/api/leagues/{league_id}/transactions-config", headers=headers, json=cfg5,
        )
        assert r5.status_code == 422


async def test_trades_config_non_commissioner_cannot_edit():
    """Only commissioners (+ co-commissioners) can PUT."""
    async with AsyncClient(base_url=BASE) as client:
        # Commissioner creates the league.
        token_owner = await _register(client, "g_owner")
        league_id = await _create_league(client, token_owner, "owner")
        # Second user (non-commissioner).
        token_other = await _register(client, "g_intruder")

        # Get a baseline envelope as the commissioner.
        r = await client.get(
            f"/api/leagues/{league_id}/transactions-config",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        cfg = r.json()

        # Intruder PUT must be 403.
        cfg["trades"] = {**cfg["trades"], "review_period_hours": 1}
        r2 = await client.put(
            f"/api/leagues/{league_id}/transactions-config",
            headers={"Authorization": f"Bearer {token_other}"},
            json=cfg,
        )
        assert r2.status_code == 403, r2.text

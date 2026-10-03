"""Iter 102: lineup-lock runtime gate + playoff bracket generator hookup."""
import os
import pytest
from httpx import AsyncClient
from datetime import datetime, timezone


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LID = "69e46af167999bfb85c39628"


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_lineup_lock_evaluator_unit():
    """Unit-test the evaluator directly — no HTTP round-trip needed."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from utils.lineup_lock import evaluate_lineup_lock

    # Daily lock, 0-min cushion → never locked
    league = {"roster_lock_type": "daily", "lineup_lock_minutes_before": 0}
    out = evaluate_lineup_lock(league)
    assert out["locked"] is False
    assert out["scope"] == "regular"
    assert out["cadence"] == "daily"

    # Weekly Monday lock with 30 min cushion — locked iff Sun 23:30..23:59
    league_w = {
        "roster_lock_type": "weekly",
        "roster_lock_day": "monday",
        "lineup_lock_minutes_before": 30,
    }
    # Sunday 23:45 UTC → inside lock window
    sun_2345 = datetime(2026, 2, 22, 23, 45, tzinfo=timezone.utc)
    assert sun_2345.weekday() == 6  # sanity: Sun
    out_locked = evaluate_lineup_lock(league_w, now=sun_2345)
    assert out_locked["locked"] is True
    assert "Weekly" in out_locked["reason"]

    # Tuesday 14:00 UTC → safely unlocked
    tue_1400 = datetime(2026, 2, 24, 14, 0, tzinfo=timezone.utc)
    assert tue_1400.weekday() == 1
    out_open = evaluate_lineup_lock(league_w, now=tue_1400)
    assert out_open["locked"] is False


@pytest.mark.asyncio
async def test_lineup_lock_playoff_override_applies_only_in_playoff_weeks():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from utils.lineup_lock import evaluate_lineup_lock

    league = {
        "roster_lock_type": "daily",
        "lineup_lock_minutes_before": 0,
        "playoff_roster_lock_override": True,
        "playoff_roster_lock_type": "weekly",
        "playoff_roster_lock_day": "monday",
        "playoff_lineup_lock_minutes_before": 30,
        "playoff_start_week": 19,
        "playoff_end_week": 21,
    }
    sun_2345 = datetime(2026, 2, 22, 23, 45, tzinfo=timezone.utc)
    # Week 10 → regular-season config (daily, 0 cushion) → unlocked
    out_reg = evaluate_lineup_lock(league, now=sun_2345, current_week=10)
    assert out_reg["locked"] is False
    assert out_reg["scope"] == "regular"
    # Week 20 → playoff override → weekly Monday + 30 cushion → LOCKED
    out_po = evaluate_lineup_lock(league, now=sun_2345, current_week=20)
    assert out_po["locked"] is True
    assert out_po["scope"] == "playoff"


@pytest.mark.asyncio
async def test_seed_pairings_methods():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from routes.matchups import _seed_pairings

    teams = ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]
    # high_vs_low → (1v8, 2v7, 3v6, 4v5)
    hv = _seed_pairings(teams, "high_vs_low")
    assert hv == [("t1", "t8"), ("t2", "t7"), ("t3", "t6"), ("t4", "t5")]
    # adjacent → (1v2, 3v4, 5v6, 7v8)
    aj = _seed_pairings(teams, "adjacent")
    assert aj == [("t1", "t2"), ("t3", "t4"), ("t5", "t6"), ("t7", "t8")]


@pytest.mark.asyncio
async def test_generate_schedule_creates_playoff_bracket_with_tree_format():
    """When playoff_format=playoff_tree, generate-schedule must seed Round 1
    real matchups and append TBD placeholders for subsequent rounds."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        # Snapshot existing format so we can revert
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()

        # Configure playoff tree + high_vs_low seeding
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": "playoff_tree",
            "playoff_seeding_method": "high_vs_low",
        })
        # Regenerate the schedule
        gen = await client.post("/api/matchups/generate-schedule", headers=headers, json={
            "league_id": LID, "num_weeks": 18,
        })
        assert gen.status_code == 200, gen.text
        body = gen.json()
        assert body["playoff_matchups"] >= 4  # 8 teams → 4 Round-1 matchups
        # Fetch the playoff matchups
        all_m = await client.get(f"/api/matchups/{LID}", headers=headers)
        rows = all_m.json()
        playoff_rows = [m for m in rows if m.get("is_playoff")]
        assert len(playoff_rows) >= 4
        # Round 1 must have NO TBD slots (real teams)
        r1 = [m for m in playoff_rows if m.get("bracket_round") == 1]
        assert all(not m.get("home_team_tbd") and not m.get("away_team_tbd") for m in r1)
        # Later rounds SHOULD have TBD placeholders
        later = [m for m in playoff_rows if m.get("bracket_round", 1) > 1]
        assert any(m.get("home_team_tbd") or m.get("away_team_tbd") for m in later)

        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": before.get("playoff_format"),
            "playoff_seeding_method": before.get("playoff_seeding_method"),
        })


@pytest.mark.asyncio
async def test_generate_schedule_h2h_matchup_format_skips_bracket():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": "h2h_matchup",
        })
        gen = await client.post("/api/matchups/generate-schedule", headers=headers, json={
            "league_id": LID, "num_weeks": 18,
        })
        assert gen.status_code == 200
        # No playoff matchups in h2h_matchup mode (matchups are the regular weekly H2H)
        # Consolation can still produce some — explicit check:
        body = gen.json()
        assert body["playoff_matchups"] == 0

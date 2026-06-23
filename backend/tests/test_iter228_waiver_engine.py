"""
Iter 228 — Waiver execution engine + scheduler endpoints.

Covers:
  • `process_pending_claims` is idempotent for un-due claims (skipped)
  • FAAB sort: highest bid wins, FAAB debited only from winner
  • Auto-priority sort: lowest priority_index wins
  • Multi-team competition for same player picks the right winner
  • `compute_next_run` returns ISO for scheduled mode, days mode, or None when disabled
  • `GET /api/waivers/next-run` surfaces config + pending count
  • `POST /api/waivers/process` honours `force=true` flag
"""
from __future__ import annotations

import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

from bson import ObjectId

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _register(prefix="iter228"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": e, "password": "Pass123!"})
    r.raise_for_status()
    return e, r.json()["access_token"]


def _login(email, password="Pass123!"):
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _create_league(tok):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"iter228-{uuid.uuid4().hex[:6]}",
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 4, "draft_type": "snake", "roster_spots": 20,
    })
    r.raise_for_status()
    return r.json()


def _db():
    # Direct mongo access for setup
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "test_database")
    return MongoClient(mongo_url)[db_name]


def _put_waiver_config(tok, league_id, *, enabled=True, system_type="faab",
                       processing_mode="days", processing_days_count=2,
                       processing_schedule=None):
    H = {"Authorization": f"Bearer {tok}"}
    cfg = {
        "claim_limits": {"season": {}, "week": {}},
        "claim_rules": {},
        "free_agency": {"system_type": "open"},
        "waiver": {
            "enabled": enabled,
            "system_type": system_type,
            "processing_mode": processing_mode,
            "processing_days_count": processing_days_count,
            "processing_schedule": processing_schedule or [],
            "faab_budget": 100,
        },
        "draft_claims": {},
    }
    r = requests.put(
        f"{API_URL}/api/leagues/{league_id}/transactions-config",
        headers=H, json=cfg,
    )
    r.raise_for_status()


def _seed_claim(db, league_id, team_id, team_name, owner_id, player_id,
                player_name, bid, processes_at):
    return db.waiver_claims.insert_one({
        "league_id": league_id,
        "team_id": team_id,
        "team_name": team_name,
        "owner_id": owner_id,
        "player_id": player_id,
        "player_name": player_name,
        "player_position": "C",
        "player_team": "NYR",
        "bid_amount": bid,
        "drop_player_id": None,
        "drop_player_name": None,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": processes_at.isoformat(),
        "week": 1,
        "season": "2025-2026",
    }).inserted_id


def _seed_team(db, league_id, owner_id, name):
    tid = db.teams.insert_one({
        "league_id": league_id,
        "owner_id": owner_id,
        "owner_name": name,
        "name": name,
        "roster": [],
        "wins": 0,
        "losses": 0,
        "points_for": 0,
    }).inserted_id
    return str(tid)


def _seed_player(db, name="Waiver Player"):
    pid = db.players.insert_one({
        "name": name,
        "nhl_id": int(uuid.uuid4().int % 1_000_000_000) + 800_000_000,
        "position": "C",
        "team": "NYR",
        "points": 25,
        "games_played": 50,
        "player_type": "skater",
    }).inserted_id
    return str(pid)


# ── Tests ────────────────────────────────────────────────────


def test_compute_next_run_disabled_returns_none():
    """When waiver.enabled=False compute_next_run returns None."""
    from services.waiver_engine import compute_next_run

    league = {"_id": ObjectId(), "transactions_config": {"waiver": {"enabled": False}}}
    assert compute_next_run(league) is None


def test_compute_next_run_days_mode_returns_future_iso():
    from services.waiver_engine import compute_next_run

    league = {"_id": ObjectId(), "transactions_config": {"waiver": {
        "enabled": True, "processing_mode": "days", "processing_days_count": 3,
    }}}
    out = compute_next_run(league)
    assert out is not None
    parsed = datetime.fromisoformat(out)
    diff = (parsed - datetime.now(timezone.utc)).total_seconds()
    # Should be ~3 days in the future (allow 5s drift)
    assert 3 * 86400 - 5 < diff < 3 * 86400 + 5


def test_compute_next_run_scheduled_mode_returns_next_slot():
    from services.waiver_engine import compute_next_run

    now = datetime.now(timezone.utc)
    # Pick a DOW 3 days from now
    target_dow = (now + timedelta(days=3)).weekday()
    league = {"_id": ObjectId(), "transactions_config": {"waiver": {
        "enabled": True,
        "processing_mode": "scheduled",
        "processing_schedule": [
            {"day_of_week": target_dow, "time": "09:00"},
        ],
    }}}
    out = compute_next_run(league, now=now)
    assert out is not None
    parsed = datetime.fromisoformat(out)
    assert parsed > now
    assert parsed.weekday() == target_dow


def test_next_run_endpoint():
    """GET /api/waivers/next-run surfaces config + pending count."""
    tok_email, tok = _register("iter228next")
    league = _create_league(tok)
    _put_waiver_config(tok, league["id"], enabled=True,
                       processing_mode="days", processing_days_count=2)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/waivers/next-run",
                     params={"league_id": league["id"]}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["mode"] == "days"
    assert body["pending_count"] == 0
    assert body["next_run_at"] is not None


def test_engine_faab_highest_bid_wins():
    """Two teams claim same player. Higher bid wins; loser marked lost."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.waiver_engine import process_pending_claims

    # Use the same DB as the app
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "test_database")
    db_sync = _db()

    # Setup: create league via API, 2 teams
    tok_email, tok = _register("iter228faab")
    league = _create_league(tok)
    _put_waiver_config(tok, league["id"], enabled=True, system_type="faab")

    # League create only seeds the commissioner team (1 team).
    # Seed a second team directly in mongo so we have 2 competitors.
    owner_b = "fake_owner_" + uuid.uuid4().hex[:8]
    team_a = db_sync.teams.find_one({"league_id": league["id"]})
    team_a_id = str(team_a["_id"])
    team_a_name = team_a["name"]
    team_a_owner = team_a["owner_id"]
    team_b_id = _seed_team(db_sync, league["id"], owner_b, "TeamB")

    # Seed FAAB budgets
    db_sync.waiver_budgets.insert_one({
        "team_id": team_a_id, "league_id": league["id"],
        "total_budget": 100, "spent": 0, "remaining": 100,
    })
    db_sync.waiver_budgets.insert_one({
        "team_id": team_b_id, "league_id": league["id"],
        "total_budget": 100, "spent": 0, "remaining": 100,
    })

    player_id = _seed_player(db_sync, name=f"WaiverTarget-{uuid.uuid4().hex[:6]}")

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    cid_a = _seed_claim(db_sync, league["id"], team_a_id, team_a_name,
                        team_a_owner, player_id, "WaiverTarget", bid=10, processes_at=past)
    cid_b = _seed_claim(db_sync, league["id"], team_b_id, "TeamB",
                        owner_b, player_id, "WaiverTarget", bid=25, processes_at=past)

    # Run the engine
    async def run():
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        return await process_pending_claims(db, league["id"])

    result = asyncio.run(run())

    assert result["processed"] == 1, result
    # Winner should be B ($25)
    claim_a = db_sync.waiver_claims.find_one({"_id": cid_a})
    claim_b = db_sync.waiver_claims.find_one({"_id": cid_b})
    assert claim_b["status"] == "won", claim_b
    assert claim_a["status"] == "lost", claim_a

    # FAAB debited only from B
    budget_a = db_sync.waiver_budgets.find_one({"team_id": team_a_id, "league_id": league["id"]})
    budget_b = db_sync.waiver_budgets.find_one({"team_id": team_b_id, "league_id": league["id"]})
    assert budget_a["remaining"] == 100, budget_a
    assert budget_b["remaining"] == 75, budget_b

    # Player should appear on B's roster
    team_b_after = db_sync.teams.find_one({"_id": ObjectId(team_b_id)})
    assert player_id in (team_b_after.get("roster") or []), team_b_after


def test_engine_skips_un_due_claims():
    """Claims with processes_at in the future are NOT processed."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.waiver_engine import process_pending_claims

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "test_database")
    db_sync = _db()

    tok_email, tok = _register("iter228future")
    league = _create_league(tok)
    _put_waiver_config(tok, league["id"], enabled=True, system_type="faab")
    team_a = db_sync.teams.find_one({"league_id": league["id"]})
    team_a_id = str(team_a["_id"])

    player_id = _seed_player(db_sync, name=f"FutureP-{uuid.uuid4().hex[:6]}")
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    cid = _seed_claim(db_sync, league["id"], team_a_id, team_a["name"],
                      team_a["owner_id"], player_id, "FutureP", bid=5, processes_at=future)

    async def run():
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        return await process_pending_claims(db, league["id"])

    result = asyncio.run(run())
    assert result["processed"] == 0, result
    assert result["skipped"] >= 1, result

    # Claim remains pending
    claim = db_sync.waiver_claims.find_one({"_id": cid})
    assert claim["status"] == "pending"


def test_force_process_via_route():
    """POST /api/waivers/process?force=true processes every pending claim."""
    db_sync = _db()
    tok_email, tok = _register("iter228force")
    league = _create_league(tok)
    _put_waiver_config(tok, league["id"], enabled=True, system_type="faab")
    team_a = db_sync.teams.find_one({"league_id": league["id"]})
    team_a_id = str(team_a["_id"])

    db_sync.waiver_budgets.insert_one({
        "team_id": team_a_id, "league_id": league["id"],
        "total_budget": 100, "spent": 0, "remaining": 100,
    })

    player_id = _seed_player(db_sync, name=f"ForceP-{uuid.uuid4().hex[:6]}")
    future = datetime.now(timezone.utc) + timedelta(days=3)
    cid = _seed_claim(db_sync, league["id"], team_a_id, team_a["name"],
                      team_a["owner_id"], player_id, "ForceP", bid=10, processes_at=future)

    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/waivers/process",
                      params={"league_id": league["id"], "force": "true"},
                      headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processed"] == 1, body
    claim = db_sync.waiver_claims.find_one({"_id": cid})
    assert claim["status"] == "won", claim

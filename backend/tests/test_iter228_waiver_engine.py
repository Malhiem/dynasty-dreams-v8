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
        # Iter 231ac — Tag every test-seeded player so the autouse
        # cleanup fixture (and any future repair script) can find and
        # delete them. Without this, repeated runs against the shared
        # preview DB leak ForceP/FutureP/WaiverTarget rows into the
        # global player pool — which surface in the live waiver wire,
        # player search, and free-agent screens for real users (see
        # iter231ac repair: 65 polluting players, 89 polluted rosters).
        "iter228_test_seed": True,
    }).inserted_id
    return str(pid)


# Iter 231ac — Module-scoped autouse cleanup. Each test that seeds a
# player via `_seed_player` AND/OR creates an `iter228-*` league via
# `_create_league` MUST be torn down so we don't leak rows into the
# shared preview database.
@__import__("pytest").fixture(autouse=True)
def _cleanup_iter228_pollution():
    """Sweep iter228 test artefacts before AND after each test.

    Before: belt-and-suspenders for runs that previously aborted
    mid-test (e.g. KeyboardInterrupt) and left rows behind.
    After: the canonical cleanup path.
    """
    def _sweep():
        try:
            db = _db()
            # 1. Find all test-seeded players (tagged + legacy prefix-named).
            import re as _re
            _pattern = _re.compile(r"^(ForceP|FutureP|WaiverTarget)", _re.IGNORECASE)
            test_players = list(db.players.find(
                {"$or": [
                    {"iter228_test_seed": True},
                    {"name": {"$regex": _pattern}},
                ]},
                {"_id": 1},
            ))
            pids = [str(p["_id"]) for p in test_players]
            if pids:
                from bson import ObjectId as _OID
                db.teams.update_many(
                    {"roster": {"$in": pids}},
                    {"$pull": {"roster": {"$in": pids}}},
                )
                db.waiver_claims.delete_many({"player_id": {"$in": pids}})
                db.players.delete_many({"_id": {"$in": [_OID(p) for p in pids]}})
            # 2. Drop iter228-* leagues + their teams + drafts.
            iter_leagues = list(db.leagues.find(
                {"name": {"$regex": "^iter228-"}}, {"_id": 1},
            ))
            iter_ids = [str(l["_id"]) for l in iter_leagues]
            if iter_ids:
                from bson import ObjectId as _OID2
                db.teams.delete_many({"league_id": {"$in": iter_ids}})
                db.drafts.delete_many({"league_id": {"$in": iter_ids}})
                db.waiver_claims.delete_many({"league_id": {"$in": iter_ids}})
                db.waiver_budgets.delete_many({"league_id": {"$in": iter_ids}})
                db.leagues.delete_many({"_id": {"$in": [_OID2(i) for i in iter_ids]}})
        except Exception as _e:
            # Best-effort cleanup; never block the test run on a sweep
            # failure (the next test's setup-sweep will catch it).
            print(f"[iter228 cleanup] sweep skipped: {_e}")

    _sweep()
    yield
    _sweep()



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


# ─── Iter 228c — Transaction guard + timezone-aware compute_next_run ─────


def test_compute_next_run_respects_league_timezone():
    """When league.timezone is set, scheduled-mode slot times are
    interpreted in that local timezone (not UTC)."""
    from services.waiver_engine import compute_next_run

    # Fix "now" to a specific UTC moment: Mon 2026-03-02 12:00 UTC
    now = datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc)
    league_la = {
        "_id": ObjectId(),
        "timezone": "America/Los_Angeles",
        "transactions_config": {"waiver": {
            "enabled": True,
            "processing_mode": "scheduled",
            "processing_schedule": [
                # Wednesday at 09:00 LA time (= 17:00 UTC)
                {"day_of_week": 2, "time": "09:00"},
            ],
        }},
    }
    out = compute_next_run(league_la, now=now)
    assert out is not None, "expected next slot computed"
    parsed = datetime.fromisoformat(out)
    # Should be Wed 2026-03-04 17:00 UTC (= Wed 2026-03-04 09:00 LA)
    assert parsed.year == 2026 and parsed.month == 3 and parsed.day == 4, parsed
    assert parsed.hour == 17, f"expected 17:00 UTC (09:00 LA), got {parsed.hour}"

    # Same slot but UTC league → 09:00 UTC on Wednesday
    league_utc = dict(league_la)
    league_utc["timezone"] = "UTC"
    out_utc = compute_next_run(league_utc, now=now)
    parsed_utc = datetime.fromisoformat(out_utc)
    assert parsed_utc.hour == 9, parsed_utc


def test_finalize_winner_rolls_back_on_roster_add_failure():
    """If the final roster $addToSet write fails, the engine compensates
    by undoing the claim status, FAAB debit, and any drop step.

    Tests `_finalize_winner` directly with a stub db that fails on the
    final `teams.update_one` $addToSet call. This exercises the
    compensating-write fallback path (Path B).
    """
    import asyncio
    from services.waiver_engine import _finalize_winner

    # Build a stub db that records writes and fails the final addToSet
    writes: list[dict] = []

    class _StubColl:
        def __init__(self, name):
            self.name = name

        async def update_one(self, filt, update, **kw):
            writes.append({"coll": self.name, "filter": filt, "update": update})
            if self.name == "teams" and "$addToSet" in update:
                raise RuntimeError("simulated roster-add failure")

            class _Res:
                modified_count = 1
            return _Res()

    class _StubDB:
        client = None  # forces Path B fallback (compensating-writes)

        def __getattr__(self, name):
            return _StubColl(name)

    winner = {
        "_id": "claim_abc",
        "team_id": str(ObjectId()),
        "player_id": "player_xyz",
        "bid_amount": 25,
        "drop_player_id": None,
    }

    ok = asyncio.run(_finalize_winner(_StubDB(), "league_1", winner, "faab",
                                       datetime.now(timezone.utc).isoformat()))
    assert ok is False, "expected finalize to abort on roster-add failure"

    # Verify compensating writes ran in reverse order:
    # forward: claim→won, FAAB-debit, teams-addToSet (failed)
    # reverse: teams-addToSet (no actual write since failed), FAAB-refund, claim-revert
    coll_names = [w["coll"] for w in writes]
    # We expect at least claim->won, budgets-debit, teams-addToSet (failed),
    # budgets-refund, claim-revert
    assert "waiver_claims" in coll_names
    assert "waiver_budgets" in coll_names
    assert "teams" in coll_names

    # Compensating writes: there should be TWO waiver_budgets writes
    # (debit + refund) and TWO waiver_claims writes (won + revert)
    budget_writes = [w for w in writes if w["coll"] == "waiver_budgets"]
    claim_writes = [w for w in writes if w["coll"] == "waiver_claims"]
    assert len(budget_writes) == 2, f"expected debit+refund, got {budget_writes}"
    assert len(claim_writes) == 2, f"expected won+revert, got {claim_writes}"

    # The second budget write should refund (inverse $inc)
    refund = budget_writes[1]["update"]["$inc"]
    assert refund["remaining"] == 25 and refund["spent"] == -25, refund

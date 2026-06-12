"""
Iter 167 — Conditional-pick asterisk + lock + false-positive chip fix.

The user reported that the Draft Board was showing the trade `↔` chip on
every pick even when none had been traded. Root cause: the abbr-keyed
fallback could resolve to a different team's (traded) pick when the
column header matched by abbr but `ownerTeam.id` didn't. Fix: the abbr
fallback now ONLY fires when `ownerTeam?.id` is unresolved.

Also adds the user-requested conditional-pick asterisk:
  * Backend `/drafts/{league_id}/picks` already returns
    `pending_protections` per pick (Iter 139).
  * Frontend Draft Board renders a `*` next to the pick number when
    `pending_protections.length > 0`, with a tooltip explaining the
    clause.
  * Backend `/trades` POST rejects any proposal that includes a pick
    with un-resolved `pick_upgrades` (status `executed`, neither
    `applied_at` nor `failed_at` set) — locking the pick from re-trade
    until the condition resolves.
"""
import os
from pathlib import Path

import pytest
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("BASE missing")


BASE = _backend_url()
LID = "69e46af167999bfb85c39628"


async def _tok(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ── Backend ──


@pytest.mark.asyncio
async def test_conditional_pick_locked_from_retrade():
    """Build a synthetic pending pick_upgrades trade, then try to
    propose a new trade that includes the locked pick — must 400."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        admin = await _tok(client, "admin@dynastydreams.com", "Admin123!")
        ah = {"Authorization": f"Bearer {admin}"}
        commish = await _tok(client, "chriszarek@gmail.com", "Chris2026!")
        ch = {"Authorization": f"Bearer {commish}"}

        # Clean slate
        await client.post(f"/api/admin/trades/clear?league_id={LID}", headers=ah)
        # Make sure picks exist
        await client.post(f"/api/admin/seed/draft-picks?league_id={LID}&year=2026&rounds=5", headers=ah)

        # Insert a synthetic "executed" trade with a pending pick_upgrade
        # via a Mongo write (no public endpoint for this in test scope).
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        import os
        from motor.motor_asyncio import AsyncIOMotorClient
        mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = mc[os.environ["DB_NAME"]]
        try:
            # Grab one of the seeded picks
            pick = await db.draft_picks.find_one({"league_id": LID})
            assert pick is not None
            pid = str(pick["_id"])
            # Find chris's team in this league
            chris_team = await db.teams.find_one({"league_id": LID, "owner_id": "69e43c4ddba209f1da22660c"})
            assert chris_team is not None
            # Get a target team
            other = await db.teams.find_one({"league_id": LID, "_id": {"$ne": chris_team["_id"]}})
            assert other is not None
            # Build the lock trade record (executed, with unresolved upgrade)
            lock_id = await db.trades.insert_one({
                "league_id": LID,
                "proposer_id": "69e43c4ddba209f1da22660c",
                "proposer_team_id": str(chris_team["_id"]),
                "target_owner_id": other.get("owner_id"),
                "target_team_id": str(other["_id"]),
                "assets_offered": [],
                "assets_requested": [],
                "status": "executed",
                "pick_upgrades": [{
                    "pick_id": pid,
                    "new_round": 1,
                    "new_year": 2027,
                    "condition": {
                        "subject_type": "team",
                        "metric": "playoff_seed",
                        "operator": "le",
                        "threshold": 5,
                        "description": "Pick becomes top-5 protected"
                    },
                    "applied_at": None,
                    "failed_at": None,
                }],
            })

            # /drafts/{league_id}/picks now returns pending_protections for that pick
            r = await client.get(f"/api/drafts/{LID}/picks?year=2026", headers=ah)
            picks_payload = r.json()
            target = next(p for p in picks_payload["picks"] if p["_id"] == pid)
            assert len(target["pending_protections"]) >= 1, "pending_protections must populate"

            # Now try to PROPOSE a new trade that includes this locked pick
            # The proposer must be the current owner of the pick — find them.
            owner_team = await db.teams.find_one({"_id": __import__("bson").ObjectId(pick["current_team_id"])})
            owner_user_id = owner_team.get("owner_id")
            # Login as that user. If not chris, fall back to admin (will hit
            # the auth gate before the lock — but the lock check happens BEFORE
            # the team-membership check is needed; the proposer team gate
            # happens AFTER the lock check in the new ordering).
            # We expect 400 from the lock irrespective of proposer identity.
            r = await client.post("/api/trades", headers=ch, json={
                "league_id": LID,
                "target_team_id": str(other["_id"]),
                "assets_offered": [{"asset_type": "pick", "pick_id": pid}],
                "assets_requested": [],
            })
            assert r.status_code == 400, r.text
            assert "conditional" in r.text.lower() or "locked" in r.text.lower(), r.text
        finally:
            # Clean up the synthetic lock
            await db.trades.delete_one({"_id": lock_id.inserted_id})


# ── Frontend ──


FRONT = Path("/app/frontend/src")


def test_draft_room_renders_conditional_asterisk():
    src = (FRONT / "lovable/pages/DraftRoom.tsx").read_text()
    # State derived from pending_protections
    assert "const conditionalProtections = (livePick?.pending_protections || []) as any[]" in src
    assert "const isConditional = conditionalProtections.length > 0" in src
    # Asterisk render + testid
    assert 'draft-board-pick-conditional-${teamAbbr}-${round}' in src
    # Tooltip explains the clause
    assert "Conditional protection — locked from re-trade" in src


def test_abbr_fallback_no_longer_overrides_ownerteam_lookup():
    """False-positive chip fix: abbr fallback must NOT trigger when
    ownerTeam.id has already resolved. Previously the abbr fallback
    could overwrite the strict-ID lookup and pull a stale pick whose
    `trade_history` belonged to a different team."""
    src = (FRONT / "lovable/pages/DraftRoom.tsx").read_text()
    assert "|| (!ownerTeam?.id ? livePicksByOrigKey[`${round}|abbr:${teamAbbr}`] : null)" in src

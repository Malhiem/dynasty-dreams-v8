"""Pick upgrade engine: a 2-team trade with a `pick_upgrades` clause that
fires on `won_championship`. Tests the `_apply_pick_upgrades` helper directly
and via the award-toggle re-eval hook surfaced through PUT /awards endpoint."""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()


BASE = _backend_url()


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_pick_upgrade_applies_when_championship_unlocks():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        h = {"Authorization": f"Bearer {tok}"}

        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        me = (await c.get("/api/auth/me", headers=h)).json()
        league = leagues[0]
        lid = league["id"]

        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if t.get("name") == "Zarek's Frozen")
        partner = next(t for t in teams if t["_id"] != my["_id"])

        # Use a pick the PARTNER currently owns — they'll send it to me; if I
        # win the championship, that 2nd-round pick upgrades to a 1st.
        partner_pick_2nd = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(partner["_id"]), "round": 2,
        })
        if not partner_pick_2nd:
            pytest.skip("No 2nd-round pick on partner team")
        partner_pick_id = str(partner_pick_2nd["_id"])
        original_round = partner_pick_2nd["round"]
        original_year = partner_pick_2nd["year"]

        # Clear any past championship flag so we control timing
        await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"championship_won_at": ""}})

        # Propose the trade (legacy 2-party path) — chris sends a player, gets
        # partner's 2nd. Conditional pick upgrade: 2nd → 1st if I win cup.
        my_player_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        if not my_player_pick:
            pytest.skip("No pick on my team to send")

        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_player_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": partner_pick_id}],
            "message": "pick-upgrade pytest",
            "pick_upgrades": [{
                "pick_id": partner_pick_id,
                "new_round": 1,
                "condition": {
                    "subject_type": "team",
                    "subject": "offered",  # the proposer side = my team
                    "team_id": str(my["_id"]),
                    "metric": "won_championship",
                    "operator": "eq",
                    "threshold": 1,
                    "description": "If Zarek's Frozen wins the cup",
                },
                "description": "2nd → 1st if Zarek wins championship",
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        assert trade_id

        # Force-execute as co-comm (chris is co-comm in seed data)
        r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
        assert r.status_code == 200, r.text

        # Pick should NOT have been upgraded yet — championship not awarded
        pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
        assert pick["round"] == original_round, "Pick upgraded prematurely"
        # `current_team_id` is now mine
        assert pick["current_team_id"] == str(my["_id"])

        # Now toggle championship — must hit the awards endpoint as commish.
        # Promote chris to commissioner of this league for the call.
        original_commish = league.get("commissioner_id")
        await db.leagues.update_one(
            {"_id": ObjectId(lid)},
            {"$set": {"commissioner_id": me["id"]}},
        )

        try:
            r = await c.put(
                f"/api/leagues/{lid}/teams/{my['_id']}/awards",
                json={"championship_won": True}, headers=h,
            )
            assert r.status_code == 200, r.text
            award = r.json()
            assert award.get("pick_upgrades_applied", 0) >= 1, award

            # Pick is upgraded
            pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
            assert pick["round"] == 1, f"Pick should be R1 now, got R{pick['round']}"
            # trade_history has a pick_upgrade entry
            history = pick.get("trade_history") or []
            assert any(h.get("kind") == "pick_upgrade" and h.get("to_round") == 1
                       for h in history), f"No pick_upgrade entry: {history}"

            # audit_log has a pass row
            audit = await db.audit_log.find_one({
                "league_id": lid, "trade_id": trade_id,
                "action": "pick_upgrade_applied", "result": "pass",
            })
            assert audit, "Missing pass audit_log row"

            # Trade doc has applied_at on the upgrade entry
            t = await db.trades.find_one({"_id": ObjectId(trade_id)})
            up = t["pick_upgrades"][0]
            assert up.get("applied_at"), "applied_at not set on trade.pick_upgrades[0]"

            # Re-running should be a no-op (idempotent)
            r2 = await c.put(
                f"/api/leagues/{lid}/teams/{my['_id']}/awards",
                json={"championship_won": True}, headers=h,
            )
            assert r2.status_code == 200
            assert r2.json().get("pick_upgrades_applied", 0) == 0, "Should not re-apply"
        finally:
            # Cleanup: restore commish + roll the pick back (round/year AND owner)
            # so the test is idempotent across runs.
            if original_commish:
                await db.leagues.update_one(
                    {"_id": ObjectId(lid)},
                    {"$set": {"commissioner_id": original_commish}},
                )
            await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"championship_won_at": ""}})
            await db.draft_picks.update_one(
                {"_id": ObjectId(partner_pick_id)},
                {"$set": {
                    "round": original_round, "year": original_year,
                    "current_team_id": str(partner["_id"]),
                    "current_team_name": partner.get("name"),
                }},
            )


@pytest.mark.asyncio
async def test_pick_upgrade_with_player_condition_fires_on_threshold():
    """Player-subject pick upgrade — uses a direct player_id (resolves from
    DB regardless of trade side) and an always-true threshold to verify the
    full eval path works end-to-end."""
    from motor.motor_asyncio import AsyncIOMotorClient

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        h = {"Authorization": f"Bearer {tok}"}
        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        lid = leagues[0]["id"]

        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if t.get("name") == "Zarek's Frozen")
        partner = next(t for t in teams if t["_id"] != my["_id"])

        # 2nd-rounder owned by partner — they send it to me
        partner_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(partner["_id"]), "round": 2,
        })
        if not partner_pick:
            pytest.skip("No 2nd-round pick on partner")
        partner_pick_id = str(partner_pick["_id"])
        original_round = partner_pick["round"]
        original_year = partner_pick["year"]

        my_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        if not my_pick:
            pytest.skip("No pick on my team")

        # Find a player I own (will be the subject of the player condition)
        my_roster = my.get("roster") or []
        if not my_roster:
            pytest.skip("My team has no roster")
        subject_player_id = my_roster[0]

        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": partner_pick_id}],
            "pick_upgrades": [{
                "pick_id": partner_pick_id,
                "new_round": 1,
                "condition": {
                    "subject_type": "player",
                    "subject": "offered",
                    "player_id": subject_player_id,
                    "metric": "games_played",
                    "operator": "gte",
                    "threshold": 0,  # always true
                    "description": "If subject player has any games played",
                },
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")

        try:
            r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
            assert r.status_code == 200, r.text
            # Player-condition triggers immediately during _apply_pick_upgrades
            pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
            assert pick["round"] == 1, f"Expected R1 after player-condition trigger, got R{pick['round']}"
        finally:
            await db.draft_picks.update_one(
                {"_id": ObjectId(partner_pick_id)},
                {"$set": {
                    "round": original_round, "year": original_year,
                    "current_team_id": str(partner["_id"]),
                    "current_team_name": partner.get("name"),
                }},
            )


@pytest.mark.asyncio
async def test_pick_downgrade_clause_supported():
    """Round can also INCREASE (downgrade) — e.g., 'if my team misses
    playoffs, my 1st becomes a 2nd'."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        h = {"Authorization": f"Bearer {tok}"}
        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        me = (await c.get("/api/auth/me", headers=h)).json()
        lid = leagues[0]["id"]

        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if t.get("name") == "Zarek's Frozen")
        partner = next(t for t in teams if t["_id"] != my["_id"])

        # Find a 1st-round pick the partner owns — receiver = me, downgrade fires
        partner_first = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(partner["_id"]), "round": 1,
        })
        if not partner_first:
            pytest.skip("No 1st-round pick on partner")
        partner_pick_id = str(partner_first["_id"])
        original_round = partner_first["round"]
        original_year = partner_first["year"]

        my_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        if not my_pick:
            pytest.skip("No pick on my team")

        # Force the downgrade trigger to fire NOW: condition = team_wins >= 0
        # (always true since wins is non-negative).
        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": partner_pick_id}],
            "pick_upgrades": [{
                "pick_id": partner_pick_id,
                "new_round": 3,  # 1st → 3rd (downgrade)
                "condition": {
                    "subject_type": "team",
                    "subject": "offered",
                    "team_id": str(my["_id"]),
                    "metric": "team_wins",
                    "operator": "gte",
                    "threshold": 0,
                },
                "description": "1st → 3rd",
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        try:
            r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
            assert r.status_code == 200

            # Should fire immediately during _apply_pick_upgrades(final_eval=False)
            pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
            assert pick["round"] == 3, f"Pick should have downgraded to R3, got R{pick['round']}"
        finally:
            await db.draft_picks.update_one(
                {"_id": ObjectId(partner_pick_id)},
                {"$set": {
                    "round": original_round, "year": original_year,
                    "current_team_id": str(partner["_id"]),
                    "current_team_name": partner.get("name"),
                }},
            )

"""Pick upgrade engine: a 2-team trade with a `pick_upgrades` clause that
fires on `won_championship`. Tests the `_apply_pick_upgrades` helper directly
and via the award-toggle re-eval hook surfaced through PUT /awards endpoint."""
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
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


@pytest_asyncio.fixture(autouse=True)
async def _restore_my_picks():
    """Some upstream tests leave Zarek's Frozen with no picks. Reset every
    pick whose ORIGINAL_TEAM is Zarek's Frozen back to that team unless it
    has a real trade_history (i.e. was traded outside this test). This keeps
    the suite idempotent without cleaning up other tests' real moves."""
    from motor.motor_asyncio import AsyncIOMotorClient as _M
    db = _M(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    me = await db.teams.find_one({"name": "Zarek's Frozen"}, {"_id": 1, "league_id": 1})
    if me:
        await db.draft_picks.update_many(
            {
                "league_id": me["league_id"],
                "original_team_id": str(me["_id"]),
                "current_team_id": {"$ne": str(me["_id"])},
                "$or": [
                    {"trade_history": {"$exists": False}},
                    {"trade_history": []},
                ],
            },
            {"$set": {
                "current_team_id": str(me["_id"]),
                "current_team_name": "Zarek's Frozen",
            }},
        )
    yield


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _accept_fixture_trade(db, trade_id):
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    target = await db.users.find_one({"_id": ObjectId(trade["target_owner_id"])})
    password = os.environ["ADMIN_PASSWORD"] if target["email"] == os.environ["ADMIN_EMAIL"] else "e2e-member-password"
    async with AsyncClient(base_url=BASE, timeout=30) as recipient:
        token = await _login(recipient, target["email"], password)
        response = await recipient.post(f"/api/trades/{trade_id}/respond", json={"action": "accept"}, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_pick_upgrade_applies_when_championship_unlocks():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}

        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        me = (await c.get("/api/auth/me", headers=h)).json()
        league = leagues[0]
        lid = league["id"]

        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))
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
        await _accept_fixture_trade(db, trade_id)
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
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}
        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        lid = leagues[0]["id"]

        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))
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
            await _accept_fixture_trade(db, trade_id)
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
async def test_pick_protection_fires_when_pick_lands_top_n():
    """Pick-protection conditional: if the pick's slot is top-3, the trigger
    fires and the pick is rewritten (typical use: lottery-protected 1sts)."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}
        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        lid = leagues[0]["id"]

        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))

        # Find any R1 pick currently owned by ANY non-me team — the test data
        # gets shuffled by earlier runs, so don't pin to a specific partner.
        partner_pick = await db.draft_picks.find_one({
            "league_id": lid,
            "round": 1,
            "current_team_id": {"$ne": str(my["_id"])},
        })
        if not partner_pick:
            pytest.skip("No 1st-round pick on a partner team")
        partner = next(t for t in teams if str(t["_id"]) == partner_pick["current_team_id"])
        partner_pick_id = str(partner_pick["_id"])
        original_round = partner_pick["round"]
        original_year = partner_pick["year"]
        original_pick_number = partner_pick.get("pick_number")
        # Stamp the pick with a top-2 slot so the protection triggers
        await db.draft_picks.update_one(
            {"_id": ObjectId(partner_pick_id)},
            {"$set": {"pick_number": 2}},
        )

        my_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        if not my_pick:
            pytest.skip("No pick on my team")

        # Protection: if the pick lands top-3, downgrade it to a 4th (i.e.,
        # essentially neutered — a typical NHL-style protection rule).
        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": partner_pick_id}],
            "pick_upgrades": [{
                "pick_id": partner_pick_id,
                "new_round": 4,
                "condition": {
                    "subject_type": "pick",
                    "subject": "requested",
                    "pick_id": partner_pick_id,
                    "metric": "pick_slot",
                    "operator": "lte",
                    "threshold": 3,
                    "description": "If pick lands top-3 (lottery protection)",
                },
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        assert trade_id, f"No trade id in response: {body}"
        try:
            await _accept_fixture_trade(db, trade_id)
            r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
            assert r.status_code == 200
            pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
            assert pick["round"] == 4, f"Top-3 protection should have downgraded pick to R4, got R{pick['round']}"
        finally:
            reset = {
                "round": original_round, "year": original_year,
                "current_team_id": str(partner["_id"]),
                "current_team_name": partner.get("name"),
            }
            if original_pick_number is None:
                await db.draft_picks.update_one(
                    {"_id": ObjectId(partner_pick_id)},
                    {"$set": reset, "$unset": {"pick_number": ""}},
                )
            else:
                reset["pick_number"] = original_pick_number
                await db.draft_picks.update_one(
                    {"_id": ObjectId(partner_pick_id)},
                    {"$set": reset},
                )


@pytest.mark.asyncio
async def test_won_draft_lottery_team_metric_evaluates():
    """Team-level `won_draft_lottery` metric reads `draft_lottery_won_at`."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}
        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        lid = leagues[0]["id"]
        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))
        partner_pick = await db.draft_picks.find_one({
            "league_id": lid, "round": 2,
            "current_team_id": {"$ne": str(my["_id"])},
        })
        if not partner_pick:
            pytest.skip("No 2nd-round pick on a partner team")
        partner = next(t for t in teams if str(t["_id"]) == partner_pick["current_team_id"])
        partner_pick_id = str(partner_pick["_id"])
        original_round = partner_pick["round"]
        original_year = partner_pick["year"]
        my_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        if not my_pick:
            pytest.skip("No pick on my team")

        await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"draft_lottery_won_at": ""}})

        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": partner_pick_id}],
            "pick_upgrades": [{
                "pick_id": partner_pick_id,
                "new_round": 1,
                "condition": {
                    "subject_type": "team",
                    "subject": "offered",
                    "team_id": str(my["_id"]),
                    "metric": "won_draft_lottery",
                    "operator": "eq",
                    "threshold": 1,
                    "description": "If my team wins the draft lottery",
                },
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        assert trade_id, f"No trade id in response: {body}"
        try:
            await _accept_fixture_trade(db, trade_id)
            await c.post(f"/api/trades/{trade_id}/execute", headers=h)
            # Pre-lottery: pick stays as 2nd
            pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
            assert pick["round"] == 2, "Should stay R2 before lottery"

            # Toggle the lottery flag on my team
            await db.teams.update_one(
                {"_id": my["_id"]},
                {"$set": {"draft_lottery_won_at": datetime.now(timezone.utc)}},
            )

            # Bind the direct evaluator to this test's live disposable DB.
            from services import trade_engine
            previous_deps = dict(trade_engine._deps)
            trade_engine.setup({"db": db})
            try:
                t = await db.trades.find_one({"_id": ObjectId(trade_id)})
                res = await trade_engine._apply_pick_upgrades(t, final_eval=False)
            finally:
                trade_engine._deps.clear()
                trade_engine._deps.update(previous_deps)
            assert res["applied"] >= 1, res
            pick = await db.draft_picks.find_one({"_id": ObjectId(partner_pick_id)})
            assert pick["round"] == 1, f"Lottery win should upgrade pick to R1, got R{pick['round']}"
        finally:
            await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"draft_lottery_won_at": ""}})
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
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}
        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        me = (await c.get("/api/auth/me", headers=h)).json()
        lid = leagues[0]["id"]

        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))
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
            await _accept_fixture_trade(db, trade_id)
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



@pytest.mark.asyncio
async def test_pick_upgrade_action_add_transfers_ownership_on_trigger():
    """Action='add': pick is NOT in the trade. When championship triggers,
    pick ownership transfers from sender (partner) to receiver (me)."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}

        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        league = leagues[0]
        lid = league["id"]

        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))
        partner = next(t for t in teams if t["_id"] != my["_id"])

        # Pick that the partner currently owns and that is NOT going to be
        # included in the trade today — only added if the condition fires.
        future_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(partner["_id"]), "round": 4,
        })
        if not future_pick:
            pytest.skip("No 4th-round pick on partner team")
        future_pick_id = str(future_pick["_id"])
        original_owner = str(partner["_id"])

        # Token assets so the trade has at least one asset on each side
        my_player_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        partner_real_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(partner["_id"]),
            "_id": {"$ne": ObjectId(future_pick_id)},
        })
        if not my_player_pick or not partner_real_pick:
            pytest.skip("Insufficient picks for setup")

        await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"championship_won_at": ""}})

        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_player_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": str(partner_real_pick["_id"])}],
            "message": "add-pick pytest",
            "pick_upgrades": [{
                "pick_id": future_pick_id,
                "action": "add",
                "from_team_id": str(partner["_id"]),
                "to_team_id": str(my["_id"]),
                "condition": {
                    "subject_type": "team",
                    "subject": "offered",
                    "team_id": str(my["_id"]),
                    "metric": "won_championship",
                    "operator": "eq", "threshold": 1,
                    "description": "If Zarek wins championship",
                },
                "description": "Add 4th-round pick on championship",
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        if not trade_id:
            pytest.skip(f"trade response missing id: {body}")
        assert trade_id

        await _accept_fixture_trade(db, trade_id)
        r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
        assert r.status_code == 200, r.text

        # The "add" pick must NOT have moved yet (no championship)
        pick = await db.draft_picks.find_one({"_id": ObjectId(future_pick_id)})
        assert pick["current_team_id"] == original_owner, "Pick moved prematurely"

        # Toggle championship — promote chris to commissioner first
        original_commish = league.get("commissioner_id")
        await db.leagues.update_one(
            {"_id": ObjectId(lid)},
            {"$set": {"commissioner_id": str(my["_id"])}},
        )
        try:
            r = await c.put(
                f"/api/leagues/{lid}/teams/{my['_id']}/awards",
                json={"championship_won": True}, headers=h,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("pick_upgrades_applied", 0) >= 1

            # The "add" pick now belongs to me
            pick = await db.draft_picks.find_one({"_id": ObjectId(future_pick_id)})
            assert pick["current_team_id"] == str(my["_id"]), \
                f"Expected pick owned by me, got {pick['current_team_id']}"
            history = pick.get("trade_history") or []
            assert any(h.get("kind") == "pick_added" for h in history), \
                f"Missing pick_added trade_history: {history}"

            # Audit + trade doc updated
            audit = await db.audit_log.find_one({
                "league_id": lid, "trade_id": trade_id,
                "action": "pick_upgrade_add_applied", "result": "pass",
            })
            assert audit, "Missing audit_log row"
            t = await db.trades.find_one({"_id": ObjectId(trade_id)})
            assert t["pick_upgrades"][0].get("applied_at"), "trade upgrade not marked applied"
        finally:
            if original_commish:
                await db.leagues.update_one(
                    {"_id": ObjectId(lid)},
                    {"$set": {"commissioner_id": original_commish}},
                )
            await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"championship_won_at": ""}})
            # Restore pick ownership
            await db.draft_picks.update_one(
                {"_id": ObjectId(future_pick_id)},
                {"$set": {
                    "current_team_id": original_owner,
                    "current_team_name": partner.get("name"),
                }},
            )


@pytest.mark.asyncio
async def test_pick_upgrade_action_remove_reverts_ownership_on_trigger():
    """Action='remove': pick IS in the trade and transfers at execution.
    When the condition fires, ownership reverts back to the original sender."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        h = {"Authorization": f"Bearer {tok}"}

        leagues = (await c.get("/api/leagues?my_leagues=true", headers=h)).json()
        league = leagues[0]
        lid = league["id"]

        me = (await c.get("/api/auth/me", headers=h)).json()
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        my = next(t for t in teams if str(t.get("owner_id")) == str(me["id"]))
        partner = next(t for t in teams if t["_id"] != my["_id"])

        # Pick that the partner sends to me as part of this trade. If
        # championship triggers, it reverts back to partner.
        traded_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(partner["_id"]), "round": 5,
        })
        if not traded_pick:
            pytest.skip("No 5th-round pick on partner team")
        traded_pick_id = str(traded_pick["_id"])
        original_owner = str(partner["_id"])
        original_round = traded_pick["round"]
        original_year = traded_pick["year"]

        my_pick = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(my["_id"]),
        })
        if not my_pick:
            pytest.skip("No pick on my team to send")

        await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"championship_won_at": ""}})

        payload = {
            "league_id": lid,
            "target_team_id": str(partner["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": traded_pick_id}],
            "message": "remove-pick pytest",
            "pick_upgrades": [{
                "pick_id": traded_pick_id,
                "action": "remove",
                "from_team_id": str(my["_id"]),     # current holder after execution
                "to_team_id": original_owner,        # revert target = original owner
                "condition": {
                    "subject_type": "team",
                    "subject": "offered",
                    "team_id": str(my["_id"]),
                    "metric": "won_championship",
                    "operator": "eq", "threshold": 1,
                    "description": "If Zarek wins championship, return pick",
                },
                "description": "Revert 5th-round pick on championship",
            }],
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        if not trade_id:
            pytest.skip(f"trade response missing id: {body}")
        assert trade_id

        await _accept_fixture_trade(db, trade_id)
        r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
        assert r.status_code == 200, r.text

        # Pick is now mine post-execution
        pick = await db.draft_picks.find_one({"_id": ObjectId(traded_pick_id)})
        assert pick["current_team_id"] == str(my["_id"]), "Pick should be mine post-execution"

        # Toggle championship
        original_commish = league.get("commissioner_id")
        await db.leagues.update_one(
            {"_id": ObjectId(lid)},
            {"$set": {"commissioner_id": str(my["_id"])}},
        )
        try:
            r = await c.put(
                f"/api/leagues/{lid}/teams/{my['_id']}/awards",
                json={"championship_won": True}, headers=h,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("pick_upgrades_applied", 0) >= 1

            # Pick reverts to original owner
            pick = await db.draft_picks.find_one({"_id": ObjectId(traded_pick_id)})
            assert pick["current_team_id"] == original_owner, \
                f"Pick should have reverted, current owner: {pick['current_team_id']}"
            history = pick.get("trade_history") or []
            assert any(h.get("kind") == "pick_removed" for h in history), \
                f"Missing pick_removed history: {history}"

            audit = await db.audit_log.find_one({
                "league_id": lid, "trade_id": trade_id,
                "action": "pick_upgrade_remove_applied", "result": "pass",
            })
            assert audit
        finally:
            if original_commish:
                await db.leagues.update_one(
                    {"_id": ObjectId(lid)},
                    {"$set": {"commissioner_id": original_commish}},
                )
            await db.teams.update_one({"_id": my["_id"]}, {"$unset": {"championship_won_at": ""}})
            await db.draft_picks.update_one(
                {"_id": ObjectId(traded_pick_id)},
                {"$set": {
                    "round": original_round, "year": original_year,
                    "current_team_id": original_owner,
                    "current_team_name": partner.get("name"),
                }},
            )

@pytest.fixture(scope="module", autouse=True)
def conditional_trade_inputs(_global_pollution_sweep):
    from pymongo import MongoClient
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        for league in db.leagues.find({"_suite_baseline": True}):
            db.leagues.update_one({"_id": league["_id"]}, {"$set": {"transactions_config.trades.conditional_trades_enabled": True}})

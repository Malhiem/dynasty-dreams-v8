"""End-to-end test for trade execution: players, picks, salary retention, conditions.
Run: cd /app/backend && python3 test_trade_flow.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ.get("REACT_APP_BACKEND_URL_OVERRIDE") or "http://localhost:8001"
API = f"{BASE}/api"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Login as chriszarek to get cookie
    async with httpx.AsyncClient(follow_redirects=True) as http:
        login = await http.post(f"{API}/auth/login",
                                 json={"email": "chriszarek@gmail.com", "password": "Chris2026!"})
        assert login.status_code == 200, f"login failed {login.status_code} {login.text}"
        cookies = {**login.cookies}

        # Pick the Ice Kings league and chriszarek's team
        u = await db.users.find_one({"email": "chriszarek@gmail.com"})
        me_id = str(u["_id"])
        league = await db.leagues.find_one({"name": "Ice Kings Head-to-Head"})
        lid = str(league["_id"])
        my_team = await db.teams.find_one({"league_id": lid, "owner_id": me_id})
        other = await db.teams.find_one({"league_id": lid, "owner_id": {"$ne": me_id}})

        print(f"Me team:    {my_team['name']} ({my_team['_id']})")
        print(f"Other team: {other['name']} ({other['_id']})")

        my_player = my_team["roster"][0]
        their_player = other["roster"][0]
        print(f"My player:  {my_player}")
        print(f"Their player: {their_player}")

        # Find any pick still owned by each (idempotent across re-runs)
        my_pick = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(my_team["_id"])})
        their_pick = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(other["_id"])})
        assert my_pick and their_pick, "Need at least one pick on each side"
        print(f"My pick:    {my_pick['year']} R{my_pick['round']} id={my_pick['_id']}")
        print(f"Their pick: {their_pick['year']} R{their_pick['round']} id={their_pick['_id']}")

        # ─── Test 1: Trade with player + pick + salary retention ───
        payload = {
            "league_id": lid,
            "target_team_id": str(other["_id"]),
            "assets_offered": [
                {"asset_type": "player", "player_id": my_player, "salary_retained_pct": 25},
                {"asset_type": "pick", "pick_id": str(my_pick["_id"])},
            ],
            "assets_requested": [
                {"asset_type": "player", "player_id": their_player},
                {"asset_type": "pick", "pick_id": str(their_pick["_id"])},
            ],
            "message": "Testing trade flow",
        }
        r = await http.post(f"{API}/trades", json=payload, cookies=cookies)
        assert r.status_code == 200, f"proposal failed {r.status_code} {r.text}"
        trade = r.json()
        trade_id = trade["_id"]
        print(f"\n✔ Proposed trade {trade_id}")

        # Accept & execute trade via co-commissioner path
        from bson import ObjectId
        await db.trades.update_one({"_id": ObjectId(trade_id)},
                                    {"$set": {"status": "accepted"}})
        r2 = await http.post(f"{API}/trades/{trade_id}/execute", cookies=cookies)
        print(f"Execute (as co-comm): {r2.status_code} {r2.json() if r2.status_code == 200 else r2.text}")
        assert r2.status_code == 200 and r2.json().get("executed"), f"Execute failed: {r2.text}"

        # Verify rosters changed
        my_team2 = await db.teams.find_one({"_id": my_team["_id"]})
        other2 = await db.teams.find_one({"_id": other["_id"]})
        assert my_player not in my_team2["roster"], "My player still on my roster!"
        assert my_player in other2["roster"], "My player not received by other team!"
        assert their_player in my_team2["roster"], "Their player not received by me!"
        assert their_player not in other2["roster"], "Their player still on other team!"
        print("✔ Players swapped correctly")

        # Verify picks changed
        my_pick2 = await db.draft_picks.find_one({"_id": my_pick["_id"]})
        their_pick2 = await db.draft_picks.find_one({"_id": their_pick["_id"]})
        assert my_pick2["current_team_id"] == str(other["_id"]), "My pick didn't transfer"
        assert their_pick2["current_team_id"] == str(my_team["_id"]), "Their pick didn't transfer"
        print("✔ Picks transferred correctly")

        # Verify salary retention
        ret = await db.salary_retentions.find_one({"league_id": lid, "player_id": my_player})
        assert ret and ret["pct"] == 25, f"Salary retention not persisted: {ret}"
        print("✔ Salary retention stored")

        # ─── Test 2: Conditional trade (auto-execute when condition met) ───
        # Pick a superstar with >= 100 NHL points
        bon_player = my_team2["roster"][1]
        bon_doc = await db.players.find_one({"_id": ObjectId(bon_player)})
        other_player2 = other2["roster"][1]
        payload2 = {
            "league_id": lid,
            "target_team_id": str(other["_id"]),
            "assets_offered": [{"asset_type": "player", "player_id": bon_player}],
            "assets_requested": [{"asset_type": "player", "player_id": other_player2}],
            "conditions": [
                {"subject": "offered", "player_id": bon_player, "metric": "nhl_points",
                 "operator": "gte", "threshold": max(1, (bon_doc.get("points", 0) - 5))},
            ],
        }
        r3 = await http.post(f"{API}/trades", json=payload2, cookies=cookies)
        assert r3.status_code == 200, f"conditional proposal failed {r3.status_code} {r3.text}"
        trade_id2 = r3.json()["_id"]
        print(f"\n✔ Proposed conditional trade {trade_id2}")

        # Evaluate conditions
        r4 = await http.post(f"{API}/trades/{trade_id2}/evaluate-conditions")
        eval_res = r4.json()
        print(f"✔ Evaluate conditions: all_met={eval_res['all_met']}")
        assert eval_res["all_met"] is True, f"Expected condition met: {eval_res}"

        # Execute conditional trade (chriszarek is co-comm so can execute)
        r5 = await http.post(f"{API}/trades/{trade_id2}/execute", cookies=cookies)
        print(f"✔ Executed conditional trade: {r5.json()}")
        assert r5.json().get("executed") is True

        # ─── Test 3: Condition NOT met ───
        payload3 = {
            "league_id": lid,
            "target_team_id": str(other["_id"]),
            "assets_offered": [{"asset_type": "player", "player_id": my_team2["roster"][2]}],
            "assets_requested": [{"asset_type": "player", "player_id": other2["roster"][2]}],
            "conditions": [
                {"subject": "offered", "metric": "nhl_points", "operator": "gte", "threshold": 99999},
            ],
        }
        r6 = await http.post(f"{API}/trades", json=payload3, cookies=cookies)
        trade_id3 = r6.json()["_id"]
        r7 = await http.post(f"{API}/trades/{trade_id3}/execute", cookies=cookies)
        data7 = r7.json()
        print(f"✔ Unmet condition trade: executed={data7.get('executed')}, reason={data7.get('reason')}")
        assert data7.get("executed") is False and data7.get("reason") == "conditions_not_met"

        # ─── Test 4: Team-level condition — 'won_championship' on my team ───
        from bson import ObjectId
        # Case A: team has NOT won championship → condition not met
        # Grab a fresh pick from each side for this test
        my_pick_b = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(my_team["_id"])})
        their_pick_b = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(other["_id"])})
        payload4 = {
            "league_id": lid,
            "target_team_id": str(other["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick_b["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": str(their_pick_b["_id"])}],
            "conditions": [
                {"subject_type": "team", "subject": "offered", "metric": "won_championship",
                 "operator": "eq", "threshold": 1, "description": "Only if my team wins championship"},
            ],
        }
        r8 = await http.post(f"{API}/trades", json=payload4, cookies=cookies)
        trade_id4 = r8.json()["_id"]
        r9 = await http.post(f"{API}/trades/{trade_id4}/execute", cookies=cookies)
        assert r9.json().get("executed") is False, f"Expected blocked: {r9.json()}"
        print(f"✔ Team condition (no championship): blocked correctly")

        # Case B: mark my team as championship winner → should unlock
        await db.teams.update_one(
            {"_id": ObjectId(str(my_team["_id"]))},
            {"$set": {"championship_won_at": datetime.now(timezone.utc)}}
        )
        # Re-fetch conditions evaluation
        r10 = await http.post(f"{API}/trades/{trade_id4}/evaluate-conditions")
        eval4 = r10.json()
        assert eval4["all_met"] is True, f"Expected met: {eval4}"
        print(f"✔ Team condition (after championship flag): met")

        # Execute it — now should succeed
        r11 = await http.post(f"{API}/trades/{trade_id4}/execute", cookies=cookies)
        assert r11.json().get("executed") is True
        print(f"✔ Team condition unlocked trade execution")

        # Undo championship for clean state
        await db.teams.update_one(
            {"_id": ObjectId(str(my_team["_id"]))},
            {"$unset": {"championship_won_at": ""}}
        )

        # ─── Test 5: Pick trade_history persisted ───
        p_after = await db.draft_picks.find_one({"_id": my_pick["_id"]})
        hist = (p_after or {}).get("trade_history", []) if p_after else []
        assert len(hist) >= 1, f"Expected at least 1 trade_history entry on my_pick: {hist}"
        print(f"✔ my_pick trade_history length: {len(hist)} entries")
        for h in hist[:3]:
            print(f"    {h['from_team_name']} → {h['to_team_name']}")
        print()
        print("🎉 ALL TRADE FLOW TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

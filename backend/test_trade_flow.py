"""End-to-end test for trade execution: players, picks, salary retention, conditions.
Run: cd /app/backend && python3 test_trade_flow.py
"""
import asyncio
import os
import sys
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

        # Find a pick owned by each
        my_pick = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(my_team["_id"]), "year": 2027, "round": 2})
        their_pick = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(other["_id"]), "year": 2028, "round": 3})
        print(f"My pick:    2027 R2 id={my_pick['_id']}")
        print(f"Their pick: 2028 R3 id={their_pick['_id']}")

        # ─── Test 1: Trade with player + pick + salary retention ───
        payload = {
            "league_id": lid,
            "target_team_id": str(other["_id"]),
            "assets_offered": [
                {"asset_type": "player", "player_id": my_player, "salary_retained_pct": 25},
                {"asset_type": "pick", "pick_year": 2027, "pick_round": "2"},
            ],
            "assets_requested": [
                {"asset_type": "player", "player_id": their_player},
                {"asset_type": "pick", "pick_year": 2028, "pick_round": "3"},
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

        print("\n🎉 ALL TRADE FLOW TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

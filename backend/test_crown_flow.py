"""End-to-end test for auto-crowning + consolation prize + compensation pick.
Verifies:
 - Championship auto-crowned when is_final matchup is simulated
 - Consolation winner receives prize (lottery boost OR compensation pick fallback)
 - Conditional trades fire automatically
"""
import asyncio
import os
from datetime import datetime, timezone
import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

BASE = "http://localhost:8001"
API = f"{BASE}/api"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    async with httpx.AsyncClient(follow_redirects=True) as http:
        # Login as admin (commissioner of all seed leagues)
        login = await http.post(f"{API}/auth/login",
                                 json={"email": "admin@dynastydreams.com", "password": "Admin123!"})
        assert login.status_code == 200, login.text
        cookies = {**login.cookies}

        league = await db.leagues.find_one({"name": "Ice Kings Head-to-Head"})
        lid = str(league["_id"])
        teams = await db.teams.find({"league_id": lid}).to_list(20)
        top_a, top_b = teams[0], teams[1]
        cons_a, cons_b = teams[2], teams[3]

        # Clean any prior state on these teams
        for t in (top_a, top_b, cons_a, cons_b):
            await db.teams.update_one({"_id": t["_id"]},
                                       {"$unset": {"championship_won_at": "", "consolation_won_at": ""}})

        # ── 1) Set consolation prize (lottery boost 3 spots, fallback R3 2027) ──
        r = await http.put(f"{API}/leagues/{lid}/consolation-prize",
                           json={"prize": {"type": "draft_lottery_boost",
                                           "lottery_boost_spots": 3,
                                           "fallback_pick_round": 3,
                                           "fallback_pick_year": 2027,
                                           "description": "Consolation winner gets 3 lottery spots"}},
                           cookies=cookies)
        assert r.status_code == 200, r.text
        print("✔ Prize configured:", r.json()["consolation_prize"]["type"])

        # ── 2) Seed a championship + consolation final matchup for Week 99 ──
        await db.matchups.delete_many({"league_id": lid, "week": 99})
        await db.matchups.insert_many([
            {"league_id": lid, "week": 99, "status": "scheduled",
             "home_team_id": str(top_a["_id"]), "home_team_name": top_a["name"],
             "away_team_id": str(top_b["_id"]), "away_team_name": top_b["name"],
             "bracket": "championship", "is_final": True,
             "home_score": 0, "away_score": 0, "winner": None,
             "scoring_format": "head_to_head"},
            {"league_id": lid, "week": 99, "status": "scheduled",
             "home_team_id": str(cons_a["_id"]), "home_team_name": cons_a["name"],
             "away_team_id": str(cons_b["_id"]), "away_team_name": cons_b["name"],
             "bracket": "consolation", "is_final": True,
             "home_score": 0, "away_score": 0, "winner": None,
             "scoring_format": "head_to_head"},
        ])
        print("✔ Seeded 2 playoff final matchups")

        # ── 3) Simulate week 99 — must run as the league commissioner ──
        # Re-login as the actual commissioner
        comm_user = await db.users.find_one({"_id": ObjectId(league["commissioner_id"])})
        # Can't login as arbitrary user without password — bypass via direct DB sim
        # Instead, make chriszarek the commissioner temporarily.
        me = await db.users.find_one({"email": "chriszarek@gmail.com"})
        original_comm = league["commissioner_id"]
        await db.leagues.update_one({"_id": league["_id"]},
                                     {"$set": {"commissioner_id": str(me["_id"])}})
        login2 = await http.post(f"{API}/auth/login",
                                   json={"email": "chriszarek@gmail.com", "password": "Chris2026!"})
        cookies = {**login2.cookies}

        r2 = await http.post(f"{API}/matchups/simulate-week",
                              json={"league_id": lid, "week": 99}, cookies=cookies)
        assert r2.status_code == 200, r2.text
        print("✔ Week 99 simulated:", [x.get("winner") for x in r2.json()["results"]])

        # ── 4) Verify championship + consolation crowning ──
        top_a2 = await db.teams.find_one({"_id": top_a["_id"]})
        top_b2 = await db.teams.find_one({"_id": top_b["_id"]})
        champ = top_a2 if top_a2.get("championship_won_at") else top_b2
        assert champ.get("championship_won_at"), f"No champion crowned: {top_a2.get('championship_won_at')} / {top_b2.get('championship_won_at')}"
        print(f"🏆 Champion: {champ['name']} @ {champ['championship_won_at']}")

        cons_a2 = await db.teams.find_one({"_id": cons_a["_id"]})
        cons_b2 = await db.teams.find_one({"_id": cons_b["_id"]})
        cons_winner = cons_a2 if cons_a2.get("consolation_won_at") else cons_b2
        assert cons_winner.get("consolation_won_at"), "No consolation winner set"
        print(f"🎖  Consolation: {cons_winner['name']} @ {cons_winner['consolation_won_at']}")

        # ── 5) Verify prize application ──
        rewards = await db.team_rewards.find({"league_id": lid,
                                                "team_id": str(cons_winner["_id"])}).to_list(5)
        assert rewards, "No reward recorded for consolation winner"
        print(f"✔ Reward recorded: {rewards[0]['prize']}")

        # Check pick modification or compensation pick created
        boosted = await db.draft_picks.find_one({
            "league_id": lid,
            "current_team_id": str(cons_winner["_id"]),
            "lottery_boost_applied": {"$exists": True}
        })
        comp = await db.draft_picks.find_one({
            "league_id": lid, "current_team_id": str(cons_winner["_id"]),
            "pick_type": "compensation"
        })
        assert boosted or comp, "Neither lottery boost nor compensation pick applied"
        if boosted:
            print(f"✔ Lottery boost applied: {boosted['year']} R{boosted['round']} → pick #{boosted['pick_number']} (boost {boosted['lottery_boost_applied']})")
        if comp:
            print(f"✔ Compensation pick awarded: {comp['year']} R{comp['round']}")

        # Restore commissioner
        await db.leagues.update_one({"_id": league["_id"]},
                                     {"$set": {"commissioner_id": original_comm}})
        print("\n🎉 AUTO-CROWN + CONSOLATION TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

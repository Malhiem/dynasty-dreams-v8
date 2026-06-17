"""Iter 170f — Seed a demo "trade for picks" inside the Ice Kings
Head-to-Head league so the user can validate that pick ownership +
provenance overlays render correctly on:
  • Draft Room (Draft Board column heading + tooltip chip)
  • Roster page (Future Draft Picks card)
  • Transactions page (executed trade row)

The trade swaps:
  • Zarek's Frozen        →  Ice Breakers     :  2026 Round 2 pick
  • Ice Breakers          →  Zarek's Frozen   :  2026 Round 3 pick

Runs idempotently — skips if a comparable trade is already executed.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv("/app/backend/.env")

LEAGUE_ID = "69e46af167999bfb85c39628"
ZAREK_TEAM_ID = "69e59b30cbd3fea02a914c61"     # Zarek's Frozen
ICE_TEAM_ID = "69e59b32cbd3fea02a914c62"        # Ice Breakers (best guess)


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Resolve Ice Breakers' actual team_id from name (more robust than guessing).
    ice = await db.teams.find_one({"league_id": LEAGUE_ID, "name": "Ice Breakers"})
    assert ice, "Ice Breakers team not found in Ice Kings league"
    ice_id = str(ice["_id"])
    zarek = await db.teams.find_one({"league_id": LEAGUE_ID, "name": "Zarek's Frozen"})
    assert zarek, "Zarek's Frozen team not found"
    zarek_id = str(zarek["_id"])
    print(f"Zarek's Frozen: {zarek_id}")
    print(f"Ice Breakers:   {ice_id}")

    # Find the picks to swap.
    pick_a = await db.draft_picks.find_one({
        "league_id": LEAGUE_ID, "year": 2026, "round": 2,
        "original_team_id": zarek_id,
    })
    pick_b = await db.draft_picks.find_one({
        "league_id": LEAGUE_ID, "year": 2026, "round": 3,
        "original_team_id": ice_id,
    })
    assert pick_a, "Zarek's 2026 R2 pick not found"
    assert pick_b, "Ice Breakers' 2026 R3 pick not found"

    # Idempotency — bail if either pick already changed hands.
    if (pick_a.get("current_team_id") != zarek_id
            or pick_b.get("current_team_id") != ice_id):
        print("Picks already traded — skipping (idempotent re-run).")
        return

    now = datetime.now(timezone.utc).isoformat()

    # Apply pick ownership transfers + trade_history annotations.
    await db.draft_picks.update_one(
        {"_id": pick_a["_id"]},
        {
            "$set": {"current_team_id": ice_id},
            "$push": {"trade_history": {
                "from_team_id": zarek_id, "to_team_id": ice_id,
                "at": now, "via": "iter170f_demo",
            }},
        },
    )
    await db.draft_picks.update_one(
        {"_id": pick_b["_id"]},
        {
            "$set": {"current_team_id": zarek_id},
            "$push": {"trade_history": {
                "from_team_id": ice_id, "to_team_id": zarek_id,
                "at": now, "via": "iter170f_demo",
            }},
        },
    )
    print("Picks rotated.")

    # Record an executed trade so the Transactions page reflects it.
    trade_doc = {
        "league_id": LEAGUE_ID,
        "proposer_team_id": zarek_id,
        "target_team_id": ice_id,
        "status": "accepted",
        "executed_at": now,
        "created_at": now,
        "assets_offered": [{
            "asset_type": "pick",
            "pick_id": str(pick_a["_id"]),
            "pick_year": pick_a["year"],
            "pick_round": pick_a["round"],
            "name": f"{pick_a['year']} Round {pick_a['round']} Pick",
        }],
        "assets_requested": [{
            "asset_type": "pick",
            "pick_id": str(pick_b["_id"]),
            "pick_year": pick_b["year"],
            "pick_round": pick_b["round"],
            "name": f"{pick_b['year']} Round {pick_b['round']} Pick",
        }],
        "note": "Iter 170f demo — swap of 2026 R2 (Zarek) for 2026 R3 (Ice Breakers)",
    }
    res = await db.trades.insert_one(trade_doc)
    print(f"Trade recorded: {res.inserted_id}")


if __name__ == "__main__":
    asyncio.run(main())

"""Iter 170o — Seed real 2026 NHL Draft-eligible prospects into the
`players` collection with `player_type: "prospect"` so entry drafts
have something to pull from. Idempotent — re-runs are safe.

Source: NHL Central Scouting Final Ranking (Feb 2026, top 30 N. American
+ European skaters and goalies). Names + age + amateur league are real;
stats are synthetic but plausible so the eligible-players ordering
(by points DESC) gives a sensible default ranking.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

PROSPECTS = [
    # name, position, age, league, gp, g, a, pts
    ("Gavin McKenna", "LW", 18, "WHL · Medicine Hat", 62, 41, 88, 129),
    ("Michael Misa", "C", 18, "OHL · Saginaw", 65, 62, 72, 134),
    ("James Hagens", "C", 18, "NCAA · Boston College", 38, 11, 26, 37),
    ("Porter Martone", "RW", 18, "OHL · Brampton", 57, 29, 49, 78),
    ("Brady Martin", "C", 18, "OHL · Sault Ste. Marie", 57, 33, 39, 72),
    ("Anton Frondell", "C", 17, "HockeyAllsvenskan · Djurgården", 29, 11, 14, 25),
    ("Caleb Desnoyers", "C", 18, "QMJHL · Moncton", 56, 35, 49, 84),
    ("Roger McQueen", "C", 18, "WHL · Brandon", 17, 10, 10, 20),
    ("Victor Eklund", "LW", 18, "HockeyAllsvenskan · Djurgården", 42, 19, 12, 31),
    ("Lynden Lakovic", "LW", 18, "WHL · Moose Jaw", 47, 27, 31, 58),
    ("Carter Bear", "LW", 18, "WHL · Everett", 56, 40, 42, 82),
    ("Jake O'Brien", "C", 18, "OHL · Brantford", 66, 32, 66, 98),
    ("Cole Reschny", "C", 18, "WHL · Victoria", 62, 26, 66, 92),
    ("Cullen Potter", "C", 18, "NCAA · Arizona State", 35, 13, 9, 22),
    ("Kashawn Aitcheson", "D", 18, "OHL · Barrie", 64, 26, 33, 59),
    ("Radim Mrtka", "D", 18, "WHL · Seattle", 43, 3, 32, 35),
    ("Jackson Smith", "D", 18, "WHL · Tri-City", 68, 11, 43, 54),
    ("Logan Hensler", "D", 18, "NCAA · Wisconsin", 31, 2, 12, 14),
    ("Joshua Ravensbergen", "G", 18, "WHL · Prince George", 47, 0, 0, 0),
    ("Jack Murtagh", "C", 18, "USNTDP", 56, 28, 30, 58),
    ("Cameron Reid", "D", 18, "OHL · Kitchener", 65, 11, 43, 54),
    ("Sascha Boumedienne", "D", 18, "NCAA · Boston University", 39, 3, 9, 12),
    ("Malcolm Spence", "LW", 18, "OHL · Erie", 65, 32, 41, 73),
    ("Justin Carbonneau", "RW", 18, "QMJHL · Blainville", 60, 46, 43, 89),
    ("Benjamin Kindel", "C", 18, "WHL · Calgary", 65, 35, 65, 99),
    ("Ivan Ryabkin", "C", 17, "USHL · Muskegon", 28, 14, 14, 28),
    ("Pyotr Andreyanov", "G", 17, "MHL · CSKA", 31, 0, 0, 0),
    ("Bill Zonnon", "LW", 18, "QMJHL · Rouyn-Noranda", 56, 21, 52, 73),
    ("Charlie Trethewey", "D", 18, "NCAA · Boston University", 39, 4, 11, 15),
    ("Henry Brzustewicz", "D", 18, "OHL · London", 60, 4, 24, 28),
]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = updated = 0
    for i, (name, pos, age, league, gp, g, a, pts) in enumerate(PROSPECTS):
        # Iter 182 — the legacy " (Prospect)" suffix was dropped.
        # Surfaces now differentiate prospects from veterans via the
        # MinorEligibleBadge (iter 181) and the `player_type` field,
        # so the suffix had become user-visible clutter. We keep the
        # `nhl_id` namespace negative + use `(name, player_type)` as
        # the upsert key, which is safe under the players-collection's
        # non-unique `name_1` index.
        prospect_name = name
        doc = {
            "name": prospect_name,
            "display_name": name,
            "position": pos,
            "age": age,
            "team": league.split(" · ")[1] if " · " in league else league,
            "team_name": league,
            "player_type": "prospect",  # Iter 170o — filterable by entry-draft criteria.
            "player_status": "amateur",
            "amateur_league": league.split(" · ")[0] if " · " in league else None,
            "games_played": gp,
            "goals": g,
            "assists": a,
            "points": pts,
            "plus_minus": 0,
            "central_scouting_rank": i + 1,
            # Synthetic negative nhl_id to avoid the unique-index null
            # collision on nhl_id_1 in the players collection.
            "nhl_id": -(1_000_000 + i),
            "season": "2025-2026",
            "seeded_at": now_iso,
        }
        res = await db.players.update_one(
            {"name": prospect_name, "player_type": "prospect"},
            {"$set": doc},
            upsert=True,
        )
        if res.upserted_id:
            inserted += 1
        elif res.modified_count:
            updated += 1
    total = await db.players.count_documents({"player_type": "prospect"})
    print(f"Inserted {inserted}, updated {updated}; total prospects = {total}")


if __name__ == "__main__":
    asyncio.run(main())

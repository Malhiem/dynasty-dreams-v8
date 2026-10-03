"""Iter 232N — One-shot backfill for legacy draft picks whose embedded
`player.league` was hardcoded to "NHL" before build_pick_player_payload
became the single source of truth.

For every pick in every draft, look up the underlying player and re-derive
its league label using the same rules as build_pick_player_payload:
  • player_type == "prospect" and amateur_league set → amateur_league
  • player_type == "prospect" without amateur_league → "Prospect"
  • otherwise → "NHL"

Only picks whose current label disagrees with the correct one are rewritten,
so re-running the script is a no-op. Prints a per-draft summary and total.
"""
from __future__ import annotations

import asyncio
import os
import sys

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


def _derive_league(player_doc: dict) -> tuple[str, str]:
    player_type = (player_doc.get("player_type") or "skater")
    amateur_league = player_doc.get("amateur_league")
    if player_type == "prospect":
        return (amateur_league or "Prospect", player_type)
    return ("NHL", player_type)


async def main() -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL / DB_NAME env vars required")
        return 1

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    total_scanned = 0
    total_updated = 0
    per_draft: list[tuple[str, int, int]] = []

    async for draft in db.drafts.find({}, {"_id": 1, "name": 1, "picks": 1}):
        picks = draft.get("picks") or []
        if not picks:
            continue
        updated = False
        d_scanned = 0
        d_updated = 0
        for p in picks:
            player_obj = p.get("player") or {}
            pid = p.get("player_id")
            if not pid:
                continue
            d_scanned += 1
            total_scanned += 1
            try:
                player_doc = await db.players.find_one(
                    {"_id": ObjectId(pid)},
                    {"player_type": 1, "amateur_league": 1},
                )
            except Exception:
                continue
            if not player_doc:
                continue
            correct_league, correct_type = _derive_league(player_doc)
            cur_league = player_obj.get("league")
            cur_type = player_obj.get("player_type")
            if cur_league != correct_league or cur_type != correct_type:
                player_obj["league"] = correct_league
                player_obj["player_type"] = correct_type
                # also stamp amateur_league so downstream UIs can use it
                if player_doc.get("amateur_league") and not player_obj.get("amateur_league"):
                    player_obj["amateur_league"] = player_doc.get("amateur_league")
                p["player"] = player_obj
                updated = True
                d_updated += 1
                total_updated += 1
        if updated:
            await db.drafts.update_one(
                {"_id": draft["_id"]},
                {"$set": {"picks": picks}},
            )
        if d_updated:
            per_draft.append((str(draft.get("name") or draft["_id"]), d_scanned, d_updated))

    print(f"Scanned {total_scanned} picks, updated {total_updated} legacy labels.")
    for name, s, u in per_draft:
        print(f"  • {name}: {u}/{s} rewritten")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

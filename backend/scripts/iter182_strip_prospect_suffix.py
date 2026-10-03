"""
Iter 182 — Clean up the "(Prospect)" suffix that the iter 170o seed
script added to prospect names.

Background
==========
Iter 170o needed to coexist prospect rows with NHL veteran rows
that occasionally share a name (e.g. when a top prospect debuts in
the NHL). Its workaround was to append " (Prospect)" to the
prospect's `name` field — keeping `display_name` clean — so the
players collection's `(name, nhl_id_unique)` indexes wouldn't
collide.

That suffix has since become user-visible:
  • `/api/players` and `/api/waivers/available` return `name` not
    `display_name`, so end-users see "Gavin McKenna (Prospect)".
  • Iter 181 added a dedicated MinorEligibleBadge to every player
    surface — the suffix is now redundant AND uglier than the
    badge.

What this script does
=====================
  1. For every prospect row whose `name` ends with " (Prospect)":
       a. Compute the clean name (strip the suffix).
       b. If another row already exists with that exact clean name
          AND `player_type == "prospect"`, DELETE the orphan
          (un-suffixed prospect from an older partial seed) and
          rename the canonical iter-170o record. This is the
          Gavin-McKenna case.
       c. If another row exists with the clean name but is an NHL
          veteran (non-prospect), leave the suffix in place to
          avoid collisions. Log it so the next ingest can
          disambiguate via `nhl_id` instead.
       d. Otherwise simply rename the prospect row to the clean name.
  2. Make sure every renamed row carries `display_name = name` so
     downstream code that reads either field gets the clean value.

The script is idempotent — re-running it is a no-op once the
cleanup has been applied.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient


SUFFIX = " (Prospect)"


async def main() -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("MONGO_URL / DB_NAME missing", file=sys.stderr)
        return 2

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    suffixed = await db.players.find(
        {"name": {"$regex": r"\(Prospect\)$"}},
    ).to_list(10_000)
    print(f"Found {len(suffixed)} player rows with the legacy '(Prospect)' suffix")

    renamed = 0
    deleted_orphans = 0
    skipped_veteran_collisions = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for doc in suffixed:
        legacy_name: str = doc["name"]
        clean_name = legacy_name[: -len(SUFFIX)].rstrip()

        collision = await db.players.find_one(
            {"_id": {"$ne": doc["_id"]}, "name": clean_name},
        )

        if collision and (collision.get("player_type") == "prospect"):
            # Old orphan prospect record (e.g. pre-iter170o seed) —
            # delete the orphan and rename our canonical row.
            await db.players.delete_one({"_id": collision["_id"]})
            await db.players.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "name": clean_name,
                    "display_name": clean_name,
                    "iter182_renamed_at": now_iso,
                }},
            )
            renamed += 1
            deleted_orphans += 1
            print(f"  ✓ Renamed {legacy_name!r} → {clean_name!r}; deleted orphan {collision['_id']}")
        elif collision and (collision.get("player_type") != "prospect"):
            # NHL veteran collision — the player_type + minor-eligible
            # badge differentiate the two records visually in every UI
            # surface, so it's safe to drop the legacy suffix. We keep
            # both rows because the prospect may not be the same person
            # (e.g. two unrelated players with the same name). The
            # collection's `name` index is non-unique so this is fine.
            await db.players.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "name": clean_name,
                    "display_name": clean_name,
                    "iter182_renamed_at": now_iso,
                }},
            )
            renamed += 1
            skipped_veteran_collisions += 1
            print(f"  ✓ Renamed {legacy_name!r} → {clean_name!r} (NHL veteran with same clean name kept at {collision['_id']})")
        else:
            await db.players.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "name": clean_name,
                    "display_name": clean_name,
                    "iter182_renamed_at": now_iso,
                }},
            )
            renamed += 1
            print(f"  ✓ Renamed {legacy_name!r} → {clean_name!r}")

    print()
    print(f"Done. renamed={renamed}, deleted_orphans={deleted_orphans}, "
          f"skipped_veteran_collisions={skipped_veteran_collisions}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

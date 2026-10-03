"""One-time DB migration: clean up stale `TEST_DraftSmoke_*` stub drafts.

Iter 231d — Identified during the iter 231b auto-init preview rollout:
50 orphan draft documents from test runs that auto-init'd a draft but
never made any picks, never scheduled the draft, and live in leagues
whose own names are clearly test artefacts (`TEST_DraftSmoke_*`).

The rows are already filtered out of every user-facing surface (League
switcher, dashboard, upcoming-drafts picker, etc.) by the existing
`_is_test_artifact_league` helper + `exclude_test=true` query flag, but
they bloat the `drafts` + `draft_picks` collections unnecessarily.

This script is **idempotent** and **safe to re-run** — it only deletes:
  - drafts with `picks: []`, `status: scheduled`, `scheduled_time: None`,
    `draft_started: False`
  - whose league name starts with `TEST_DraftSmoke_`

Plus their cascading `draft_picks` rows.

Usage:
  python -m scripts.iter231d_cleanup_test_draftsmoke_stubs
  python -m scripts.iter231d_cleanup_test_draftsmoke_stubs --dry-run
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient


async def main(dry_run: bool = False) -> dict:
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]

    # Find candidate stub drafts.
    candidates = await db.drafts.find({
        "picks": {"$size": 0},
        "status": "scheduled",
        "scheduled_time": None,
        "draft_started": False,
        "league_name": {"$regex": "^TEST_DraftSmoke_"},
    }).to_list(1000)

    print(f"Found {len(candidates)} stub drafts matching the cleanup criteria.")
    deleted_drafts = 0
    deleted_picks = 0
    for d in candidates:
        draft_id = str(d["_id"])
        league_name = d.get("league_name", "?")
        # Count cascading draft_picks rows.
        picks_in_collection = await db.draft_picks.count_documents({"draft_id": draft_id})
        if dry_run:
            print(f"  [dry-run] would delete draft {draft_id}  league={league_name!r}  cascading_picks={picks_in_collection}")
            continue
        await db.drafts.delete_one({"_id": d["_id"]})
        if picks_in_collection > 0:
            r = await db.draft_picks.delete_many({"draft_id": draft_id})
            deleted_picks += r.deleted_count
        deleted_drafts += 1
        print(f"  deleted draft {draft_id}  league={league_name!r}  cascading_picks={picks_in_collection}")

    summary = {
        "candidates_found": len(candidates),
        "drafts_deleted": deleted_drafts,
        "draft_picks_deleted": deleted_picks,
        "dry_run": dry_run,
    }
    print("\nDone:", summary)
    client.close()
    return summary


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry))

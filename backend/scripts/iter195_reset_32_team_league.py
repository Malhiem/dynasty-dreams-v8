"""Iter 195 — Reset 'Ice Kings 32 Entry Draft' to a wizard-ready
empty state so commissioner chriszarek can run the setup wizard
from scratch.

What it does:
  * Deletes all 32 seeded teams + 1440 draft picks + any matchups /
    waiver claims / trades / activity tied to the league.
  * Wipes scoring/roster/playoff config back to neutral defaults.
  * Flips `setup_wizard_complete=False` + `current_season_status="setup"`.
  * Preserves: league _id, name, commissioner_id (chriszarek),
    invite_code, created_at.

Idempotent. Safe to re-run.
"""
import asyncio
import os
from datetime import datetime, timezone

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

LEAGUE_NAME = "Ice Kings 32 Entry Draft"

# Fields to zero out so the wizard takes the user back through every
# step. We preserve identity / commissioner / invite_code.
RESET_FIELDS = {
    "setup_wizard_complete": False,
    "setup_wizard_completed_at": None,
    "setup_wizard_completed_by": None,
    "current_season_status": "setup",
    "current_week": 0,
    "first_draft_completed": False,
    "current_teams": 0,
    "max_teams": 32,
    "trade_deadline_at": None,
    "draft_trade_review_minutes": 30,
    "draft_trade_post_delay_action": "auto_execute",
    "audit_log": [],
    "playoff_settings": None,
    "scoring_settings": None,
    "roster_spots": None,
    "salary_cap": None,
    "salary_cap_enabled": False,
}


async def main() -> None:
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    league = await db.leagues.find_one({"name": LEAGUE_NAME})
    if not league:
        print(f"League '{LEAGUE_NAME}' not found — nothing to reset.")
        return
    lid = str(league["_id"])
    print(f"Resetting league {lid} ({LEAGUE_NAME}) …")

    # ── Children ─────────────────────────────────────────────────
    for coll in (
        "teams", "draft_picks", "rosters", "matchups", "waiver_claims",
        "trades", "draft_orders", "league_invites",
    ):
        try:
            r = await db[coll].delete_many({"league_id": lid})
            print(f"  cleared {coll}: {r.deleted_count}")
        except Exception as e:
            print(f"  skip {coll}: {e}")
    # Also strip the activity_feed for this league so the wizard
    # starts on a clean slate.
    r = await db.activity_feed.delete_many({"league_id": lid})
    print(f"  cleared activity_feed: {r.deleted_count}")

    # ── League doc ───────────────────────────────────────────────
    await db.leagues.update_one(
        {"_id": ObjectId(lid)},
        {"$set": {**RESET_FIELDS, "reset_at": datetime.now(timezone.utc)}},
    )
    print("League doc reset. Wizard will take over on next visit.")


if __name__ == "__main__":
    asyncio.run(main())

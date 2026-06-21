"""Iter 191 — Idempotent cleanup of mock trade artefacts for the
`Ice Kings Head-to-Head` league.

Drops:
  * Every `trades` doc for the league (status irrelevant).
  * Every `activity_feed` doc whose `event_type` starts with "trade_"
    or equals "pick_traded" / "ops_force_fix".
  * Restores each draft_pick's `current_team_*` back to `original_team_*`
    and empties `trade_history`.

Writes a JSON backup to /app/backend/scripts/iter191_cleanup_backup_YYYYMMDD-HHMM.json
before any destructive op so we can roll back if needed.

Idempotent: re-running on an already-clean league is a no-op (counts
will all be 0).

Usage:
    cd /app/backend && python -m scripts.iter191_cleanup_ice_kings_trades
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

LEAGUE_NAME = "Ice Kings Head-to-Head"
BACKUP_DIR = Path("/app/backend/scripts")
TRADE_EVENT_TYPES = {
    "trade_executed",
    "trade_proposed",
    "trade_accepted",
    "trade_rejected",
    "trade_vetoed",
    "trade_cancelled",
    "pick_traded",
}


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    league = await db.leagues.find_one({"name": LEAGUE_NAME})
    if not league:
        print(f"League '{LEAGUE_NAME}' not found — nothing to clean.")
        return
    lid = str(league["_id"])
    print(f"League: {LEAGUE_NAME} ({lid})")

    # ── Backup ──────────────────────────────────────────
    trades = await db.trades.find({"league_id": lid}).to_list(None)
    activity = await db.activity_feed.find({
        "league_id": lid,
        "event_type": {"$in": list(TRADE_EVENT_TYPES)},
    }).to_list(None)
    traded_picks = await db.draft_picks.find({
        "league_id": lid,
        "$or": [
            {"$expr": {"$ne": ["$current_team_id", "$original_team_id"]}},
            {"trade_history": {"$exists": True, "$ne": []}},
        ],
    }).to_list(None)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"iter191_cleanup_backup_{ts}.json"

    def _jsonify(obj):
        if isinstance(obj, dict):
            return {k: _jsonify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_jsonify(v) for v in obj]
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        try:
            from bson import ObjectId
            if isinstance(obj, ObjectId):
                return str(obj)
        except Exception:
            pass
        return obj

    backup_path.write_text(json.dumps({
        "league_id": lid,
        "league_name": LEAGUE_NAME,
        "captured_at": ts,
        "trades": _jsonify(trades),
        "activity_feed": _jsonify(activity),
        "traded_picks": _jsonify(traded_picks),
    }, indent=2))
    print(f"Backup → {backup_path}")
    print(
        f"Pre-cleanup counts: trades={len(trades)} "
        f"activity={len(activity)} traded_picks={len(traded_picks)}"
    )

    # ── Cleanup ─────────────────────────────────────────
    tr_del = await db.trades.delete_many({"league_id": lid})
    print(f"Deleted trades: {tr_del.deleted_count}")

    act_del = await db.activity_feed.delete_many({
        "league_id": lid,
        "event_type": {"$in": list(TRADE_EVENT_TYPES)},
    })
    print(f"Deleted activity_feed trade entries: {act_del.deleted_count}")

    # Reset traded picks. We mirror `original_team_*` back into
    # `current_team_*` and clear `trade_history`. Picks that were
    # never traded remain untouched (count is 0 there).
    pick_reset = 0
    for p in traded_picks:
        await db.draft_picks.update_one(
            {"_id": p["_id"]},
            {"$set": {
                "current_team_id": p.get("original_team_id"),
                "current_team_name": p.get("original_team_name"),
                "trade_history": [],
            }},
        )
        pick_reset += 1
    print(f"Reset draft_picks: {pick_reset}")

    print("Done — idempotent. Re-run any time.")


if __name__ == "__main__":
    asyncio.run(main())

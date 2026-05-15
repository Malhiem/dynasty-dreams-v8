"""Backfill legacy trade documents to use the canonical field names.

Some early trades stored their team references under `team_a_id` /
`team_b_id` and asset arrays under `team_a_assets` / `team_b_assets`. The
runtime code-path now expects `proposer_team_id` / `target_team_id` and
`assets_offered` / `assets_requested`. Without backfilling, the
Transactions filter (which now drops "ghost trade" rows where teamA or
teamB resolve to blank) silently hides these historic trades from view.

This migration:
  • Copies team_a_id → proposer_team_id, team_b_id → target_team_id
  • Copies team_a_assets → assets_offered, team_b_assets → assets_requested
  • Hydrates proposer_team_name / target_team_name from `db.teams`
  • Drops legacy fields after the copy (so re-runs are no-ops)
  • Idempotent — uses `$exists: True` checks per field

Usage:
    cd /app/backend
    python -m scripts.backfill_legacy_trade_fields [--dry-run] [--verbose]
"""
import argparse
import asyncio
import os
import sys
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


def _env(key: str) -> str | None:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(p):
        return os.environ.get(key)
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(key)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    mongo_url = _env("MONGO_URL")
    db_name = _env("DB_NAME")
    if not mongo_url or not db_name:
        print("MONGO_URL/DB_NAME not configured", file=sys.stderr)
        return 1

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Hydrate a team_id → name cache once
    team_names: dict[str, str] = {}
    async for t in db.teams.find({}, {"name": 1}):
        team_names[str(t["_id"])] = t.get("name") or ""

    total = 0
    touched = 0
    field_writes: dict[str, int] = {}
    field_drops: dict[str, int] = {}

    cursor = db.trades.find({
        "$or": [
            {"team_a_id": {"$exists": True}},
            {"team_b_id": {"$exists": True}},
            {"team_a_assets": {"$exists": True}},
            {"team_b_assets": {"$exists": True}},
            {"from_team_id": {"$exists": True}},
            {"to_team_id": {"$exists": True}},
            {"from_assets": {"$exists": True}},
            {"to_assets": {"$exists": True}},
        ]
    })
    async for trade in cursor:
        total += 1
        set_ops: dict[str, Any] = {}
        unset_ops: dict[str, Any] = {}

        def _copy(legacy: str, canonical: str):
            if legacy in trade and (canonical not in trade or trade.get(canonical) in (None, [], "")):
                set_ops[canonical] = trade[legacy]
                field_writes[canonical] = field_writes.get(canonical, 0) + 1
            if legacy in trade:
                unset_ops[legacy] = ""
                field_drops[legacy] = field_drops.get(legacy, 0) + 1

        _copy("team_a_id", "proposer_team_id")
        _copy("team_b_id", "target_team_id")
        _copy("from_team_id", "proposer_team_id")
        _copy("to_team_id", "target_team_id")
        _copy("team_a_assets", "assets_offered")
        _copy("team_b_assets", "assets_requested")
        _copy("from_assets", "assets_offered")
        _copy("to_assets", "assets_requested")

        # Hydrate names from the resolved IDs
        proposer_id = set_ops.get("proposer_team_id") or trade.get("proposer_team_id")
        target_id = set_ops.get("target_team_id") or trade.get("target_team_id")
        if proposer_id and not trade.get("proposer_team_name"):
            nm = team_names.get(str(proposer_id))
            if nm:
                set_ops["proposer_team_name"] = nm
        if target_id and not trade.get("target_team_name"):
            nm = team_names.get(str(target_id))
            if nm:
                set_ops["target_team_name"] = nm

        if not set_ops and not unset_ops:
            continue
        touched += 1
        if args.verbose:
            print(f"  • {trade.get('_id')} → set {sorted(set_ops.keys())} unset {sorted(unset_ops.keys())}")
        if not args.dry_run:
            mongo_update: dict[str, Any] = {}
            if set_ops: mongo_update["$set"] = set_ops
            if unset_ops: mongo_update["$unset"] = unset_ops
            await db.trades.update_one({"_id": trade["_id"]}, mongo_update)

    verb = "Would update" if args.dry_run else "Updated"
    print(f"\n{verb} {touched} / {total} legacy trade docs.")
    if field_writes:
        print("  fields set:", dict(sorted(field_writes.items())))
    if field_drops:
        print("  fields dropped:", dict(sorted(field_drops.items())))
    if args.dry_run:
        print("Dry run — re-run without --dry-run to apply.")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

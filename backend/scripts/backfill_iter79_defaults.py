"""Backfill defaults for iter 79 + iter 81 league settings on every existing
league document.

Idempotent: only writes a field when it's missing (uses `$exists: False` filter
per field). Safe to re-run; running twice will set zero documents.

Usage:
    cd /app/backend
    python -m scripts.backfill_iter79_defaults [--dry-run] [--verbose]

Fields backfilled (iter 79):
    season_start_date          (None)
    season_end_date            (None)
    matchup_length_days        (7)
    opponents_per_matchup_period (1)
    playoff_end_week           (derived from playoff_start_week + 3, or None)
    consolation_enabled        (False)
    consolation_uses_playoff_schedule (True)
    consolation_start_week     (None)
    consolation_end_week       (None)
    salary_retention_enabled   (derived from salary_retention_slots>0)
    salary_retention_max_pct   (50)
    salary_retention_slots     (kept if present, else 0)

Fields backfilled (iter 81):
    ir_slots                   (0)
    ir_plus_slots              (0)
    taxi_squad_size            (0)
    position_limits            ({})
    enforce_position_maxes     (False)
    min_active_players         (0)
    min_games_played           (0)
    prorate_min_max_by_period  (False)
    allow_illegal_rosters      (True)
    ir_eligibility_modes       (["IR"])
"""
import argparse
import asyncio
import os
import sys
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient


def _load_env() -> dict:
    """Read MONGO_URL and DB_NAME from backend/.env. The dotenv loaded at app
    boot doesn't run for an ad-hoc script, so we parse the file ourselves to
    avoid the user having to export anything before running this."""
    env: dict = {}
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(here, "..", ".env")),
        "/app/backend/.env",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        break
    return env


def _iter79_defaults(league: dict) -> dict:
    """Return only the iter-79 fields that are missing from this league doc."""
    out: dict[str, Any] = {}
    if "season_start_date" not in league:
        out["season_start_date"] = None
    if "season_end_date" not in league:
        out["season_end_date"] = None
    if "matchup_length_days" not in league:
        out["matchup_length_days"] = 7
    if "opponents_per_matchup_period" not in league:
        out["opponents_per_matchup_period"] = 1
    if "playoff_end_week" not in league:
        ps = league.get("playoff_start_week")
        out["playoff_end_week"] = (ps + 3) if isinstance(ps, int) else None
    if "consolation_enabled" not in league:
        out["consolation_enabled"] = False
    if "consolation_uses_playoff_schedule" not in league:
        out["consolation_uses_playoff_schedule"] = True
    if "consolation_start_week" not in league:
        out["consolation_start_week"] = None
    if "consolation_end_week" not in league:
        out["consolation_end_week"] = None
    if "salary_retention_enabled" not in league:
        # If the league already has retention slots configured, treat as on
        slots = league.get("salary_retention_slots") or 0
        out["salary_retention_enabled"] = slots > 0
    if "salary_retention_max_pct" not in league:
        out["salary_retention_max_pct"] = 50
    if "salary_retention_slots" not in league:
        out["salary_retention_slots"] = 0
    return out


def _iter81_defaults(league: dict) -> dict:
    """Return only the iter-81 fields that are missing from this league doc."""
    out: dict[str, Any] = {}
    if "ir_slots" not in league:
        out["ir_slots"] = 0
    if "ir_plus_slots" not in league:
        out["ir_plus_slots"] = 0
    if "taxi_squad_size" not in league:
        out["taxi_squad_size"] = 0
    if "position_limits" not in league:
        out["position_limits"] = {}
    if "enforce_position_maxes" not in league:
        out["enforce_position_maxes"] = False
    if "min_active_players" not in league:
        out["min_active_players"] = 0
    if "min_games_played" not in league:
        out["min_games_played"] = 0
    if "prorate_min_max_by_period" not in league:
        out["prorate_min_max_by_period"] = False
    if "allow_illegal_rosters" not in league:
        out["allow_illegal_rosters"] = True
    if "ir_eligibility_modes" not in league:
        out["ir_eligibility_modes"] = ["IR"]
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; don't write")
    parser.add_argument("--verbose", action="store_true", help="print each league's diff")
    args = parser.parse_args()

    env = _load_env()
    mongo_url = env.get("MONGO_URL") or os.environ.get("MONGO_URL")
    db_name = env.get("DB_NAME") or os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL or DB_NAME not configured in backend/.env or environment",
              file=sys.stderr)
        return 1

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    total = 0
    touched = 0
    iter79_writes = 0
    iter81_writes = 0
    async for league in db.leagues.find({}):
        total += 1
        diff = {**_iter79_defaults(league), **_iter81_defaults(league)}
        if not diff:
            continue
        touched += 1
        iter79_writes += sum(1 for k in diff if k in _iter79_defaults(league))
        iter81_writes += sum(1 for k in diff if k in _iter81_defaults(league))
        if args.verbose:
            print(f"  • {league.get('name', league.get('_id'))} → {sorted(diff.keys())}")
        if not args.dry_run:
            await db.leagues.update_one(
                {"_id": league["_id"]},
                {"$set": diff},
            )

    verb = "Would set" if args.dry_run else "Set"
    print(f"\n{verb} defaults on {touched} / {total} leagues "
          f"(iter79 keys: {iter79_writes}, iter81 keys: {iter81_writes}).")
    if args.dry_run:
        print("Dry run — no documents modified. Re-run without --dry-run to apply.")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

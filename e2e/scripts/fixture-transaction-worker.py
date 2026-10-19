"""Bounded transaction engines for named fixtures in the disposable E2E stack."""
import argparse
import asyncio
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

if not (os.environ.get("E2E_MODE", "").lower() == "true"
        and os.environ.get("DB_NAME") == "dynasty_dreams_e2e"
        and urlsplit(os.environ.get("MONGO_URL", "")).hostname == "mongo"
        and os.environ.get("FIXTURE_WORKERS_ISOLATED") == "1"):
    raise SystemExit("Refusing: explicit disposable E2E configuration is required")

from server import db, log_activity, _execute_trade
from services.waiver_engine import process_pending_claims


async def run(seconds, mode, interval):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if mode in ("both", "waivers"):
            async for league in db.leagues.find({"name": {"$regex": "^Position moves"}, "transactions_config.waiver.enabled": True}, {"_id": 1}):
                try:
                    print("waivers", str(league["_id"]), await process_pending_claims(db, str(league["_id"]), log_activity=log_activity), flush=True)
                except Exception as error:
                    print("waiver-error", str(league["_id"]), type(error).__name__, str(error), flush=True)
        if mode in ("both", "trades"):
            leagues = await db.leagues.find({"name": {"$regex": "^H2H acceptance"}}, {"_id": 1}).to_list(None)
            ids = [str(league["_id"]) for league in leagues]
            async for trade in db.trades.find({"league_id": {"$in": ids}, "status": "pending", "processes_at": {"$lte": datetime.now(timezone.utc).isoformat(), "$ne": None}}):
                try:
                    result = await _execute_trade(trade)
                    if result and result.get("executed"):
                        await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"status": "executed", "processed_at": datetime.now(timezone.utc).isoformat()}})
                    print("trade", str(trade["_id"]), result, flush=True)
                except Exception as error:
                    print("trade-error", str(trade["_id"]), type(error).__name__, str(error), flush=True)
        await asyncio.sleep(min(interval, max(0, end - time.monotonic())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=360, choices=range(60, 601), metavar="60..600")
    parser.add_argument("--mode", choices=("both", "trades", "waivers"), default="both")
    parser.add_argument("--interval", type=int, default=60, choices=range(1, 61), metavar="1..60")
    args = parser.parse_args()
    asyncio.run(run(args.seconds, args.mode, args.interval))

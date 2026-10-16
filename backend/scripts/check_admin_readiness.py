"""Read-only release preflight: python -m scripts.check_admin_readiness."""
import asyncio
import json
import os
from motor.motor_asyncio import AsyncIOMotorClient
from services.admin_mutations import transaction_ready


async def check(db):
    await transaction_ready(db)
    # Exercise a transaction with a read, then abort. Never write production data.
    async with await db.client.start_session() as session:
        session.start_transaction()
        try:
            await db.users.find_one({}, {"_id": 1}, session=session)
        finally:
            await session.abort_transaction()
    return {"ready": True, "transaction_read": "passed", "writes_performed": False}


async def main():
    url, name = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not url or not name:
        print(json.dumps({"ready": False, "reason": "Explicit MONGO_URL and DB_NAME are required"}))
        return 1
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=5000)
    try:
        result = await check(client[name])
        code = 0
    except Exception:
        # Do not echo connection strings, credentials, server addresses or raw DB errors.
        result = {"ready": False, "reason": "Transaction preflight failed; check topology, connectivity and database permissions", "writes_performed": False}
        code = 1
    finally:
        client.close()
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

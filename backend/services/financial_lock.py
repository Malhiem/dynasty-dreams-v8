"""Cross-worker serialization of league financial mutations on standalone Mongo.

A lease is acquired before validation and held through writes. Crashed workers
release after five minutes; a token prevents an old owner deleting a new lease.
"""
import asyncio
import inspect
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from functools import wraps
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

_held = ContextVar("financial_leases", default=frozenset())


def serialize_finances(db_getter):
    def decorate(fn):
        signature = inspect.signature(fn, eval_str=True)
        @wraps(fn)
        async def locked(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            db = values.get("db")
            if db is None:
                db = db_getter()
            league_id = values.get("league_id")
            if not league_id and "trade" in values:
                league_id = values["trade"]["league_id"]
            if not league_id and "input" in values:
                league_id = getattr(values["input"], "league_id", None)
            if not league_id and "trade_id" in values:
                trade = await db.trades.find_one({"_id": ObjectId(values["trade_id"])})
                league_id = (trade or {}).get("league_id")
            if not league_id and "contract_id" in values:
                contract = await db.contracts.find_one({"_id": ObjectId(values["contract_id"])})
                league_id = (contract or {}).get("league_id")
            if not league_id and "draft_id" in values:
                draft = await db.drafts.find_one({"_id": ObjectId(values["draft_id"])})
                league_id = (draft or {}).get("league_id")
            if not league_id and "team_id" in values:
                team = await db.teams.find_one({"_id": ObjectId(values["team_id"])})
                league_id = (team or {}).get("league_id")
            if not league_id or league_id in _held.get():
                return await fn(*args, **kwargs)
            owner = uuid.uuid4().hex
            acquired = False
            for attempt in range(200):
                now = datetime.now(timezone.utc)
                try:
                    result = await db.financial_locks.update_one(
                        {"_id": league_id, "$or": [{"expires_at": {"$lte": now}}, {"owner": owner}]},
                        {"$set": {"owner": owner, "expires_at": now + timedelta(minutes=5)}}, upsert=True)
                    acquired = bool(result.upserted_id or result.modified_count)
                except DuplicateKeyError:
                    pass
                if acquired:
                    break
                await asyncio.sleep(0.05)
            if not acquired:
                raise HTTPException(409, "Another league financial transaction is in progress; retry")
            token = _held.set(_held.get() | {league_id})
            try:
                return await fn(*args, **kwargs)
            finally:
                _held.reset(token)
                await db.financial_locks.delete_one({"_id": league_id, "owner": owner})
        locked.__signature__ = signature
        return locked
    return decorate

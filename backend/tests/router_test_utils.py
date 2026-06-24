"""Shared helpers for router-unit tests.

Each router exposes a `setup(deps: dict)` injection point. We exploit that to
swap the live `db` reference with an ephemeral test database, then mount the
router on a throwaway FastAPI app + run requests in-process via `httpx
AsyncClient(transport=ASGITransport)`. The result: no HTTP, no port, no
shared collection pollution.

Usage:
    from .router_test_utils import isolated_router_app

    async def test_thing():
        async with isolated_router_app(contracts_routes) as ctx:
            r = await ctx.client.get("/api/contracts?league_id=fake")
            assert r.status_code == 200
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import os
import uuid

from bson import ObjectId
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient


def _env(key: str) -> str:
    """Pull a value from backend/.env without importing dotenv."""
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(key)


@dataclass
class IsolatedCtx:
    db: object
    client: AsyncClient
    user: dict
    broadcast_calls: list = field(default_factory=list)
    activity_calls: list = field(default_factory=list)


@asynccontextmanager
async def isolated_router_app(router_module, *, user: dict | None = None):
    """Mount `router_module.router` on an ephemeral FastAPI app pointed at a
    fresh test database. Yields an `IsolatedCtx` with helpers for assertions.

    The test database is dropped on exit so each test starts pristine — this
    is the property the iter-85 test-pollution incident specifically lacked.
    """
    # Per-test mongo client. We tried sharing one client across tests but
    # motor's connection pool occasionally hands out a stale socket under
    # the 200+ test suite (manifests as `AutoReconnect: connection closed`).
    # Per-test clients with `maxPoolSize=1` keep the kernel TIME_WAIT pool
    # bounded and `retryReads/Writes=True` masks the rare transient.
    mongo = AsyncIOMotorClient(
        _env("MONGO_URL"),
        maxPoolSize=1,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        retryReads=True,
        retryWrites=True,
    )
    db_name = f"dynasty_test_router_{uuid.uuid4().hex[:8]}"
    db = mongo[db_name]

    # ── Stubbed deps ──
    # The real `get_current_user` parses a JWT cookie. For unit tests we hand
    # the router a static identity that satisfies its checks.
    test_user = user or {
        "_id": "test_user_0001",
        "id": "test_user_0001",
        "name": "Test User",
        "email": "test@example.com",
    }

    async def _stub_get_current_user(_request):
        return test_user

    def _safe_object_id(value, _label="id"):
        from fastapi import HTTPException
        try:
            return ObjectId(value)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid id: {exc}")

    broadcast_calls: list = []
    activity_calls: list = []

    async def _stub_broadcast(room, event, payload):
        broadcast_calls.append({"room": room, "event": event, "payload": payload})

    async def _stub_log_activity(league_id, event_type, message, user_id=None, metadata=None):
        activity_calls.append({
            "league_id": league_id,
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "metadata": metadata,
        })

    async def _stub_recompute(team_id):  # pragma: no cover - only used by contracts router fallback
        return 0.0

    def _stub_calculate_fantasy_points(player, config=None):
        return float(player.get("points") or player.get("fantasy_points") or 0.0)

    router_module.setup({
        "db": db,
        "get_current_user": _stub_get_current_user,
        "_safe_object_id": _safe_object_id,
        "broadcast_to_room": _stub_broadcast,
        "log_activity": _stub_log_activity,
        "_recompute_team_salary_used": _stub_recompute,
        "calculate_fantasy_points": _stub_calculate_fantasy_points,
    })

    app = FastAPI()
    sub = APIRouter()
    sub.include_router(router_module.router)
    app.include_router(sub, prefix="/api")

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver",
        ) as client:
            yield IsolatedCtx(
                db=db,
                client=client,
                user=test_user,
                broadcast_calls=broadcast_calls,
                activity_calls=activity_calls,
            )
    finally:
        try:
            await mongo.drop_database(db_name)
        finally:
            mongo.close()


async def seed_league(db, *, commissioner_id="test_user_0001", co_commissioners=None, salary_cap_enabled=False, salary_cap=82_500_000):
    """Insert a minimal league doc and return its string id."""
    res = await db.leagues.insert_one({
        "name": "Unit Test League",
        "commissioner_id": commissioner_id,
        "co_commissioners": co_commissioners or [],
        "salary_cap_enabled": salary_cap_enabled,
        "salary_cap": salary_cap,
    })
    return str(res.inserted_id)


async def seed_team(db, *, league_id, owner_id="test_user_0001", name="Test Team"):
    res = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": owner_id,
        "owner_name": "Test Owner",
        "name": name,
    })
    return str(res.inserted_id)


async def seed_player(db, *, name="Test Player", position="C", aav=5_000_000):
    res = await db.players.insert_one({
        "name": name,
        "position": position,
        "team": "TST",
        "contract": {"aav": aav},
        "salary": aav,
    })
    return str(res.inserted_id)

"""Iter 231aq — Global ErrorBoundary + `POST /api/client-errors` sink.

User asked:
  "Drop a tiny global ErrorBoundary right above the router so any
   future component crash shows a friendly 'Something went sideways —
   refresh to retry' card instead of the raw dev overlay? It would
   also let us POST the stack to a backend /api/client-errors
   endpoint so we hear about crashes before users do."

Backend: `routes/client_errors.py`
  • `POST /api/client-errors` — anonymous-friendly sink, truncates
    every text field, caps payload at 64 KB.
  • `GET /api/client-errors` — paginated, platform-admin only
    (matches `db_hygiene._is_platform_admin` gate: `role == "admin"`
    OR `ADMIN_EMAIL` env override OR explicit `is_admin: true`).

Frontend: `components/GlobalErrorBoundary.tsx`
  • React class boundary above `<BrowserRouter>`.
  • Friendly fallback card with "Refresh to retry" + "back to
    dashboard" CTAs.
  • Global `window.onerror` + `unhandledrejection` listeners catch
    non-React crashes too.
  • 20-entry breadcrumb ring (clicks + nav) attaches to every report.
  • POST uses `keepalive: true` so reports survive a same-tick page
    reload.
"""
import os
import sys
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, APIRouter
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import client_errors as client_errors_routes  # noqa: E402


# ── Frontend artefact guards ──────────────────────────────────────────

from pathlib import Path  # noqa: E402

APP_JS = Path("/app/frontend/src/App.js")
BOUNDARY = Path("/app/frontend/src/components/GlobalErrorBoundary.tsx")


def test_boundary_mounted_above_router():
    src = APP_JS.read_text()
    assert 'import GlobalErrorBoundary from "@/components/GlobalErrorBoundary"' in src
    # `<GlobalErrorBoundary>` wraps `<AuthProvider>` → `<BrowserRouter>`
    # so a crash anywhere in the tree (including auth context) is
    # caught.
    assert "<GlobalErrorBoundary>" in src
    assert "</GlobalErrorBoundary>" in src


def test_boundary_has_friendly_fallback_and_reload_cta():
    src = BOUNDARY.read_text()
    # Fallback card is rendered only when `hasError`.
    assert "static getDerivedStateFromError" in src
    assert "componentDidCatch" in src
    # Friendly copy + retry button (testids let QA drive it).
    assert "Something went sideways" in src
    assert 'data-testid="global-error-boundary"' in src
    assert 'data-testid="global-error-boundary-reload"' in src
    assert "window.location.reload()" in src


def test_boundary_posts_to_client_errors_with_breadcrumbs():
    src = BOUNDARY.read_text()
    # The POST hits `/api/client-errors` (route prefix is added at the
    # server, we hard-code the leading segment here).
    assert '"/api/client-errors"' in src
    # Fire-and-forget — `keepalive: true` keeps the request alive
    # even if the page reloads same-tick.
    assert "keepalive: true" in src
    # Breadcrumb ring caps at 20 entries.
    assert "BREADCRUMB_LIMIT = 20" in src
    assert "pushBreadcrumb(" in src
    # Global listeners exist for non-React crashes.
    assert 'addEventListener("error"' in src
    assert 'addEventListener("unhandledrejection"' in src


# ── Backend route behaviour ──────────────────────────────────────────

async def _isolated_app():
    """Build an ephemeral FastAPI app with the client_errors router."""
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"], maxPoolSize=1)
    db_name = f"dynasty_test_clienterr_{uuid.uuid4().hex[:8]}"
    db = mongo[db_name]

    async def get_user_anon(_request):
        return None

    async def get_user_admin(_request):
        return {"_id": "user_admin", "email": os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), "role": "admin"}

    async def get_user_regular(_request):
        return {"_id": "user_reg", "email": "owner@example.com"}

    return mongo, db_name, db, get_user_anon, get_user_admin, get_user_regular


@pytest.mark.asyncio
async def test_anonymous_post_records_error():
    mongo, dbname, db, anon, _admin, _reg = await _isolated_app()
    try:
        client_errors_routes.setup({"db": db, "get_current_user": anon})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(client_errors_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(
                "/api/client-errors",
                json={
                    "message": "TypeError: undefined is not a function",
                    "stack": "Error\n  at Foo (Foo.tsx:12:3)",
                    "url": "https://app.example.com/dashboard",
                    "user_agent": "Mozilla/5.0",
                    "breadcrumbs": [{"ts": "2026-02-28T00:00:00Z", "kind": "click", "detail": "x"}],
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "id" in body
        # Record was actually persisted (with no `user_id` since anon).
        doc = await db.client_errors.find_one({})
        assert doc is not None
        assert doc["message"].startswith("TypeError")
        assert doc["user_id"] is None
        assert len(doc["breadcrumbs"]) == 1
    finally:
        await mongo.drop_database(dbname)
        mongo.close()


@pytest.mark.asyncio
async def test_post_truncates_oversized_payload():
    """A 200KB stack must not bloat Mongo. Each field is truncated."""
    mongo, dbname, db, anon, _admin, _reg = await _isolated_app()
    try:
        client_errors_routes.setup({"db": db, "get_current_user": anon})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(client_errors_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(
                "/api/client-errors",
                json={
                    "message": "x" * 50_000,
                    "stack": "y" * 200_000,
                    "component_stack": "z" * 50_000,
                    "breadcrumbs": [{"k": i} for i in range(100)],
                },
            )
        assert r.status_code == 200
        doc = await db.client_errors.find_one({})
        # Message capped at 8 KB.
        assert len(doc["message"]) <= 8_000
        # Stack capped at 16 KB.
        assert len(doc["stack"]) <= 16_000 + 32
        # Breadcrumbs capped at 25.
        assert len(doc["breadcrumbs"]) == 25
    finally:
        await mongo.drop_database(dbname)
        mongo.close()


@pytest.mark.asyncio
async def test_get_requires_platform_admin():
    mongo, dbname, db, _anon, _admin, regular = await _isolated_app()
    try:
        client_errors_routes.setup({"db": db, "get_current_user": regular})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(client_errors_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/client-errors")
        assert r.status_code == 403
    finally:
        await mongo.drop_database(dbname)
        mongo.close()


@pytest.mark.asyncio
async def test_get_returns_newest_first_for_admin():
    mongo, dbname, db, _anon, admin, _reg = await _isolated_app()
    try:
        client_errors_routes.setup({"db": db, "get_current_user": admin})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(client_errors_routes.router)
        app.include_router(sub, prefix="/api")
        # Seed 3 errors directly.
        await db.client_errors.insert_many([
            {"message": "first", "created_at": "2026-02-28T00:00:00+00:00"},
            {"message": "second", "created_at": "2026-02-28T00:01:00+00:00"},
            {"message": "third", "created_at": "2026-02-28T00:02:00+00:00"},
        ])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/client-errors?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert [e["message"] for e in body["errors"]] == ["third", "second", "first"]
    finally:
        await mongo.drop_database(dbname)
        mongo.close()


@pytest.mark.asyncio
async def test_post_never_raises_even_with_empty_body():
    """If a crashing client somehow POSTs an empty body, we still log
    a record — never reject with 422."""
    mongo, dbname, db, anon, _admin, _reg = await _isolated_app()
    try:
        client_errors_routes.setup({"db": db, "get_current_user": anon})
        app = FastAPI()
        sub = APIRouter()
        sub.include_router(client_errors_routes.router)
        app.include_router(sub, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/client-errors", json={})
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        await mongo.drop_database(dbname)
        mongo.close()

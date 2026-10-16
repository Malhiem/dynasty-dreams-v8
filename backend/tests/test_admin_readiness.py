"""Readiness failures are safe, actionable and redact database details."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from pymongo.errors import ServerSelectionTimeoutError
from services.admin_mutations import transaction_ready
from scripts.check_admin_readiness import check


@pytest.mark.asyncio
async def test_database_outage_becomes_safe_unavailable_response():
    db = SimpleNamespace(command=AsyncMock(side_effect=ServerSelectionTimeoutError("secret-host:27017")))
    with pytest.raises(HTTPException) as error:
        await transaction_ready(db)
    assert error.value.status_code == 503
    assert "No changes were made" in error.value.detail
    assert "secret-host" not in error.value.detail


@pytest.mark.asyncio
async def test_standalone_is_not_release_ready():
    db = SimpleNamespace(command=AsyncMock(return_value={"ok": 1}))
    with pytest.raises(HTTPException) as error:
        await transaction_ready(db)
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_readiness_checks_real_transaction_and_always_aborts():
    from tests.router_test_utils import isolated_router_app
    from routes import admin_user_actions
    async with isolated_router_app(admin_user_actions, user={"_id": "000000000000000000000001", "role": "admin"}) as context:
        before = await context.db.users.count_documents({})
        assert await check(context.db) == {"ready": True, "transaction_read": "passed", "writes_performed": False}
        assert await context.db.users.count_documents({}) == before

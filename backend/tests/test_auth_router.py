"""Auth router extraction smoke tests.

Verifies all auth endpoints behave identically after extraction to /app/backend/routes/auth.py.
Endpoints: register, login, logout, /me, refresh, forgot-password, reset-password.
"""
import os
import time
import uuid
import pytest
from httpx import AsyncClient


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()


BASE = _backend_url()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


@pytest.mark.asyncio
async def test_login_admin_returns_tokens_and_cookie():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        # httpOnly cookie should be set
        cookies = r.cookies
        assert any(k for k in cookies.keys() if "token" in k.lower() or "session" in k.lower()) or len(cookies) > 0


@pytest.mark.asyncio
async def test_login_wrong_password_401():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-pass-xyz"})
        assert r.status_code in (400, 401), r.text


@pytest.mark.asyncio
async def test_me_with_bearer_token():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        login = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        tok = login.json()["access_token"]
        c.cookies.clear()
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("email") == ADMIN_EMAIL


@pytest.mark.asyncio
async def test_me_without_token_401():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.get("/api/auth/me")
        assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_refresh_with_valid_token():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        login = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        rt = login.json().get("refresh_token")
        assert rt
        c.cookies.clear()
        # Refresh accepts via cookie OR Authorization: Bearer header
        r = await c.post("/api/auth/refresh", headers={"Authorization": f"Bearer {rt}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body


@pytest.mark.asyncio
async def test_refresh_with_bogus_token_401():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/refresh", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code in (400, 401), r.text


@pytest.mark.asyncio
async def test_register_dup_email_400():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        # Admin already exists — should 400
        payload = {
            "email": ADMIN_EMAIL,
            "password": "AnotherPass1!",
            "username": f"dup{uuid.uuid4().hex[:6]}",
        }
        r = await c.post("/api/auth/register", json=payload)
        assert r.status_code in (400, 409), r.text


@pytest.mark.asyncio
async def test_register_new_user_succeeds():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "email": f"TEST_authrouter_{suffix}@example.com",
            "password": "TempPass1!",
            "username": f"TEST_user_{suffix}",
        }
        r = await c.post("/api/auth/register", json=payload)
        assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_logout_returns_200():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        login = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        tok = login.json()["access_token"]
        r = await c.post("/api/auth/logout", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_forgot_password_returns_200_for_any_email():
    """Forgot password should never leak whether email exists — always 200."""
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/forgot-password", json={"email": "TEST_noexist@example.com"})
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_reset_password_with_bogus_token_400():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/reset-password", json={"token": "bogus", "new_password": "NewPass1!"})
        assert r.status_code in (400, 401, 404), r.text

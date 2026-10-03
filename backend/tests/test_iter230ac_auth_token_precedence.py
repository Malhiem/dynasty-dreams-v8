"""
Iter 230ac — `Authorization: Bearer …` MUST win over `access_token` cookie.

Two real user-facing bugs surfaced without this precedence:
  1. chriszarek1 (live) saw chriszarek (gmail)'s notifications because
     the browser still had gmail's `access_token` cookie from an earlier
     session — the cookie was winning over chriszarek1's Bearer header.
  2. The Team page rendered Toronto Singularity (gmail's team) for
     chriszarek1 for the same reason.

This test seeds two distinct users, captures each one's login cookie +
access_token in isolation, then verifies `/auth/me` returns the
Bearer-identified user even when the request also carries a different
user's cookie.
"""
import os
import sys
import random
import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _register_isolated(suffix):
    """Register a user using a fresh AsyncClient and capture both the
    access_token AND the resulting cookie. Returning both lets the
    precedence test mix one user's cookie with another user's Bearer
    in a single request, which is exactly the cross-user bleed scenario.
    """
    suf = f"{suffix}_{random.randint(10000, 99999)}"
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        r = await client.post(
            "/api/auth/register",
            json={
                "username": f"u_{suf}",
                "email": f"u_{suf}@example.com",
                "password": "TestPass123!",
            },
        )
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        cookie = client.cookies.get("access_token")
        assert cookie, "register endpoint should set the access_token cookie"
        me = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert me.status_code == 200
        return {
            "id": me.json()["id"],
            "email": me.json()["email"],
            "access": access,
            "cookie": cookie,
        }


@pytest.mark.asyncio
async def test_bearer_header_wins_over_stale_cookie():
    """The original bug: a stale browser cookie was authenticating the
    request even when the frontend explicitly sent a different user's
    Bearer header. Verify the fix — Bearer wins regardless of cookie."""
    a = await _register_isolated("usera")
    b = await _register_isolated("userb")

    async with AsyncClient(base_url=BASE, timeout=30) as client:
        # Mix user A's cookie + user B's Bearer.
        client.cookies.set("access_token", a["cookie"])
        r = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {b['access']}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == b["email"], (
            f"Bearer header user B should win over cookie user A; "
            f"got {r.json()['email']!r} expected {b['email']!r}"
        )

        # And the inverse — mix B's cookie + A's Bearer.
        client.cookies.clear()
        client.cookies.set("access_token", b["cookie"])
        r2 = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {a['access']}"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["email"] == a["email"], (
            f"Bearer header user A should win over cookie user B; "
            f"got {r2.json()['email']!r} expected {a['email']!r}"
        )


@pytest.mark.asyncio
async def test_cookie_still_used_when_no_bearer_header():
    """Don't break cookie-only flows (SSR / direct page nav) — when no
    Bearer header is present, the cookie should still authenticate.
    """
    a = await _register_isolated("cookieonly")
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        client.cookies.set("access_token", a["cookie"])
        r = await client.get("/api/auth/me")  # no Authorization header
        assert r.status_code == 200, r.text
        assert r.json()["email"] == a["email"]


@pytest.mark.asyncio
async def test_invalid_bearer_does_not_silently_fall_back_to_cookie():
    """A malformed/expired Bearer must NOT silently fall back to the
    cookie — that would be a privilege escalation vector (an attacker
    with a stolen cookie + a junk header could pivot to cookie auth).
    """
    a = await _register_isolated("validcookie")
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        client.cookies.set("access_token", a["cookie"])
        r = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.real.jwt"},
        )
        assert r.status_code == 401, (
            "Invalid Bearer should 401, not silently fall back to cookie auth"
        )

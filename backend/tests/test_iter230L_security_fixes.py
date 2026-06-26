"""Iter 230L — Regression tests for the SEC-001 (Socket.IO auth) +
SEC-002 (team/roster read auth) security fixes.

Failing any of these means the security hardening from the audit has
been silently regressed and the app is once again leaking private team
data / accepting unauthenticated socket connections.
"""
import asyncio
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


API_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


# ─── SEC-002 — team/roster reads require auth + league membership ────────


def test_sec002_anonymous_get_teams_is_401():
    r = requests.get(f"{API_URL}/api/teams", timeout=10)
    assert r.status_code == 401, r.text


def test_sec002_anonymous_get_team_is_401():
    # Discover a real team_id first (so we test the auth gate, not the
    # 404 "Team not found" branch that fires earlier in the handler).
    tok = _login("chriszarek@gmail.com", "Chris2026!")
    teams = requests.get(
        f"{API_URL}/api/teams",
        headers={"Authorization": f"Bearer {tok}"}, timeout=10,
    ).json()
    assert teams, "seed user must have at least one team"
    team_id = teams[0]["id"]
    r = requests.get(f"{API_URL}/api/teams/{team_id}", timeout=10)
    assert r.status_code == 401, r.text


def test_sec002_anonymous_get_roster_is_401():
    tok = _login("chriszarek@gmail.com", "Chris2026!")
    teams = requests.get(
        f"{API_URL}/api/teams",
        headers={"Authorization": f"Bearer {tok}"}, timeout=10,
    ).json()
    team_id = teams[0]["id"]
    r = requests.get(f"{API_URL}/api/roster/{team_id}", timeout=10)
    assert r.status_code == 401, r.text


def test_sec002_anonymous_get_roster_detail_is_401():
    tok = _login("chriszarek@gmail.com", "Chris2026!")
    teams = requests.get(
        f"{API_URL}/api/teams",
        headers={"Authorization": f"Bearer {tok}"}, timeout=10,
    ).json()
    team_id = teams[0]["id"]
    r = requests.get(f"{API_URL}/api/roster/{team_id}/detail", timeout=10)
    assert r.status_code == 401, r.text


def test_sec002_authenticated_can_read_own_team_roster():
    """End-to-end: log in as the seed user and confirm we CAN read our
    own roster. This guards against an overly-aggressive auth gate that
    would break legitimate league members."""
    tok = _login("chriszarek@gmail.com", "Chris2026!")
    # Discover one of my teams via the now-auth'd /teams list.
    r = requests.get(
        f"{API_URL}/api/teams",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r.status_code == 200
    teams = r.json()
    assert isinstance(teams, list) and teams, "expected at least one team for seed user"
    team_id = teams[0]["id"]
    # /roster/{team_id} should now return 200 for the owner.
    r2 = requests.get(
        f"{API_URL}/api/roster/{team_id}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "team_id" in body and "players" in body


# ─── SEC-001 — Socket.IO auth handshake + room-join authorization ────────


@pytest.mark.asyncio
async def test_sec001_socket_connect_rejects_unauth():
    """Connecting without an auth token must be refused."""
    socketio = pytest.importorskip("socketio")
    sio = socketio.AsyncClient(reconnection=False)
    refused = []

    @sio.event
    async def connect_error(data):
        refused.append(data)

    try:
        await sio.connect(API_URL, socketio_path="/api/socket.io")
        await asyncio.sleep(0.5)
    except Exception as e:
        refused.append(str(e))
    try:
        await sio.disconnect()
    except Exception:
        pass

    assert refused, "unauthenticated socket connect was NOT refused"


@pytest.mark.asyncio
async def test_sec001_socket_cannot_join_other_users_room():
    """Authenticated user attempting to join `user_{victim_id}` must be
    denied via a `room_join_denied` event (NOT silently joined)."""
    socketio = pytest.importorskip("socketio")
    tok = _login("chriszarek@gmail.com", "Chris2026!")
    me = requests.get(
        f"{API_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    ).json()
    my_uid = me["id"]
    victim = "0000000000000000deadbeef"

    sio = socketio.AsyncClient(reconnection=False)
    denied: dict = {}
    joined: dict = {}

    @sio.event
    async def user_joined(d):
        joined.update(d or {})

    @sio.event
    async def room_join_denied(d):
        denied.update(d or {})

    await sio.connect(
        API_URL,
        socketio_path="/api/socket.io",
        auth={"token": tok},
    )
    await asyncio.sleep(0.3)
    # Attempt to invade victim's room.
    await sio.emit("join_room", {"room_id": f"user_{victim}", "user_id": victim})
    await asyncio.sleep(0.5)
    assert denied.get("reason") == "not_authorized", denied
    assert not joined, f"victim room join leaked: {joined}"
    # Sanity: caller can still join their OWN room.
    denied.clear()
    joined.clear()
    await sio.emit("join_room", {"room_id": f"user_{my_uid}", "user_id": my_uid})
    await asyncio.sleep(0.5)
    assert not denied
    assert joined.get("room_id") == f"user_{my_uid}"
    await sio.disconnect()

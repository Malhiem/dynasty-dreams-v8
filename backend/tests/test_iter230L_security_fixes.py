"""Security regressions against a disposable HTTP API and matching Mongo DB."""
import asyncio

import pytest
import requests
import socketio

from security_http_fixtures import API_URL, security_db, security_users, private_team


def test_sec002_anonymous_get_teams_is_401():
    r = requests.get(f"{API_URL}/api/teams", timeout=10)
    assert r.status_code == 401, r.text


def _assert_anonymous_denied(path):
    r = requests.get(f"{API_URL}/api/{path}", timeout=10)
    assert r.status_code == 401, r.text


def test_sec002_anonymous_get_team_is_401(private_team):
    _assert_anonymous_denied(f"teams/{private_team['id']}")
    _assert_anonymous_denied("teams/000000000000000000000000")


def test_sec002_anonymous_get_roster_is_401(private_team):
    _assert_anonymous_denied(f"roster/{private_team['id']}")
    _assert_anonymous_denied("roster/000000000000000000000000")


def test_sec002_anonymous_get_roster_detail_is_401(private_team):
    _assert_anonymous_denied(f"roster/{private_team['id']}/detail")
    _assert_anonymous_denied("roster/000000000000000000000000/detail")


def test_sec002_authenticated_can_read_own_team_roster(private_team):
    r = requests.get(f"{API_URL}/api/roster/{private_team['id']}",
                     headers=private_team['owner']['headers'], timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["team_id"] == private_team["id"]
    assert "players" in r.json()


@pytest.mark.asyncio
async def test_sec001_socket_connect_rejects_unauth(security_users):
    # A working authenticated connection prevents an outage from passing this test.
    user = security_users()
    healthy = socketio.AsyncClient(reconnection=False)
    anonymous = socketio.AsyncClient(reconnection=False)
    refused = []
    @anonymous.event
    async def connect_error(data):
        refused.append(data)
    try:
        await healthy.connect(API_URL, socketio_path="/api/socket.io", auth={"token": user["access_token"]})
        assert healthy.connected
        with pytest.raises(socketio.exceptions.ConnectionError):
            await anonymous.connect(API_URL, socketio_path="/api/socket.io")
        assert refused, "Expected an application handshake refusal"
        assert "authentication required" in str(refused).lower(), refused
        assert not anonymous.connected
    finally:
        await anonymous.disconnect()
        await healthy.disconnect()


@pytest.mark.asyncio
async def test_sec001_socket_cannot_join_other_users_room(security_users):
    user, victim = security_users(), security_users()
    sio = socketio.AsyncClient(reconnection=False)
    events = asyncio.Queue()
    @sio.event
    async def user_joined(data):
        await events.put(("joined", data))
    @sio.event
    async def room_join_denied(data):
        await events.put(("denied", data))
    try:
        await sio.connect(API_URL, socketio_path="/api/socket.io", auth={"token": user["access_token"]})
        await sio.emit("join_room", {"room_id": f"user_{victim['id']}", "user_id": victim['id']})
        kind, data = await asyncio.wait_for(events.get(), 5)
        assert kind == "denied", data
        assert data == {"room_id": f"user_{victim['id']}", "reason": "not_authorized"}
        await sio.emit("join_room", {"room_id": f"user_{user['id']}", "user_id": victim['id']})
        kind, data = await asyncio.wait_for(events.get(), 5)
        assert kind == "joined", data
        assert data["room_id"] == f"user_{user['id']}"
    finally:
        await sio.disconnect()

"""No cap, no salaries: league-view API responses omit player salary figures
when the league's salary cap is disabled, and keep them when it is enabled."""
import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users, private_team  # noqa: F401


def _set_cap(db, league_id, enabled):
    db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {
        "salary_cap_enabled": enabled, "salary_cap": 80_000_000 if enabled else None}})


def _seed_player(db, team_id):
    pid = db.players.insert_one({
        "name": "TEST_nocap_player", "position": "C", "team": "TOR",
        "salary": 5_000_000, "cap_hit": 5_000_000,
        "contract": {"salary": 5_000_000, "aav": 5_000_000, "yearsRemaining": 2},
    }).inserted_id
    db.teams.update_one({"_id": ObjectId(team_id)}, {"$set": {"roster": [str(pid)]}})
    return pid


def _truncated(private_team):
    r = requests.get(f"{API_URL}/api/teams/{private_team['id']}/roster-truncated",
                     headers=private_team["owner"]["headers"], timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["players"]


def test_roster_truncated_omits_cap_hit_when_cap_disabled(private_team, security_db):
    pid = _seed_player(security_db, private_team["id"])
    try:
        _set_cap(security_db, private_team["league_id"], False)
        players = _truncated(private_team)
        assert players and all("cap_hit" not in p for p in players), players
        _set_cap(security_db, private_team["league_id"], True)
        players = _truncated(private_team)
        assert players[0]["cap_hit"] == 5_000_000
    finally:
        security_db.players.delete_one({"_id": pid})


def _block_item(db, private_team, pid):
    return db.trade_block.insert_one({
        "league_id": private_team["league_id"], "team_id": private_team["id"],
        "player_id": str(pid), "created_at": "2026-01-01T00:00:00Z"}).inserted_id


def test_trade_block_omits_aav_when_cap_disabled(private_team, security_db):
    pid = _seed_player(security_db, private_team["id"])
    item = _block_item(security_db, private_team, pid)
    try:
        for enabled in (False, True):
            _set_cap(security_db, private_team["league_id"], enabled)
            r = requests.get(f"{API_URL}/api/trade-block", params={"league_id": private_team["league_id"]},
                             headers=private_team["owner"]["headers"], timeout=10)
            assert r.status_code == 200, r.text
            rows = [i for i in r.json() if i.get("player_id") == str(pid)]
            assert rows, r.text
            if enabled:
                assert rows[0].get("aav") == 5_000_000
            else:
                assert rows[0].get("aav") is None
    finally:
        security_db.trade_block.delete_one({"_id": item})
        security_db.players.delete_one({"_id": pid})


async def test_trade_hydration_omits_salary_when_cap_disabled(private_team, security_db):
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    from routes.trade_hydration import _hydrate_side

    pid = _seed_player(security_db, private_team["id"])
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    adb = client[os.environ["DB_NAME"]]
    try:
        for enabled in (False, True):
            _set_cap(security_db, private_team["league_id"], enabled)
            asset = {"player_id": str(pid), "asset_type": "player", "salary": 1, "cap_hit": 1}
            out = await _hydrate_side(adb, private_team["league_id"], {}, None, [asset])
            if enabled:
                assert out[0]["cap_hit"] == 5_000_000
            else:
                assert "salary" not in out[0] and "cap_hit" not in out[0]
    finally:
        client.close()
        security_db.players.delete_one({"_id": pid})

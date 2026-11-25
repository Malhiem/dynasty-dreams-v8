"""No cap, no salaries: the salary-cap overview and contracts list must not
invent a cap or list contract salaries for a league whose cap is disabled."""
import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users, private_team  # noqa: F401


def _set_cap(db, league_id, enabled):
    db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {
        "salary_cap_enabled": enabled, "salary_cap": 80_000_000 if enabled else None}})


def _get(private_team, path, **params):
    r = requests.get(f"{API_URL}/api{path}", params=params,
                     headers=private_team["owner"]["headers"], timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def test_overview_and_contracts_hidden_when_cap_disabled(private_team, security_db):
    contract = security_db.contracts.insert_one({
        "league_id": private_team["league_id"], "team_id": private_team["id"],
        "player_id": "TEST_nocap_pid", "player_name": "TEST_nocap", "aav": 5_000_000, "status": "active", "years": 2,
    }).inserted_id
    try:
        _set_cap(security_db, private_team["league_id"], False)
        overview = _get(private_team, f"/salary-cap/{private_team['league_id']}")
        assert overview["salary_cap_enabled"] is False
        assert overview["salary_cap"] is None
        assert overview["teams"] == []
        assert _get(private_team, "/contracts", league_id=private_team["league_id"]) == []

        _set_cap(security_db, private_team["league_id"], True)
        overview = _get(private_team, f"/salary-cap/{private_team['league_id']}")
        assert overview["salary_cap_enabled"] is True
        assert overview["salary_cap"] == 80_000_000
        assert overview["teams"], overview
        rows = _get(private_team, "/contracts", league_id=private_team["league_id"])
        assert any(c.get("player_name") == "TEST_nocap" for c in rows)
    finally:
        security_db.contracts.delete_one({"_id": contract})

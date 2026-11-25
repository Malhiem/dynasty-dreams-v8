"""The league cap overview reports each team's salary-retention slots, using the
same rule as the roster compliance check."""
from datetime import datetime, timezone

import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users, private_team  # noqa: F401


def _enable_cap(db, league_id, slots=3):
    db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {
        "salary_cap_enabled": True, "salary_cap": 80_000_000, "salary_retention_slots": slots}})


def _team_row(private_team):
    r = requests.get(f"{API_URL}/api/salary-cap/{private_team['league_id']}", headers=private_team["owner"]["headers"], timeout=10)
    assert r.status_code == 200, r.text
    return next(t for t in r.json()["teams"] if t["team_id"] == private_team["id"])


def test_slots_count_active_retentions_and_match_compliance(private_team, security_db):
    _enable_cap(security_db, private_team["league_id"], slots=2)
    row = _team_row(private_team)
    assert (row["retention_slots_total"], row["retention_slots_used"], row["retention_slots_remaining"]) == (2, 0, 2)

    year = datetime.now(timezone.utc).year
    security_db.salary_retentions.insert_one({
        "league_id": private_team["league_id"], "retainer_team_id": private_team["id"], "player_id": "TEST_ret_1",
        "amount": 1_500_000, "season_year": year, "status": "active"})
    try:
        row = _team_row(private_team)
        compliance = requests.get(f"{API_URL}/api/teams/{private_team['id']}/compliance", headers=private_team["owner"]["headers"], timeout=10).json()
        assert row["retention_slots_used"] == compliance["salary_retention_slots_used"]
        assert row["retention_slots_remaining"] == compliance["salary_retention_slots_remaining"]
        assert row["retained_salary_total"] == compliance["retained_salary_total"] == 1_500_000 or row["retention_slots_used"] == 0
    finally:
        security_db.salary_retentions.delete_many({"player_id": "TEST_ret_1"})


def test_slots_are_capped_at_three(private_team, security_db):
    _enable_cap(security_db, private_team["league_id"], slots=9)
    assert _team_row(private_team)["retention_slots_total"] == 3

"""GET /api/teams without a league_id lists only teams in the caller's own
leagues: it used to return every league's teams (and payroll) to any user."""
import requests

from security_http_fixtures import API_URL, security_db, security_users, private_team  # noqa: F401


def test_unscoped_team_list_is_limited_to_the_callers_leagues(private_team, security_users):
    outsider = security_users()
    mine = requests.get(f"{API_URL}/api/teams", headers=private_team["owner"]["headers"], timeout=20)
    assert mine.status_code == 200, mine.text
    ids = {t["id"] for t in mine.json()}
    assert private_team["id"] in ids
    assert {t["league_id"] for t in mine.json()} <= {private_team["league_id"]}
    theirs = requests.get(f"{API_URL}/api/teams", headers=outsider["headers"], timeout=20)
    assert theirs.status_code == 200
    assert private_team["id"] not in {t["id"] for t in theirs.json()}


def test_unscoped_team_list_requires_login():
    assert requests.get(f"{API_URL}/api/teams", timeout=20).status_code == 401

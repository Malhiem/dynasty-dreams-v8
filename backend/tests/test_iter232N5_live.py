"""Live end-to-end tests for iter232N.5 via public URL."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")},
               timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def test_feed_scope_user(sess):
    r = sess.get(f"{BASE}/api/player-status/feed", params={"scope": "user", "days": 14}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "players" in data and "total_updates" in data
    assert isinstance(data["players"], list)


def test_feed_scope_league(sess):
    r = sess.get(f"{BASE}/api/player-status/feed",
                 params={"scope": "league", "league_id": "69e46af167999bfb85c39629", "days": 14},
                 timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "players" in data


def test_feed_scope_team_invalid_id_safe(sess):
    # Invalid ObjectId should be handled gracefully (500 not acceptable)
    r = sess.get(f"{BASE}/api/player-status/feed",
                 params={"scope": "team", "team_id": "000000000000000000000000", "days": 14},
                 timeout=30)
    # Missing team → empty result
    assert r.status_code == 200, r.text
    assert r.json()["players"] == []


def test_feed_requires_auth():
    r = requests.get(f"{BASE}/api/player-status/feed", params={"scope": "user"}, timeout=30)
    assert r.status_code in (401, 403), r.text


def test_players_include_my_team_flag_accepted(sess):
    # Find user's team
    tr = sess.get(f"{BASE}/api/teams", params={"owner_id": "me"}, timeout=30)
    if tr.status_code != 200:
        pytest.skip(f"teams endpoint returned {tr.status_code}")
    teams = tr.json() if isinstance(tr.json(), list) else tr.json().get("teams", [])
    if not teams:
        pytest.skip("no team for user")
    team_id = str(teams[0].get("_id") or teams[0].get("id"))
    league_id = str(teams[0].get("league_id"))

    r_off = sess.get(f"{BASE}/api/players",
                     params={"league_id": league_id, "exclude_team_id": team_id, "limit": 20},
                     timeout=30)
    r_on = sess.get(f"{BASE}/api/players",
                    params={"league_id": league_id, "exclude_team_id": team_id,
                            "include_my_team": "true", "limit": 20},
                    timeout=30)
    assert r_off.status_code == 200, r_off.text
    assert r_on.status_code == 200, r_on.text
    off = r_off.json().get("players", [])
    on = r_on.json().get("players", [])
    # include_my_team should return >= count of off
    assert len(on) >= len(off)

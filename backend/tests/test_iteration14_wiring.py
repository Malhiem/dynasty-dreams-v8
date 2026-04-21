"""
Iteration 14 backend tests — Roster detail, Team roster fields, Matchup keys, Live scoring.
Covers review request items 1, 2, 3, 4, 8, 9.
"""
import os
import pytest
import requests

def _load_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return url.rstrip("/")

BASE_URL = _load_url()
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
KNOWN_LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings H2H
KNOWN_TEAM_ID = "69e59b30cbd3fea02a914c61"  # Zarek's Frozen


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ----- 1. Auth/me -----
def test_auth_me(session):
    r = session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == EMAIL


# ----- 9. Leagues regression -----
def test_my_leagues(session):
    r = session.get(f"{BASE_URL}/api/leagues?my_leagues=true")
    assert r.status_code == 200
    leagues = r.json()
    assert isinstance(leagues, list)
    assert len(leagues) >= 5, f"Expected >=5 leagues, got {len(leagues)}"


# ----- 2. Teams payload now includes roster, live_points, logo_abbr -----
def test_teams_include_roster_and_live_points(session):
    r = session.get(f"{BASE_URL}/api/leagues?my_leagues=true")
    leagues = r.json()
    failures = []
    for lg in leagues:
        lid = lg["id"]
        rt = session.get(f"{BASE_URL}/api/teams?league_id={lid}")
        assert rt.status_code == 200, f"teams for {lid} -> {rt.status_code}"
        teams = rt.json()
        assert isinstance(teams, list) and len(teams) > 0
        for t in teams:
            for key in ("roster", "live_points", "logo_abbr"):
                if key not in t:
                    failures.append(f"League {lg['name']} team {t.get('name')} missing {key}")
            if "roster" in t:
                rl = len(t["roster"])
                if rl < 15:  # league rosters are 20-28
                    failures.append(f"League {lg['name']} team {t.get('name')} roster len={rl}")
    assert not failures, "\n".join(failures[:10])


# ----- 3. NEW: /api/roster/{team_id}/detail -----
def test_roster_detail_zarek(session):
    r = session.get(f"{BASE_URL}/api/roster/{KNOWN_TEAM_ID}/detail")
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    for key in ("team_id", "team_name", "league_id", "league_name",
                "wins", "losses", "ties", "season_fpts", "live_fpts", "players"):
        assert key in data, f"missing {key}"
    assert data["team_id"] == KNOWN_TEAM_ID
    assert isinstance(data["players"], list)
    assert len(data["players"]) >= 20, f"expected >=20 players, got {len(data['players'])}"

    # Verify player shape on first player
    p0 = data["players"][0]
    for key in ("id", "name", "position", "team", "eligiblePositions",
                "age", "dynastyValue", "trend", "contract",
                "statsByPeriod", "categoryBreakdown", "rosterSection"):
        assert key in p0, f"player missing {key}: {list(p0.keys())}"
    for ck in ("salary", "yearsRemaining", "type"):
        assert ck in p0["contract"], f"contract missing {ck}"

    # McDavid should be in starting C1
    mcdavid = next((p for p in data["players"] if "McDavid" in p["name"]), None)
    assert mcdavid is not None, "McDavid not on roster"
    assert mcdavid.get("rosterSection") == "starting", f"McDavid section={mcdavid.get('rosterSection')}"
    assert mcdavid.get("rosterSlotId") == "C1", f"McDavid slot={mcdavid.get('rosterSlotId')}"

    # All starters should have a rosterSlotId
    starters = [p for p in data["players"] if p.get("rosterSection") == "starting"]
    assert len(starters) >= 9, f"expected ~10 starters, got {len(starters)}"
    for s in starters:
        assert s.get("rosterSlotId"), f"starter {s['name']} missing rosterSlotId"


def test_roster_detail_invalid_id(session):
    r = session.get(f"{BASE_URL}/api/roster/notavalidid/detail")
    assert r.status_code in (400, 404), f"expected 400/404, got {r.status_code}"


# ----- 4. Matchup current week uses home_team_id/away_team_id -----
def test_matchup_current_week_keys():
    r = requests.get(f"{BASE_URL}/api/matchups/{KNOWN_LEAGUE_ID}/current-week")
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    assert "week" in data
    assert "matchups" in data
    assert isinstance(data["matchups"], list)
    assert len(data["matchups"]) >= 1
    m0 = data["matchups"][0]
    assert "home_team_id" in m0, f"missing home_team_id: {list(m0.keys())}"
    assert "away_team_id" in m0, f"missing away_team_id: {list(m0.keys())}"
    assert "team1_id" not in m0, "old team1_id key still present"
    assert "team2_id" not in m0, "old team2_id key still present"


# ----- 8. Live scoring still works -----
def test_live_scoring_team(session):
    r = session.get(f"{BASE_URL}/api/live-scoring/team/{KNOWN_TEAM_ID}")
    assert r.status_code == 200
    data = r.json()
    assert "live_points" in data or "total_points" in data or "fpts" in data
    pts = data.get("live_points") or data.get("total_points") or data.get("fpts") or 0
    assert pts != 0, f"Expected non-zero live points, got {pts}: {data}"

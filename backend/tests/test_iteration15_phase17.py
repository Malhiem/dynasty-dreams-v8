"""
Phase 17 Backend regression tests:
- /api/salary-cap
- /api/roster/{id}/detail (realistic salaries)
- /api/activity/{league_id}
- /api/trades
- /api/trade-block (now filtered by league_id)
- /api/waivers/* endpoints
- /api/drafts/{id}/board
- /api/leagues/{id}/standings
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dynasty-preview.preview.emergentagent.com').rstrip('/')
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def ice_kings_league_id(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/leagues", timeout=15)
    assert r.status_code == 200, r.text
    leagues = r.json()
    for lg in leagues:
        name = lg.get("name", "")
        if "Ice Kings" in name:
            return lg.get("id") or lg.get("_id")
    # fallback first
    assert leagues, "No leagues for user"
    return leagues[0].get("id") or leagues[0].get("_id")


@pytest.fixture(scope="module")
def my_team_id(auth_session, ice_kings_league_id):
    r = auth_session.get(f"{BASE_URL}/api/teams?league_id={ice_kings_league_id}", timeout=15)
    assert r.status_code == 200, r.text
    teams = r.json()
    me = auth_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
    user_id = me.get("id") or me.get("_id")
    for t in teams:
        if t.get("owner_id") == user_id or t.get("user_id") == user_id:
            return t.get("id") or t.get("_id")
    return teams[0].get("id") or teams[0].get("_id")


# 1. Salary Cap
class TestSalaryCap:
    def test_salary_cap_endpoint(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/salary-cap?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code in (200, 404), f"{r.status_code}: {r.text[:200]}"
        if r.status_code == 200:
            data = r.json()
            print(f"Salary cap response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

    def test_roster_detail_realistic_salary(self, auth_session, my_team_id):
        r = auth_session.get(f"{BASE_URL}/api/roster/{my_team_id}/detail", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        players = data.get("players") or data.get("roster") or data
        assert isinstance(players, list) and len(players) > 0
        print(f"Roster has {len(players)} players")
        # Find McDavid
        mcdavid = next((p for p in players if "McDavid" in (p.get("name", "") or p.get("player_name", ""))), None)
        if mcdavid:
            salary = mcdavid.get("salary") or mcdavid.get("cap_hit") or 0
            print(f"McDavid salary: {salary}")
            # Realistic salary: $11M-$15M (in dollars or millions)
            assert salary < 20_000_000, f"McDavid salary unrealistic: {salary}"
        # All player salaries should be reasonable
        for p in players:
            sal = p.get("salary") or p.get("cap_hit") or 0
            assert sal < 50_000_000, f"Unrealistic salary: {p.get('name')}={sal}"


# 2. Transactions / Activity
class TestTransactions:
    def test_activity_endpoint(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/activity/{ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text
        events = r.json()
        if isinstance(events, dict):
            events = events.get("items", [])
        assert isinstance(events, list), type(events)
        print(f"Activity events: {len(events)}")
        assert len(events) >= 9, f"Expected >=9 events, got {len(events)}"

    def test_trades_endpoint(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/trades?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text
        trades = r.json()
        assert isinstance(trades, list)


# 3. Trade Block
class TestTradeBlock:
    def test_trade_block_filtered_by_league(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/trade-block?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        print(f"Trade block items in Ice Kings: {len(items)}")
        # Should be ~8 not 40
        assert len(items) <= 20, f"Expected <=20 (league filtered), got {len(items)}"
        # Validate filtering: all entries should belong to this league
        for item in items:
            lg = item.get("league_id")
            if lg:
                assert lg == ice_kings_league_id, f"Cross-league leak: {lg} != {ice_kings_league_id}"


# 4. Waivers
class TestWaivers:
    def test_waivers_available(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/waivers/available?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        players = data if isinstance(data, list) else data.get("players", [])
        assert isinstance(players, list)
        print(f"Waiver available players: {len(players)}")

    def test_waivers_claims(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/waivers/claims?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text

    def test_waivers_history(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/waivers/history?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text

    def test_waivers_budget(self, auth_session, my_team_id, ice_kings_league_id):
        # Try with team_id; fallback league_id
        r = auth_session.get(f"{BASE_URL}/api/waivers/budget?team_id={my_team_id}", timeout=15)
        if r.status_code != 200:
            r = auth_session.get(f"{BASE_URL}/api/waivers/budget?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text

    def test_waivers_order(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/waivers/order?league_id={ice_kings_league_id}", timeout=15)
        assert r.status_code == 200, r.text


# 5. Draft Board
class TestDraftBoard:
    def test_draft_board(self, auth_session, ice_kings_league_id):
        # Get drafts for league
        r = auth_session.get(f"{BASE_URL}/api/drafts?league_id={ice_kings_league_id}", timeout=15)
        if r.status_code != 200:
            pytest.skip(f"Drafts list endpoint not available: {r.status_code}")
        drafts = r.json()
        if not drafts:
            pytest.skip("No drafts for league")
        draft_id = drafts[0].get("id") or drafts[0].get("_id")
        r2 = auth_session.get(f"{BASE_URL}/api/drafts/{draft_id}/board", timeout=15)
        assert r2.status_code == 200, r2.text


# 6. Analytics
class TestAnalytics:
    def test_standings(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/leagues/{ice_kings_league_id}/standings", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        standings = data if isinstance(data, list) else data.get("standings", [])
        assert len(standings) > 0
        # Total league FPTS
        total_fpts = sum(float(t.get("points_for") or t.get("fpts") or t.get("live_points") or 0) for t in standings)
        print(f"Total league FPTS: {total_fpts}")


# 9. Phase 14-16 spot-check
class TestPriorPhases:
    def test_roster_endpoint(self, auth_session, my_team_id):
        r = auth_session.get(f"{BASE_URL}/api/roster/{my_team_id}", timeout=15)
        assert r.status_code == 200

    def test_matchup_endpoint(self, auth_session, ice_kings_league_id):
        r = auth_session.get(f"{BASE_URL}/api/leagues/{ice_kings_league_id}/matchups", timeout=15)
        assert r.status_code in (200, 404)

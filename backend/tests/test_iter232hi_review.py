"""End-to-end review verification for iter 232h security fixes + 232i bonus picks.

Tests SEC-001 (chat channels league membership), SEC-002 (email leak in members),
and the new bonus picks API (list/add/delete + non-commissioner 403).
"""
import os
import requests
import pytest
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CHRIS_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
CHRIS_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def chris_token():
    return _login(CHRIS_EMAIL, CHRIS_PASSWORD)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def non_member_token(_global_pollution_sweep):
    """An ordinary disposable account with no league memberships."""
    from uuid import uuid4
    suffix = uuid4().hex[:12]
    email = f"TEST_outsider_{suffix}@e2e.dynastydreams.com"
    response = requests.post(f"{API}/auth/register", json={"email": email, "username": f"outsider_{suffix}", "password": "TestOutsider1!"}, timeout=15)
    assert response.status_code == 200, response.text
    return _login(email, "TestOutsider1!")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Discover a league where throwaway user is a non-member ----------
@pytest.fixture(scope="module")
def any_league_id(chris_token):
    # Grab any league; use it as target for SEC tests (throwaway user is guaranteed non-member).
    r = requests.get(f"{API}/leagues", headers=_h(chris_token), timeout=15)
    assert r.status_code == 200
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    assert leagues, "no leagues available for SEC test"
    return str(leagues[0].get("id") or leagues[0].get("_id"))


# --------------------------- SEC-001 ---------------------------
class TestSEC001ChatChannelsMembership:
    def test_non_member_channels_list_403(self, non_member_token, any_league_id):
        r = requests.get(
            f"{API}/chat/channels", params={"league_id": any_league_id},
            headers=_h(non_member_token), timeout=15,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
        assert "not a member" in r.text.lower()

    def test_non_member_fake_channel_messages(self, non_member_token):
        fake_id = "0" * 24
        r = requests.get(
            f"{API}/chat/channels/{fake_id}/messages",
            headers=_h(non_member_token), timeout=15,
        )
        assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}"

    def test_non_member_post_message_denied(self, non_member_token):
        fake_id = "0" * 24
        r = requests.post(
            f"{API}/chat/channels/{fake_id}/messages",
            headers=_h(non_member_token),
            json={"content": "spoof"}, timeout=15,
        )
        assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}: {r.text[:200]}"


# --------------------------- SEC-002 ---------------------------
class TestSEC002MembersEmailLeak:
    def test_non_member_members_403(self, non_member_token, any_league_id):
        r = requests.get(
            f"{API}/chat/league/{any_league_id}/members",
            headers=_h(non_member_token), timeout=15,
        )
        assert r.status_code == 403

    def test_member_members_no_email(self, chris_token):
        # Find a league where Chris is a member (any league he can see).
        r = requests.get(f"{API}/leagues", headers=_h(chris_token), timeout=15)
        leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
        assert leagues
        checked = 0
        for lg in leagues[:5]:
            lg_id = str(lg.get("id") or lg.get("_id"))
            m = requests.get(f"{API}/chat/league/{lg_id}/members", headers=_h(chris_token), timeout=15)
            if m.status_code != 200:
                continue
            checked += 1
            members = m.json().get("members", [])
            for row in members:
                assert "email" not in row, f"email leaked in member row: {row}"
        assert checked > 0, "chris was not a member of any tried league (unexpected)"


# --------------------------- Bonus Picks ---------------------------
@pytest.fixture(scope="module")
def commissioner_draft(chris_token):
    """Find a draft where Chris is the commissioner."""
    r = requests.get(f"{API}/leagues", headers=_h(chris_token), timeout=15)
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    for lg in leagues:
        lg_id = str(lg.get("id") or lg.get("_id"))
        commish = lg.get("commissioner_id")
        # Look up drafts for the league
        d = requests.get(f"{API}/drafts", params={"league_id": lg_id}, headers=_h(chris_token), timeout=15)
        if d.status_code != 200:
            continue
        drafts = d.json() if isinstance(d.json(), list) else d.json().get("drafts", [])
        for draft in drafts:
            draft_id = str(draft.get("id") or draft.get("_id"))
            # Try listing bonus-picks to confirm we're commissioner
            lb = requests.get(f"{API}/drafts/{draft_id}/bonus-picks", headers=_h(chris_token), timeout=15)
            if lb.status_code == 200:
                return {"draft_id": draft_id, "league_id": lg_id, "draft": draft}
    pytest.skip("No draft found where Chris is commissioner")


class TestBonusPicks:
    def test_list_bonus_picks(self, chris_token, commissioner_draft):
        r = requests.get(
            f"{API}/drafts/{commissioner_draft['draft_id']}/bonus-picks",
            headers=_h(chris_token), timeout=15,
        )
        assert r.status_code == 200
        assert "bonus_picks" in r.json()

    def test_add_bonus_pick_end_of_round(self, chris_token, commissioner_draft):
        # Fetch draft detail to get team_map + status
        d_id = commissioner_draft["draft_id"]
        # get teams in this league
        lg_id = commissioner_draft["league_id"]
        tr = requests.get(f"{API}/teams", params={"league_id": lg_id}, headers=_h(chris_token), timeout=15)
        teams = tr.json() if isinstance(tr.json(), list) else tr.json().get("teams", [])
        assert teams, "no teams found for league"
        team_id = str(teams[0].get("id") or teams[0].get("_id"))
        draft = commissioner_draft["draft"]
        status = draft.get("status", "unknown")
        total_rounds = int(draft.get("total_rounds") or 5)
        payload = {
            "team_id": team_id,
            "bonus_kind": "compensation",
            "position_mode": "end_of_round",
            "after_round": 1 if total_rounds >= 1 else 1,
            "tradeable": True,
            "note": "test iter232i",
        }
        r = requests.post(f"{API}/drafts/{d_id}/bonus-picks", json=payload, headers=_h(chris_token), timeout=15)
        # Scheduled → 200 add success. Completed/active-past-pick → 409/422 acceptable.
        assert r.status_code in (200, 409, 422), f"unexpected {r.status_code}: {r.text[:300]}"
        if r.status_code == 200:
            pick = r.json().get("bonus_pick")
            assert pick and pick.get("bonus_kind") == "compensation"
            assert pick.get("team_id") == team_id
            # Cleanup: delete it
            pid = pick["id"]
            dr = requests.delete(f"{API}/drafts/{d_id}/bonus-picks/{pid}", headers=_h(chris_token), timeout=15)
            assert dr.status_code == 200

    def test_add_bonus_pick_overall_mode(self, chris_token, commissioner_draft):
        d_id = commissioner_draft["draft_id"]
        lg_id = commissioner_draft["league_id"]
        tr = requests.get(f"{API}/teams", params={"league_id": lg_id}, headers=_h(chris_token), timeout=15)
        teams = tr.json() if isinstance(tr.json(), list) else tr.json().get("teams", [])
        team_id = str(teams[0].get("id") or teams[0].get("_id"))
        draft = commissioner_draft["draft"]
        team_count = len(draft.get("team_abbrs") or teams)
        total_rounds = int(draft.get("total_rounds") or 5)
        overall_pos = max(1, team_count * total_rounds)
        payload = {
            "team_id": team_id,
            "bonus_kind": "expansion",
            "position_mode": "overall",
            "overall_position": overall_pos,
            "tradeable": False,
            "note": "expansion test",
        }
        r = requests.post(f"{API}/drafts/{d_id}/bonus-picks", json=payload, headers=_h(chris_token), timeout=15)
        assert r.status_code in (200, 409, 422), f"unexpected {r.status_code}: {r.text[:300]}"
        if r.status_code == 200:
            pick = r.json().get("bonus_pick")
            assert pick.get("bonus_kind") == "expansion"
            pid = pick["id"]
            dr = requests.delete(f"{API}/drafts/{d_id}/bonus-picks/{pid}", headers=_h(chris_token), timeout=15)
            assert dr.status_code == 200

    def test_non_commissioner_add_403(self, non_member_token, commissioner_draft):
        payload = {
            "team_id": "0" * 24,
            "bonus_kind": "compensation",
            "position_mode": "end_of_round",
            "after_round": 1,
        }
        r = requests.post(
            f"{API}/drafts/{commissioner_draft['draft_id']}/bonus-picks",
            json=payload, headers=_h(non_member_token), timeout=15,
        )
        # Non-league-member -> 403 or 404 (either is acceptable, so long as not 200/422 for input parsing)
        assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}: {r.text[:200]}"


# --------------------------- Regression: LastUpdatedBadge endpoint smoke ---------------------------
class TestRegression:
    def test_leagues_endpoint_reachable(self, chris_token):
        r = requests.get(f"{API}/leagues", headers=_h(chris_token), timeout=15)
        assert r.status_code == 200

    def test_users_me(self, chris_token):
        r = requests.get(f"{API}/auth/me", headers=_h(chris_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == CHRIS_EMAIL

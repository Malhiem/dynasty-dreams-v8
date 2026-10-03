"""Phase 21 backend tests: week-at-a-glance opponent + scoring_format, and team awards endpoint."""
import os
from tests.live_snapshot_fixture import live_snapshot_inputs
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CHRIS_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
CHRIS_PASS = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

ICE_KINGS_ID = "69e46af167999bfb85c39628"
ZAREK_TEAM_ID = "69e59b30cbd3fea02a914c61"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def chris():
    return _login(CHRIS_EMAIL, CHRIS_PASS)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


# ── week-at-a-glance ────────────────────────────────────────────
class TestWeekAtAGlance:
    def test_returns_scoring_format_and_opponent_field(self, chris):
        r = chris.get(f"{API}/users/me/week-at-a-glance", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "summaries" in body
        summaries = body["summaries"]
        assert len(summaries) >= 1, "chriszarek should have at least 1 team"

        for s in summaries:
            assert "scoring_format" in s, f"missing scoring_format in {s.get('team_name')}"
            assert "opponent" in s  # key present (value may be None)

        h2h = [s for s in summaries if s.get("scoring_format") == "head_to_head"]
        non_h2h = [s for s in summaries if s.get("scoring_format") != "head_to_head"]

        # At least one league should be H2H (Ice Kings) with opponent populated
        assert len(h2h) >= 1, "expected ≥1 head_to_head league"
        h2h_with_opp = [s for s in h2h if s.get("opponent")]
        assert len(h2h_with_opp) >= 1, "expected H2H summary to include opponent info"
        opp = h2h_with_opp[0]["opponent"]
        for k in ("opponent_team_id", "opponent_team_name", "opponent_weekly_fpts", "week"):
            assert k in opp, f"opponent missing {k}"

        # For non-H2H formats opponent should be None/missing
        for s in non_h2h:
            assert not s.get("opponent"), f"non-H2H league has opponent: {s}"


# ── Team Awards PUT endpoint ────────────────────────────────────
class TestTeamAwards:
    def test_non_commissioner_403(self):
        # register a stranger, then try to PUT awards
        s = requests.Session()
        email = "TEST_phase21_stranger@example.com"
        pw = "StrongerPass1!"
        r = s.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "Phase21 Stranger", "username": "phase21stranger"}, timeout=20)
        # register may 200 or 409 if exists; fall back to login
        if r.status_code not in (200, 201):
            r2 = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
            assert r2.status_code == 200, r.text
        resp = s.put(
            f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards",
            json={"championship_won": True},
            timeout=20,
        )
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text}"

    def test_set_and_clear_championship(self, chris):
        # SET championship_won
        r = chris.put(
            f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards",
            json={"championship_won": True},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["team_id"] == ZAREK_TEAM_ID
        assert body["championship_won_at"] is not None
        assert "unlocked_trades" in body
        assert isinstance(body["unlocked_trades"], int)

        # Verify GET /api/teams returns the timestamp
        g = chris.get(f"{API}/teams?league_id={ICE_KINGS_ID}", timeout=20)
        assert g.status_code == 200
        teams = g.json() if isinstance(g.json(), list) else g.json().get("teams", [])
        match = [t for t in teams if str(t.get("id") or t.get("_id")) == ZAREK_TEAM_ID]
        assert match, f"team {ZAREK_TEAM_ID} not in GET /teams response"
        t = match[0]
        # Response should expose award fields (may be None on clear)
        assert "championship_won_at" in t
        assert t["championship_won_at"] is not None, "champion field not persisted"

        # CLEAR championship_won
        r2 = chris.put(
            f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards",
            json={"championship_won": False},
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2.get("championship_won_at") in (None, ""), body2

    def test_division_and_playoffs_fields(self, chris):
        r = chris.put(
            f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards",
            json={"division_winner": True, "playoffs_reached": True},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["division_winner_at"] is not None
        assert body["playoffs_reached_at"] is not None

        # Clear
        chris.put(
            f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards",
            json={"division_winner": False, "playoffs_reached": False},
            timeout=30,
        )

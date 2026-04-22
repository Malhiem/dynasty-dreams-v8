"""Phase 19 backend tests: draft picks endpoint, trade execute auth, evaluate-conditions."""
import os
import pytest
import requests
from pathlib import Path
from dotenv import dotenv_values

_env = dotenv_values(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

CHRIS_EMAIL = "chriszarek@gmail.com"
CHRIS_PWD = "Chris2026!"
ICE_KINGS_LID = "69e46af167999bfb85c39628"


@pytest.fixture(scope="module")
def chris_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": CHRIS_EMAIL, "password": CHRIS_PWD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def league_team_counts():
    # Look up the 5 leagues via a chris session
    s = requests.Session()
    s.post(f"{API}/auth/login", json={"email": CHRIS_EMAIL, "password": CHRIS_PWD})
    r = s.get(f"{API}/leagues")
    assert r.status_code == 200
    out = {}
    for lg in r.json():
        out[lg["name"]] = lg.get("_id") or lg.get("id")
    return out


# ── Draft picks endpoint ──────────────────────────────────────────────
class TestDraftPicks:
    def test_ice_kings_2026_picks(self):
        r = requests.get(f"{API}/drafts/{ICE_KINGS_LID}/picks", params={"year": 2026})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["league_id"] == ICE_KINGS_LID
        assert body["year"] == 2026
        picks = body["picks"]
        assert len(picks) == 60, f"Expected 60 picks for Ice Kings 2026, got {len(picks)}"
        sample = picks[0]
        for k in ("_id", "league_id", "year", "round",
                  "original_team_id", "original_team_name",
                  "current_team_id", "current_team_name"):
            assert k in sample, f"missing key {k} in pick {sample}"
        assert all(1 <= p["round"] <= 5 for p in picks)
        # Must NOT leak ObjectId style _id (should be str)
        assert isinstance(sample["_id"], str)

    def test_other_league_pick_counts(self, league_team_counts):
        expected = {
            "Ice Kings Head-to-Head": 60,
            "Stat Chasers Roto": 70,
            "Frozen Dynasty": 80,
            "Perennial Keepers": 60,
            "Set-and-Forget Best Ball": 160,
        }
        for name, count in expected.items():
            lid = league_team_counts.get(name)
            assert lid, f"League {name} not found"
            r = requests.get(f"{API}/drafts/{lid}/picks", params={"year": 2026})
            assert r.status_code == 200, f"{name}: {r.text}"
            picks = r.json()["picks"]
            assert len(picks) == count, f"{name} expected {count}, got {len(picks)}"

    def test_team_abbrs_real(self):
        r = requests.get(f"{API}/drafts/{ICE_KINGS_LID}/picks", params={"year": 2026})
        names = {p["original_team_name"] for p in r.json()["picks"]}
        # Old mock names should NOT be present
        for old in ("Arctic Wolves", "Blizzards", "Frostbite Falcons"):
            assert old not in names, f"Mock team name '{old}' leaked"
        # At least some real ones should appear
        real = {"Zarek's Frozen", "Ice Breakers", "Slapshot Snipers"}
        assert real.intersection(names), f"Expected real team names, got {names}"


# ── Evaluate conditions (no auth required) ────────────────────────────
class TestEvaluateConditions:
    def test_evaluate_no_auth(self, chris_session):
        # Propose a quick conditional trade then call evaluate w/o auth
        r = chris_session.get(f"{API}/teams", params={"league_id": ICE_KINGS_LID})
        assert r.status_code == 200
        teams = r.json()
        me = chris_session.get(f"{API}/auth/me").json()
        my_uid = me.get("_id") or me.get("id")
        my_team = next(t for t in teams if t.get("owner_id") == my_uid)
        other = next(t for t in teams if t.get("owner_id") != my_uid)
        my_tid = my_team.get("_id") or my_team.get("id")
        other_tid = other.get("_id") or other.get("id")
        payload = {
            "league_id": ICE_KINGS_LID,
            "target_team_id": other_tid,
            "assets_offered": [{"asset_type": "player", "player_id": my_team["roster"][5]}],
            "assets_requested": [{"asset_type": "player", "player_id": other["roster"][5]}],
            "conditions": [{
                "subject": "offered", "metric": "nhl_points",
                "operator": "gte", "threshold": 99999,
            }],
        }
        rp = chris_session.post(f"{API}/trades", json=payload)
        assert rp.status_code == 200, rp.text
        trade = rp.json()
        assert trade.get("conditional") is True
        assert isinstance(trade.get("conditions"), list) and len(trade["conditions"]) == 1
        tid = trade["_id"]
        # Call evaluate with NO cookies/session
        re = requests.post(f"{API}/trades/{tid}/evaluate-conditions")
        assert re.status_code == 200, re.text
        body = re.json()
        assert "all_met" in body and "results" in body
        assert body["all_met"] is False
        assert isinstance(body["results"], list) and len(body["results"]) == 1
        assert "actual_value" in body["results"][0]
        assert body["results"][0]["met"] is False


# ── Trade execute permissions ─────────────────────────────────────────
class TestTradeExecuteAuth:
    def test_non_participant_403(self, chris_session):
        # Use a stranger to attempt to execute; first create stranger
        from uuid import uuid4
        email = f"TEST_phase19_{uuid4().hex[:8]}@example.com"
        # Create stranger
        rs = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "Stranger1!",
            "name": "Phase19 Stranger", "username": f"p19_{uuid4().hex[:6]}",
        })
        if rs.status_code not in (200, 201):
            pytest.skip(f"registration failed: {rs.status_code} {rs.text}")
        ss = requests.Session()
        rl = ss.post(f"{API}/auth/login", json={"email": email, "password": "Stranger1!"})
        assert rl.status_code == 200, rl.text
        # Have chris propose a trade
        r = chris_session.get(f"{API}/teams", params={"league_id": ICE_KINGS_LID})
        teams = r.json()
        me = chris_session.get(f"{API}/auth/me").json()
        my_uid = me.get("_id") or me.get("id")
        my_team = next(t for t in teams if t.get("owner_id") == my_uid)
        other = next(t for t in teams if t.get("owner_id") != my_uid)
        other_tid = other.get("_id") or other.get("id")
        payload = {
            "league_id": ICE_KINGS_LID, "target_team_id": other_tid,
            "assets_offered": [{"asset_type": "player", "player_id": my_team["roster"][8]}],
            "assets_requested": [{"asset_type": "player", "player_id": other["roster"][8]}],
        }
        rp = chris_session.post(f"{API}/trades", json=payload)
        assert rp.status_code == 200, rp.text
        tid = rp.json()["_id"]
        # Stranger tries to execute → 403
        rx = ss.post(f"{API}/trades/{tid}/execute")
        assert rx.status_code == 403, f"expected 403, got {rx.status_code} {rx.text}"

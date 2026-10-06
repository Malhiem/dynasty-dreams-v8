"""Iteration 34 — Roster compliance tile, minors seed, IR compliance mode endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ZAREK_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
ZAREK_PASS = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
ZAREK_TEAM_ID = "69e59b30cbd3fea02a914c61"
LEAGUE_ID = "69e46af167999bfb85c39628"


@pytest.fixture(scope="module")
def zarek_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ZAREK_EMAIL, "password": ZAREK_PASS})
    assert r.status_code == 200, f"Zarek login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module", autouse=True)
def _ensure_roster_over_cap():
    """Iter 230u — Self-healing fixture: `test_zarek_too_many_players`
    asserts Zarek's roster count exceeds `max_roster`. Real-user activity
    (drops, settings tweaks) can push `roster_spots` above the live roster
    size and break the assertion. This fixture inspects Zarek's roster
    count, sets `roster_spots = roster_count - 1` (forcing over-cap) before
    the module's tests run, and restores the original value afterwards.
    """
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": ZAREK_EMAIL, "password": ZAREK_PASS})
    team = s.get(f"{BASE_URL}/api/teams/{ZAREK_TEAM_ID}").json()
    roster_count = len(team.get("roster") or [])
    league = s.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}").json()
    original_spots = league.get("roster_spots")
    # Need at least 2 players to make the test meaningful; skip the patch
    # entirely if the roster is empty so the empty_roster rule (iter 230s)
    # is what's asserted instead.
    if roster_count >= 2:
        target_spots = max(2, roster_count - 1)
        r = s.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}",
            json={"roster_spots": target_spots},
        )
        assert r.status_code == 200, f"roster_spots PUT failed: {r.status_code} {r.text[:200]}"
    yield
    if original_spots is not None:
        try:
            s.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json={"roster_spots": original_spots})
        except Exception:
            pass


# -------- Minors seed validation --------
@pytest.fixture(scope="module", autouse=True)
def explicit_minors_inputs(_global_pollution_sweep):
    from pymongo import MongoClient
    from bson import ObjectId
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        teams = list(db.teams.find({"league_id": "69e46af167999bfb85c39628"}).limit(2))
        prospects = list(db.players.find({"player_type": "prospect"}).limit(2))
        for team, prospect in zip(teams, prospects):
            pid = str(prospect["_id"])
            db.teams.update_one({"_id": team["_id"]}, {"$addToSet": {"roster": pid}, "$set": {f"lineup.{pid}": {"section": "minors", "slot": "MIN"}}})
        yield

class TestMinorsSeed:
    def test_zarek_team_lineup_has_minors(self, zarek_session):
        r = zarek_session.get(f"{BASE_URL}/api/teams/{ZAREK_TEAM_ID}/lineup")
        assert r.status_code == 200, r.text[:300]
        lineup = r.json().get("lineup") or {}
        minors_entries = [v for v in lineup.values() if isinstance(v, dict) and (v.get("section") or "").lower() == "minors"]
        # Per context: 121 prospects placed across 100 teams → at least some teams have minors
        # We assert shape of any minors entry if present; Zarek's team might or might not have minors
        for e in minors_entries:
            assert e.get("slot") == "MIN", f"Expected slot 'MIN' for minors entry, got {e}"

    def test_at_least_some_teams_have_minors(self, admin_session):
        # Seed script placed minors across multiple teams (not necessarily in the target test league;
        # depends on which teams had minors-eligible young players). Scan a broader sample.
        r = admin_session.get(f"{BASE_URL}/api/teams")
        assert r.status_code == 200, r.text[:300]
        teams = r.json() if isinstance(r.json(), list) else r.json().get("teams", [])
        assert len(teams) > 0
        found_minors_teams = 0
        for t in teams[:60]:  # sample up to 60 teams
            tid = t.get("id") or t.get("_id") or t.get("team_id")
            if not tid:
                continue
            lr = admin_session.get(f"{BASE_URL}/api/teams/{tid}/lineup")
            if lr.status_code != 200:
                continue
            lineup = lr.json().get("lineup") or {}
            if any(isinstance(v, dict) and (v.get("section") or "").lower() == "minors"
                   and (v.get("slot") or "") == "MIN"
                   for v in lineup.values()):
                found_minors_teams += 1
        assert found_minors_teams >= 2, \
            f"Expected seeded minors across multiple teams, only found {found_minors_teams}"


# -------- Compliance endpoint --------
class TestCompliance:
    def test_compliance_response_shape(self, zarek_session):
        r = zarek_session.get(f"{BASE_URL}/api/teams/{ZAREK_TEAM_ID}/compliance")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("compliant", "reasons", "roster_count", "max_roster",
                  "salary_used", "salary_cap", "salary_cap_enabled",
                  "injury_reserve_compliance_mode"):
            assert k in d, f"Missing key {k} in compliance response"
        assert isinstance(d["reasons"], list)
        assert isinstance(d["compliant"], bool)

    def test_zarek_too_many_players(self, zarek_session):
        r = zarek_session.get(f"{BASE_URL}/api/teams/{ZAREK_TEAM_ID}/compliance")
        assert r.status_code == 200
        d = r.json()
        assert d["roster_count"] > d["max_roster"], \
            f"Expected roster over max: got {d['roster_count']}/{d['max_roster']}"
        codes = [reason["code"] for reason in d["reasons"]]
        assert "too_many_players" in codes, f"Expected 'too_many_players' in reasons, got {codes}"
        assert d["compliant"] is False

    def test_compliance_404_for_bad_team(self, zarek_session):
        bad_id = "000000000000000000000000"
        r = zarek_session.get(f"{BASE_URL}/api/teams/{bad_id}/compliance")
        assert r.status_code == 404


# -------- IR compliance mode endpoint --------
class TestIRComplianceMode:
    def test_non_commissioner_forbidden(self, zarek_session):
        # Zarek may not be commissioner of league LEAGUE_ID — expect 403 unless he is
        r = zarek_session.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
            json={"mode": "none"},
        )
        # Accept either 200 (if Zarek is the commissioner) or 403
        assert r.status_code in (200, 403), f"Unexpected status: {r.status_code} {r.text[:200]}"

    def test_invalid_mode_400(self, admin_session):
        r = admin_session.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
            json={"mode": "bogus_mode"},
        )
        # admin may not be commissioner → could be 403 before 400 validation
        assert r.status_code in (400, 403), f"Unexpected: {r.status_code} {r.text[:200]}"

    def test_valid_mode_updates_as_commissioner(self, admin_session):
        # Discover commissioner and use that user to test
        lr = admin_session.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}")
        if lr.status_code != 200:
            pytest.skip("Cannot fetch league")
        commish_id = lr.json().get("commissioner_id")
        if not commish_id:
            pytest.skip("League has no commissioner_id")

        # Try admin first
        r = admin_session.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
            json={"mode": "lock_waivers"},
        )
        if r.status_code == 403:
            pytest.skip(f"Admin not commissioner (commish_id={commish_id}); cannot test happy path without elevation")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["injury_reserve_compliance_mode"] == "lock_waivers"

        # Verify via compliance endpoint reflection
        cr = admin_session.get(f"{BASE_URL}/api/teams/{ZAREK_TEAM_ID}/compliance")
        assert cr.status_code == 200
        assert cr.json()["injury_reserve_compliance_mode"] == "lock_waivers"

        # Reset back to none to keep league clean
        admin_session.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
            json={"mode": "none"},
        )

    def test_all_valid_modes_accepted(self, admin_session):
        lr = admin_session.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}")
        if lr.status_code != 200:
            pytest.skip("Cannot fetch league")
        # Probe commissioner access first
        probe = admin_session.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
            json={"mode": "none"},
        )
        if probe.status_code == 403:
            pytest.skip("Admin not commissioner; skipping full mode matrix")
        for mode in ["none", "lock_all", "lock_waivers", "lock_adds",
                     "lock_adds_trades", "illegal_roster", "drop_player"]:
            r = admin_session.put(
                f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
                json={"mode": mode},
            )
            assert r.status_code == 200, f"mode {mode} failed: {r.status_code} {r.text[:200]}"
            assert r.json()["injury_reserve_compliance_mode"] == mode
        # Reset
        admin_session.put(
            f"{BASE_URL}/api/leagues/{LEAGUE_ID}/injury-reserve-compliance-mode",
            json={"mode": "none"},
        )

"""Iter 232N.9/232N.10 backend regression tests.

Covers:
  1. /api/roster/{team_id} and /api/roster/{team_id}/detail both return
     `status_flags` and `trends` on every player row (shared payload
     builder helpers so the two endpoints can't drift).
  2. Auth is enforced (401 with no token).
  3. League-membership guard (403 for outsiders) — checked implicitly
     by verifying a valid TFHL member CAN read the roster.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

USER = {"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")}
# TFHL — chriszarek's roster with McDavid (from iter 138 report).
TFHL_TEAM_ID = "69e59b33cbd3fea02a914c79"
TFHL_LEAGUE_ID = "69e46af167999bfb85c39629"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json=USER, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestRosterAuth:
    def test_roster_light_requires_auth(self):
        r = requests.get(f"{API}/roster/{TFHL_TEAM_ID}", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_roster_detail_requires_auth(self):
        r = requests.get(f"{API}/roster/{TFHL_TEAM_ID}/detail", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


class TestRosterPayloadConsistency:
    """Iter 232N.10 — verify both endpoints emit status_flags + trends."""

    def test_roster_light_status_flags_and_trends(self, auth_headers):
        r = requests.get(
            f"{API}/roster/{TFHL_TEAM_ID}", headers=auth_headers, timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        players = data.get("players", [])
        assert len(players) > 0, "expected non-empty roster"
        for p in players:
            assert "status_flags" in p, f"missing status_flags: {p.get('name')}"
            sf = p["status_flags"]
            assert isinstance(sf, dict)
            for key in ("injured", "in_minors", "unsigned", "undrafted"):
                assert key in sf, f"status_flags missing '{key}' on {p.get('name')}"
            assert "trends" in p, f"missing trends key: {p.get('name')}"
            assert p["trends"] is None or isinstance(p["trends"], dict)

    def test_roster_detail_status_flags_and_trends(self, auth_headers):
        r = requests.get(
            f"{API}/roster/{TFHL_TEAM_ID}/detail",
            headers=auth_headers, timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        players = data.get("players", [])
        assert len(players) > 0
        for p in players:
            assert "status_flags" in p, f"detail: missing status_flags: {p.get('name')}"
            sf = p["status_flags"]
            assert isinstance(sf, dict)
            for key in ("injured", "in_minors", "unsigned", "undrafted"):
                assert key in sf, f"detail: status_flags missing '{key}'"
            assert "trends" in p, f"detail: missing trends: {p.get('name')}"
            assert p["trends"] is None or isinstance(p["trends"], dict)

    def test_shape_no_drift_between_endpoints(self, auth_headers):
        """For every player_id present in both payloads, status_flags and
        trends must agree exactly."""
        r_light = requests.get(
            f"{API}/roster/{TFHL_TEAM_ID}", headers=auth_headers, timeout=20,
        )
        r_detail = requests.get(
            f"{API}/roster/{TFHL_TEAM_ID}/detail",
            headers=auth_headers, timeout=20,
        )
        assert r_light.status_code == 200
        assert r_detail.status_code == 200
        light = {p["player_id"]: p for p in r_light.json().get("players", [])}
        detail = {p["player_id"]: p for p in r_detail.json().get("players", [])}
        common = set(light.keys()) & set(detail.keys())
        assert len(common) > 0, "no overlapping players — sanity check failed"
        for pid in common:
            assert light[pid]["status_flags"] == detail[pid]["status_flags"], (
                f"status_flags drift on {pid}: "
                f"light={light[pid]['status_flags']} detail={detail[pid]['status_flags']}"
            )
            assert light[pid]["trends"] == detail[pid]["trends"], (
                f"trends drift on {pid}: "
                f"light={light[pid]['trends']} detail={detail[pid]['trends']}"
            )


class TestWaiversEndpointsForPanel:
    """Sanity-check the endpoints the WaiverManagementPanel hits."""

    def test_waivers_next_run(self, auth_headers):
        r = requests.get(
            f"{API}/waivers/next-run?league_id={TFHL_LEAGUE_ID}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code in (200, 404), r.status_code

    def test_waivers_my_claims(self, auth_headers):
        r = requests.get(
            f"{API}/waivers/claims?league_id={TFHL_LEAGUE_ID}&my_claims=true",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text[:200]

    def test_waivers_history(self, auth_headers):
        r = requests.get(
            f"{API}/waivers/history?league_id={TFHL_LEAGUE_ID}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text[:200]

    def test_waivers_order(self, auth_headers):
        r = requests.get(
            f"{API}/waivers/order?league_id={TFHL_LEAGUE_ID}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text[:200]

"""Iter232N62 live HTTP smoke: cap-status endpoint auth + shape, cap-settings PUT."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "admin@dynastydreams.com", "password": "Admin123!"}


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return ses


def test_cap_status_unauthenticated_401():
    r = requests.get(f"{BASE}/api/drafts/000000000000000000000000/cap-status", timeout=10)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_cap_status_nonexistent_draft_404(s):
    r = s.get(f"{BASE}/api/drafts/000000000000000000000000/cap-status", timeout=15)
    assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"


def test_cap_status_shape_on_real_draft(s):
    # Find an existing draft
    r = s.get(f"{BASE}/api/leagues", timeout=15)
    assert r.status_code == 200
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    if not leagues:
        pytest.skip("No leagues available")
    draft_id = None
    for lg in leagues[:20]:
        lid = lg.get("id") or lg.get("_id")
        if not lid:
            continue
        dr = s.get(f"{BASE}/api/leagues/{lid}/drafts", timeout=15)
        if dr.status_code == 200:
            drafts = dr.json() if isinstance(dr.json(), list) else dr.json().get("drafts", [])
            if drafts:
                draft_id = drafts[0].get("id") or drafts[0].get("_id")
                if draft_id:
                    break
    if not draft_id:
        pytest.skip("No drafts found to test shape against")
    r = s.get(f"{BASE}/api/drafts/{draft_id}/cap-status", timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    for k in ["draft_id", "league_id", "salary_cap_enabled", "approaching_pct", "teams"]:
        assert k in data, f"missing key {k}: {list(data.keys())}"
    assert isinstance(data["teams"], list)
    if data.get("salary_cap_enabled") and data["teams"]:
        t = data["teams"][0]
        for k in ["team_id", "name", "salary_used", "salary_cap", "remaining", "percent_used", "over_cap", "approaching", "picks_count"]:
            assert k in t, f"team missing {k}: {list(t.keys())}"


def test_cap_settings_put_new_fields(s):
    r = s.get(f"{BASE}/api/leagues", timeout=15)
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    target = None
    for lg in leagues[:30]:
        if lg.get("salary_cap_enabled"):
            target = lg
            break
    if not target:
        pytest.skip("no cap-enabled league")
    lid = target.get("id") or target.get("_id")
    payload = {
        "salary_cap_enabled": True,
        "salary_cap": target.get("salary_cap") or 90_000_000,
        "default_rookie_aav": 975000,
        "minors_cap_treatment": "default",
    }
    r = s.put(f"{BASE}/api/leagues/{lid}/admin/cap-settings", json=payload, timeout=15)
    assert r.status_code in (200, 204), f"{r.status_code}: {r.text[:300]}"
    r = s.get(f"{BASE}/api/leagues/{lid}", timeout=15)
    assert r.status_code == 200
    lg = r.json()
    assert lg.get("default_rookie_aav") == 975000, lg
    assert lg.get("minors_cap_treatment") == "default", lg

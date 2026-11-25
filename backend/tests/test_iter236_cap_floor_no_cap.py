"""No cap, no floor: the cap-floor watchlist must report no floor for a league
whose salary cap is disabled (even if stale floor settings remain), must be
league-members only, and must expose the Year+1 / Year+2 floors for clients."""
import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users, private_team  # noqa: F401


def _set(db, league_id, **fields):
    db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": fields})


def _watchlist(headers, league_id):
    return requests.get(f"{API_URL}/api/leagues/{league_id}/cap-floor-watchlist", headers=headers, timeout=10)


def test_no_floor_when_cap_disabled_even_with_stale_floor(private_team, security_db):
    _set(security_db, private_team["league_id"], salary_cap_enabled=False, salary_cap=None,
         cap_floor_enabled=True, cap_floor=60_000_000)
    r = _watchlist(private_team["owner"]["headers"], private_team["league_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["floor_enabled"] is False
    assert body["floor"] == 0
    assert body["floor_year_plus_1"] == 0 and body["floor_year_plus_2"] == 0
    assert all(t["status"] == "above" for t in body["teams"])


def test_floor_reported_when_cap_and_floor_enabled(private_team, security_db):
    _set(security_db, private_team["league_id"], salary_cap_enabled=True, salary_cap=80_000_000,
         cap_floor_enabled=True, cap_floor=60_000_000, cap_floor_year_plus_1=62_000_000)
    body = _watchlist(private_team["owner"]["headers"], private_team["league_id"]).json()
    assert body["floor_enabled"] is True
    assert body["floor"] == 60_000_000
    assert body["floor_year_plus_1"] == 62_000_000
    # Year+2 falls back to Year+1 when not configured (same rule as the web).
    assert body["floor_year_plus_2"] == 62_000_000
    mine = [t for t in body["teams"] if t["team_id"] == private_team["id"]]
    assert mine and mine[0]["status"] == "below"  # empty payroll < floor


def test_watchlist_is_members_only(private_team, security_users, security_db):
    _set(security_db, private_team["league_id"], salary_cap_enabled=True, salary_cap=80_000_000,
         cap_floor_enabled=True, cap_floor=60_000_000)
    outsider = security_users()
    assert _watchlist(outsider["headers"], private_team["league_id"]).status_code == 403

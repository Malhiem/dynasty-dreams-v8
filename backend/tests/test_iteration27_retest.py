"""Iteration 27 retest: verify FIX 1 (backfill on /trade-block-summary).
Verifies that every item returned by GET /api/leagues/{id}/trade-block-summary
has a non-null team_name and salary_retention_pref (no undefined retention badges).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")

OWNER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
OWNER_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")


@pytest.fixture(scope="module")
def owner_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ice_kings_league_id(owner_session):
    r = owner_session.get(f"{BASE_URL}/api/leagues")
    assert r.status_code == 200
    leagues = r.json()
    for L in leagues:
        if "ice king" in (L.get("name") or "").lower():
            return L["id"]
    pytest.skip("Ice Kings league not found")


@pytest.fixture(scope="module", autouse=True)
def legacy_trade_block_inputs(_global_pollution_sweep):
    from pymongo import MongoClient
    from bson import ObjectId
    from datetime import datetime, timezone
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        lid = "69e46af167999bfb85c39628"
        teams = list(db.teams.find({"league_id": lid}).limit(2))
        entries = []
        for team in teams:
            player = db.players.find_one({"_id": ObjectId(team["roster"][0])})
            entries.append({"league_id": lid, "owner_id": team["owner_id"], "item_type": "player",
                "player_id": str(player["_id"]), "name": player["name"], "position": player["position"],
                "created_at": datetime.now(timezone.utc).isoformat(), "_legacy_block_fixture": True})
        db.trade_block.insert_many(entries)
        yield
        db.trade_block.delete_many({"_legacy_block_fixture": True})


class TestFix1Backfill:
    """FIX 1: All items in trade-block-summary must have non-null team_name and salary_retention_pref."""

    def test_summary_all_items_have_team_name(self, owner_session, ice_kings_league_id):
        r = owner_session.get(
            f"{BASE_URL}/api/leagues/{ice_kings_league_id}/trade-block-summary?limit=50"
        )
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", [])
        assert len(items) > 0, "No items in summary - cannot validate backfill"
        missing = [it for it in items if not it.get("team_name")]
        assert not missing, (
            f"{len(missing)}/{len(items)} items missing team_name "
            f"(item ids: {[m.get('_id') for m in missing[:5]]})"
        )

    def test_summary_all_items_have_retention_pref(self, owner_session, ice_kings_league_id):
        r = owner_session.get(
            f"{BASE_URL}/api/leagues/{ice_kings_league_id}/trade-block-summary?limit=50"
        )
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) > 0
        valid = {"willing_to_retain", "no_retention", "no_preference"}
        missing = [it for it in items if not it.get("salary_retention_pref")]
        invalid = [it for it in items if it.get("salary_retention_pref") not in valid]
        assert not missing, f"{len(missing)} items missing salary_retention_pref"
        assert not invalid, f"{len(invalid)} items with invalid retention pref values"

    def test_summary_all_items_have_team_id(self, owner_session, ice_kings_league_id):
        r = owner_session.get(
            f"{BASE_URL}/api/leagues/{ice_kings_league_id}/trade-block-summary?limit=50"
        )
        items = r.json().get("items", [])
        missing = [it for it in items if not it.get("team_id")]
        assert not missing, f"{len(missing)} items missing team_id (backfill should populate)"

    def test_summary_caps_at_50(self, owner_session, ice_kings_league_id):
        r = owner_session.get(
            f"{BASE_URL}/api/leagues/{ice_kings_league_id}/trade-block-summary?limit=200"
        )
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) <= 50, f"Limit not capped at 50, got {len(items)}"

    def test_summary_ranked_by_fantasy_points(self, owner_session, ice_kings_league_id):
        r = owner_session.get(
            f"{BASE_URL}/api/leagues/{ice_kings_league_id}/trade-block-summary?limit=50"
        )
        items = r.json().get("items", [])
        if len(items) < 2:
            pytest.skip("Need >=2 items to verify ranking")
        fps = [float(it.get("fantasy_points") or 0) for it in items]
        assert fps == sorted(fps, reverse=True), \
            f"Items not sorted desc by fantasy_points: {fps[:5]}"

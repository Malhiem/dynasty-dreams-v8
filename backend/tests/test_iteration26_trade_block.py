"""
Iteration 26 - Trade Block system tests
Covers:
  - POST /api/trade-block (player + pick) with enrichment
  - Duplicate prevention (400)
  - DELETE /api/trade-block/{id} (owner-only / 403)
  - GET /api/trade-block w/ league_id, team_id, owner_id filters
  - PUT /api/teams/{id}/trade-block-preference w/ cascade + validation
  - GET /api/leagues/{id}/trade-block-summary (sorted, capped)
  - POST /api/leagues/{id}/trade-block/refresh-stats (commissioner only)
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

OWNER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
OWNER_PASS = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def owner_session():
    return _login(OWNER_EMAIL, OWNER_PASS)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def context(owner_session):
    """Resolve Ice Kings league, Zarek's Frozen team, and a roster player."""
    me = owner_session.get(f"{API}/auth/me", timeout=10).json()
    user_id = me.get("id") or me.get("_id")
    leagues = owner_session.get(f"{API}/leagues", timeout=15).json()
    league = next((l for l in leagues if "Ice Kings" in l.get("name", "")), None)
    assert league, f"Ice Kings league not found. Available: {[l.get('name') for l in leagues]}"
    league_id = league.get("id") or league.get("_id")

    teams = owner_session.get(f"{API}/teams?league_id={league_id}", timeout=15).json()
    assert isinstance(teams, list), f"teams payload not a list: {teams}"
    own_team = next((t for t in teams if t.get("owner_id") == user_id), None)
    assert own_team, f"Zarek's Frozen not found for user {user_id}"
    other_team = next((t for t in teams if t.get("owner_id") != user_id), None)
    assert other_team, "No other team found"

    team_id = own_team.get("id") or own_team.get("_id")
    roster = own_team.get("roster", [])
    assert roster, "Owner team has no roster"
    first = roster[0]
    player_id = first if isinstance(first, str) else (
        first.get("player_id") or first.get("id") or first.get("_id")
    )

    return {
        "user_id": user_id,
        "league_id": league_id,
        "team_id": team_id,
        "other_team_id": other_team.get("id") or other_team.get("_id"),
        "other_owner_id": other_team.get("owner_id"),
        "player_id": player_id,
        "is_commissioner": league.get("commissioner_id") == user_id,
    }


# ─────────── Helper: cleanup ───────────
def _cleanup_owner_block(session, league_id):
    items = session.get(f"{API}/trade-block?league_id={league_id}", timeout=15).json()
    me = session.get(f"{API}/auth/me", timeout=10).json()
    me_id = me.get("id") or me.get("_id")
    for it in items:
        if it.get("owner_id") == me_id:
            session.delete(f"{API}/trade-block/{it['_id']}", timeout=10)


class TestTradeBlockPlayer:
    def test_post_player_returns_enriched_fields(self, owner_session, context):
        _cleanup_owner_block(owner_session, context["league_id"])
        payload = {
            "item_type": "player",
            "player_id": context["player_id"],
            "league_id": context["league_id"],
            "team_id": context["team_id"],
            "looking_for": ["DEF help"],
        }
        r = owner_session.post(f"{API}/trade-block", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "_id" in data
        assert data["item_type"] == "player"
        assert data["player_id"] == context["player_id"]
        assert data["league_id"] == context["league_id"]
        assert data["team_id"] == context["team_id"]
        # enriched fields present
        for k in ["name", "position", "nhl_team", "goals", "assists", "points",
                  "plus_minus", "games_played", "fantasy_points", "fantasy_ppg",
                  "team_name", "salary_retention_pref"]:
            assert k in data, f"Missing field {k} in response: {list(data.keys())}"
        assert data["salary_retention_pref"] in (
            "willing_to_retain", "no_preference", "seeking_retention"
        )

    def test_duplicate_player_returns_400(self, owner_session, context):
        payload = {
            "item_type": "player",
            "player_id": context["player_id"],
            "league_id": context["league_id"],
            "team_id": context["team_id"],
        }
        r = owner_session.post(f"{API}/trade-block", json=payload, timeout=15)
        assert r.status_code == 400
        assert "Already" in r.text or "already" in r.text

    def test_get_filtered_by_team_id(self, owner_session, context):
        r = owner_session.get(f"{API}/trade-block?team_id={context['team_id']}", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert all(it.get("team_id") == context["team_id"] for it in items)
        assert any(it.get("player_id") == context["player_id"] for it in items)

    def test_get_filtered_by_owner_id(self, owner_session, context):
        r = owner_session.get(f"{API}/trade-block?owner_id={context['user_id']}", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert all(it.get("owner_id") == context["user_id"] for it in items)

    def test_get_filtered_by_league_id(self, owner_session, context):
        r = owner_session.get(f"{API}/trade-block?league_id={context['league_id']}", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert all(it.get("league_id") == context["league_id"] for it in items)

    def test_delete_outsider_403(self, admin_session, owner_session, context):
        # find the player item created in test_post_player_returns_enriched_fields
        items = owner_session.get(
            f"{API}/trade-block?team_id={context['team_id']}", timeout=15
        ).json()
        target = next(
            (it for it in items if it.get("player_id") == context["player_id"]), None
        )
        assert target, "could not find created player item"
        # admin is NOT the owner of Zarek's Frozen
        r = admin_session.delete(f"{API}/trade-block/{target['_id']}", timeout=10)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_delete_owner_succeeds(self, owner_session, context):
        items = owner_session.get(
            f"{API}/trade-block?team_id={context['team_id']}", timeout=15
        ).json()
        target = next(
            (it for it in items if it.get("player_id") == context["player_id"]), None
        )
        assert target
        r = owner_session.delete(f"{API}/trade-block/{target['_id']}", timeout=10)
        assert r.status_code == 200
        # verify gone
        items_after = owner_session.get(
            f"{API}/trade-block?team_id={context['team_id']}", timeout=15
        ).json()
        assert not any(
            it.get("player_id") == context["player_id"] for it in items_after
        )


class TestTradeBlockPick:
    def test_post_pick_with_pick_id(self, owner_session, context):
        # Try to find an owned pick - try multiple endpoints + raw mongo-style filters.
        # The team's draft_picks aren't part of the team doc; they live in draft_picks
        # collection with current_team_id field.
        pick_id = None
        for path in [
            f"/leagues/{context['league_id']}/draft-picks?team_id={context['team_id']}",
            f"/draft-picks?team_id={context['team_id']}",
            f"/leagues/{context['league_id']}/draft-picks?current_team_id={context['team_id']}",
        ]:
            r = owner_session.get(f"{API}{path}", timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("picks") or data.get("items") or []
                for p in items:
                    cur = p.get("current_team_id") or p.get("team_id")
                    if cur == context["team_id"]:
                        pick_id = p.get("_id") or p.get("id")
                        if pick_id:
                            break
                if pick_id:
                    break
        if not pick_id:
            pytest.skip("No owned draft pick discoverable via API endpoints")

        payload = {
            "item_type": "pick",
            "pick_id": pick_id,
            "league_id": context["league_id"],
            "team_id": context["team_id"],
        }
        r = owner_session.post(f"{API}/trade-block", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["item_type"] == "pick"
        assert data["pick_id"] == pick_id
        assert "name" in data
        assert "R" in data["name"]
        owner_session.delete(f"{API}/trade-block/{data['_id']}", timeout=10)


class TestRetentionPreference:
    def test_invalid_preference_400(self, owner_session, context):
        r = owner_session.put(
            f"{API}/teams/{context['team_id']}/trade-block-preference",
            json={"preference": "invalid_value"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_non_owner_403(self, admin_session, context):
        r = admin_session.put(
            f"{API}/teams/{context['team_id']}/trade-block-preference",
            json={"preference": "willing_to_retain"},
            timeout=10,
        )
        assert r.status_code == 403

    def test_owner_set_and_cascade(self, owner_session, context):
        # Create an item first to verify cascade
        _cleanup_owner_block(owner_session, context["league_id"])
        post = owner_session.post(
            f"{API}/trade-block",
            json={
                "item_type": "player",
                "player_id": context["player_id"],
                "league_id": context["league_id"],
                "team_id": context["team_id"],
            },
            timeout=15,
        )
        assert post.status_code == 200
        item_id = post.json()["_id"]

        try:
            for pref in ("willing_to_retain", "seeking_retention", "no_preference"):
                r = owner_session.put(
                    f"{API}/teams/{context['team_id']}/trade-block-preference",
                    json={"preference": pref},
                    timeout=10,
                )
                assert r.status_code == 200, r.text
                assert r.json()["preference"] == pref

                # Verify cascade
                items = owner_session.get(
                    f"{API}/trade-block?team_id={context['team_id']}", timeout=15
                ).json()
                target = next((it for it in items if it["_id"] == item_id), None)
                assert target, "item missing after pref update"
                assert target.get("salary_retention_pref") == pref, (
                    f"cascade failed: expected {pref}, got {target.get('salary_retention_pref')}"
                )
        finally:
            owner_session.delete(f"{API}/trade-block/{item_id}", timeout=10)


class TestSummaryAndRefresh:
    def test_summary_default_limit(self, owner_session, context):
        # ensure at least one item exists
        _cleanup_owner_block(owner_session, context["league_id"])
        owner_session.post(
            f"{API}/trade-block",
            json={
                "item_type": "player",
                "player_id": context["player_id"],
                "league_id": context["league_id"],
                "team_id": context["team_id"],
            },
            timeout=15,
        )
        try:
            r = owner_session.get(
                f"{API}/leagues/{context['league_id']}/trade-block-summary",
                timeout=15,
            )
            assert r.status_code == 200
            body = r.json()
            assert "items" in body and "count" in body
            assert body["league_id"] == context["league_id"]
            assert len(body["items"]) <= 10  # default
            # sort order: fantasy_points desc, then recent_form_ppw desc
            fpts = [float(i.get("fantasy_points") or 0) for i in body["items"]]
            assert fpts == sorted(fpts, reverse=True), f"items not sorted by fantasy_points desc: {fpts}"
            # Each NEW item should have player stats + team_name + retention pref.
            # Note: legacy items added before iteration 26 may lack team_name /
            # salary_retention_pref because they were created without team_id.
            # We only enforce the contract on items we just created (team_id matches).
            for it in body["items"]:
                if it.get("item_type") == "player" and it.get("team_id") == context["team_id"]:
                    for k in ["name", "position", "nhl_team", "fantasy_points",
                              "team_name", "salary_retention_pref"]:
                        assert k in it, f"summary item missing {k}: {list(it.keys())}"
        finally:
            _cleanup_owner_block(owner_session, context["league_id"])

    def test_summary_caps_limit_at_50(self, owner_session, context):
        r = owner_session.get(
            f"{API}/leagues/{context['league_id']}/trade-block-summary?limit=999",
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) <= 50

    def test_refresh_stats_requires_auth(self, context):
        # Unauthenticated request should be rejected
        r = requests.post(
            f"{API}/leagues/{context['league_id']}/trade-block/refresh-stats",
            timeout=20,
        )
        assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}"

    def test_refresh_stats_commissioner_succeeds(self, owner_session, admin_session, context):
        # Both admin (commissioner) and chriszarek (co_commissioner) should be allowed.
        r_admin = admin_session.post(
            f"{API}/leagues/{context['league_id']}/trade-block/refresh-stats",
            timeout=30,
        )
        assert r_admin.status_code == 200, r_admin.text
        body = r_admin.json()
        assert "items_refreshed" in body
        assert body["league_id"] == context["league_id"]

        r_owner = owner_session.post(
            f"{API}/leagues/{context['league_id']}/trade-block/refresh-stats",
            timeout=30,
        )
        # chriszarek is co_commissioner
        assert r_owner.status_code == 200, r_owner.text


class TestRegression:
    def test_get_no_filter_returns_list(self, owner_session):
        r = owner_session.get(f"{API}/trade-block", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

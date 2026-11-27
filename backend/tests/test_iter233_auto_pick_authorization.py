"""POST /api/drafts/{id}/auto-pick must only fire for league members whose pick
clock has run out (commissioners and platform admins may skip early).

Regression for a security bug: the route used to require only a valid login, so
any self-registered account could make picks for every team in any draft,
at any time. Disposable Compose stack only (see e2e/README.md).
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
import requests
from bson import ObjectId

from http_test_auth import test_admin_headers
from security_http_fixtures import API_URL, security_db, security_users  # noqa: F401  (pytest fixtures)


def _iso_ago(seconds):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def seed_draft(security_db):
    """Factory: league + one team per owner + players + an active draft."""
    created = {"leagues": [], "players": []}

    def make(owners, *, started_ago=0, **draft_overrides):
        suffix = uuid.uuid4().hex[:8]
        league_id = str(security_db.leagues.insert_one({
            "name": f"i233 auto-pick {suffix}", "commissioner_id": owners[0]["id"], "status": "active",
        }).inserted_id)
        created["leagues"].append(league_id)
        abbrs, team_map = [], {}
        for i, owner in enumerate(owners):
            team_id = str(security_db.teams.insert_one({
                "name": f"i233 Team {i + 1}", "league_id": league_id, "owner_id": owner["id"],
                "roster": [], "draft_queue": [],
            }).inserted_id)
            abbr = f"T{i + 1}"
            abbrs.append(abbr)
            team_map[abbr] = {"id": team_id, "name": f"i233 Team {i + 1}"}
        for i in range(6):
            pid = ObjectId()
            security_db.players.insert_one({
                "_id": pid, "nhl_id": f"i233-{pid}", "name": f"i233 Player {i + 1}", "position": "C",
                "team": "TOR", "team_name": "Toronto", "points": 100 - i, "games_played": 82,
                "player_type": "skater",
            })
            created["players"].append(pid)
        started = _iso_ago(started_ago)
        draft = {
            "league_id": league_id, "name": "i233 Draft", "status": "active", "draft_type": "snake",
            "snake_draft": True, "total_rounds": 2, "time_per_pick": 60, "current_pick": 1,
            "team_abbrs": abbrs, "team_map": team_map, "picks": [], "chat_messages": [],
            "current_pick_started_at": started, "started_at": started,
        }
        draft.update(draft_overrides)
        return str(security_db.drafts.insert_one(draft).inserted_id)

    try:
        yield make
    finally:
        for league_id in created["leagues"]:
            security_db.drafts.delete_many({"league_id": league_id})
            security_db.teams.delete_many({"league_id": league_id})
            security_db.leagues.delete_one({"_id": ObjectId(league_id)})
        security_db.players.delete_many({"_id": {"$in": created["players"]}})


@pytest.fixture
def cast(security_users):
    """commissioner (owns T1, on the clock first), member (owns T2), outsider (no team)."""
    return {"commissioner": security_users(), "member": security_users(), "outsider": security_users()}


def _fire(draft_id, headers=None, expected_pick=None):
    kwargs = {"json": {"expected_pick": expected_pick}} if expected_pick is not None else {}
    return requests.post(f"{API_URL}/api/drafts/{draft_id}/auto-pick", headers=headers or {}, timeout=20, **kwargs)


def _state(db, draft_id):
    d = db.drafts.find_one({"_id": ObjectId(draft_id)})
    return d["current_pick"], [p["overall"] for p in d.get("picks", [])], d.get("picks", [])


def _owners(cast):
    return [cast["commissioner"], cast["member"]]


# --- authentication / membership -------------------------------------------------

def test_unauthenticated_is_rejected(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=3600)
    assert _fire(draft_id).status_code == 401
    assert _state(security_db, draft_id)[:2] == (1, [])


def test_outsider_cannot_skip_turns_on_a_fresh_clock(seed_draft, cast, security_db):
    """The original exploit: a stranger forcing picks for every team."""
    draft_id = seed_draft(_owners(cast), started_ago=0)
    for _ in range(3):
        assert _fire(draft_id, cast["outsider"]["headers"]).status_code == 403
    assert _state(security_db, draft_id)[:2] == (1, [])


def test_outsider_cannot_fire_even_when_the_clock_has_expired(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=3600)
    assert _fire(draft_id, cast["outsider"]["headers"]).status_code == 403
    assert _state(security_db, draft_id)[:2] == (1, [])


# --- pick clock ------------------------------------------------------------------

def test_member_cannot_fire_before_the_clock_expires(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=0)
    assert _fire(draft_id, cast["member"]["headers"]).status_code == 409
    assert _state(security_db, draft_id)[:2] == (1, [])


def test_member_can_fire_once_the_clock_has_expired(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=3600)
    r = _fire(draft_id, cast["member"]["headers"])
    assert r.status_code == 200, r.text
    current, overalls, picks = _state(security_db, draft_id)
    assert (current, overalls) == (2, [1])
    assert picks[0]["auto_pick_source"] == "timeout"


def test_browser_firing_at_its_own_zero_is_accepted_but_early_requests_are_not(seed_draft, cast, security_db):
    """time_per_pick=60. The worker waits 3s past the deadline so browsers go
    first; the route must therefore accept a request at (roughly) 60s elapsed,
    allowing a couple of seconds of client clock skew, but not one at 55s."""
    early = seed_draft(_owners(cast), started_ago=55)
    assert _fire(early, cast["member"]["headers"]).status_code == 409
    at_zero = seed_draft(_owners(cast), started_ago=59)
    assert _fire(at_zero, cast["member"]["headers"]).status_code == 200


def test_personal_timer_cap_is_honoured_like_the_worker(seed_draft, cast, security_db):
    fresh = seed_draft(_owners(cast), started_ago=0, time_per_pick=3600, personal_pick_timer_seconds=5)
    assert _fire(fresh, cast["member"]["headers"]).status_code == 409
    expired = seed_draft(_owners(cast), started_ago=60, time_per_pick=3600, personal_pick_timer_seconds=5)
    r = _fire(expired, cast["member"]["headers"])
    assert r.status_code == 200, r.text
    assert _state(security_db, expired)[2][0]["auto_pick_source"] == "personal_timeout"


def test_paused_clock_blocks_members(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=3600, timer_paused=True)
    assert _fire(draft_id, cast["member"]["headers"]).status_code == 409
    assert _state(security_db, draft_id)[:2] == (1, [])


def test_inactive_draft_is_rejected(seed_draft, cast):
    draft_id = seed_draft(_owners(cast), started_ago=3600, status="scheduled")
    assert _fire(draft_id, cast["member"]["headers"]).status_code == 400


# --- stale / duplicate requests --------------------------------------------------

def test_stale_expected_pick_is_rejected_and_matching_is_accepted(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=3600)
    assert _fire(draft_id, cast["member"]["headers"], expected_pick=2).status_code == 409
    assert _state(security_db, draft_id)[:2] == (1, [])
    assert _fire(draft_id, cast["member"]["headers"], expected_pick=1).status_code == 200
    assert _state(security_db, draft_id)[:2] == (2, [1])


def test_simultaneous_member_requests_make_exactly_one_pick(seed_draft, cast, security_db):
    """Several browsers all see the countdown hit zero and fire together."""
    draft_id = seed_draft(_owners(cast), started_ago=3600)
    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = sorted(pool.map(
            lambda _: _fire(draft_id, cast["member"]["headers"], expected_pick=1).status_code, range(5)))
    assert codes == [200, 409, 409, 409, 409], codes
    assert _state(security_db, draft_id)[:2] == (2, [1])


# --- privileged early skips ------------------------------------------------------

def test_league_commissioner_can_skip_a_pick_early(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=0)
    r = _fire(draft_id, cast["commissioner"]["headers"])
    assert r.status_code == 200, r.text
    current, overalls, picks = _state(security_db, draft_id)
    assert (current, overalls) == (2, [1])
    assert picks[0]["auto_pick_source"] == "commissioner_skip"


def test_platform_admin_can_skip_a_pick_early(seed_draft, cast, security_db):
    draft_id = seed_draft(_owners(cast), started_ago=0)
    r = _fire(draft_id, test_admin_headers())
    assert r.status_code == 200, r.text
    assert _state(security_db, draft_id)[:2] == (2, [1])

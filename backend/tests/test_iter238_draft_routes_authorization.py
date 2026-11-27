"""Draft routes must be limited to the league's members.

Audit of every /drafts route found: draft detail, board, stats, chat, auction
state, eligible players, picks, draft order and more answered with no login at
all; `GET /drafts` listed every league's drafts to anyone; any signed-in user
could post to a draft's chat, read another team's auto-pick queue, and (worst)
propose and vote on in-draft pick trades in leagues they do not belong to, with
the default `auto_execute` policy moving picks and players between teams.
Disposable Compose stack only (see e2e/README.md).
"""
import uuid

import pytest
import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users  # noqa: F401

READS = [
    "/drafts/{d}", "/drafts/{d}/board", "/drafts/{d}/stats", "/drafts/{d}/chat", "/drafts/{d}/auction/state",
    "/drafts/{d}/eligible-players", "/drafts/{d}/player-stats", "/drafts/{d}/related-trades", "/drafts/{d}/edit-preview",
    "/drafts/{d}/leaderboard", "/drafts/{d}/picks/1/defer",
    "/drafts/{l}/picks", "/drafts/{l}/pick-trades/pending", "/leagues/{l}/upcoming-drafts", "/leagues/{l}/draft-order",
    "/leagues/{l}/expansion-draft-board", "/leagues/{l}/draft-hall-of-awards",
]


@pytest.fixture
def world(security_db, security_users):
    suffix = uuid.uuid4().hex[:8]
    com, mem, out = security_users(), security_users(), security_users()
    league_id = str(security_db.leagues.insert_one({
        "name": f"i238 {suffix}", "commissioner_id": com["id"], "status": "active", "is_private": True,
    }).inserted_id)
    teams = {}
    for key, user in (("com", com), ("mem", mem)):
        teams[key] = str(security_db.teams.insert_one({
            "name": f"i238 {key}", "league_id": league_id, "owner_id": user["id"], "roster": [], "draft_queue": ["secret-1"],
        }).inserted_id)
    draft_id = str(security_db.drafts.insert_one({
        "league_id": league_id, "name": "i238", "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60, "current_pick": 1, "team_abbrs": ["A", "B"],
        "team_map": {"A": {"id": teams["com"], "name": "i238 com"}, "B": {"id": teams["mem"], "name": "i238 mem"}},
        "picks": [], "chat_messages": [{"id": "m1", "sender": "x", "text": "private plan"}],
    }).inserted_id)
    other_league = str(security_db.leagues.insert_one({"name": f"i238 other {suffix}", "commissioner_id": out["id"], "status": "active"}).inserted_id)
    other_draft = str(security_db.drafts.insert_one({
        "league_id": other_league, "name": "i238 other", "status": "active", "picks": [], "team_abbrs": ["A"], "team_map": {},
        "draft_type": "snake", "total_rounds": 1, "time_per_pick": 60, "current_pick": 1,
        "created_at": "2099-01-01T00:00:00+00:00", "scheduled_at": "2099-01-01T00:00:00+00:00",
    }).inserted_id)
    try:
        yield {"com": com, "mem": mem, "out": out, "league": league_id, "draft": draft_id, "teams": teams,
               "other_league": other_league, "other_draft": other_draft}
    finally:
        for lid in (league_id, other_league):
            security_db.drafts.delete_many({"league_id": lid})
            security_db.teams.delete_many({"league_id": lid})
            security_db.trades.delete_many({"league_id": lid})
            security_db.leagues.delete_one({"_id": ObjectId(lid)})


def _url(path, w):
    return API_URL + "/api" + path.format(d=w["draft"], l=w["league"])


@pytest.mark.parametrize("path", READS)
def test_reads_require_login(path, world):
    assert requests.get(_url(path, world), timeout=20).status_code == 401, path


@pytest.mark.parametrize("path", READS)
def test_reads_reject_non_members(path, world):
    r = requests.get(_url(path, world), headers=world["out"]["headers"], timeout=20)
    assert r.status_code == 403, (path, r.status_code, r.text[:120])


@pytest.mark.parametrize("path", READS)
def test_reads_still_work_for_members(path, world):
    for key in ("mem", "com"):
        r = requests.get(_url(path, world), headers=world[key]["headers"], timeout=20)
        assert r.status_code not in (401, 403), (key, path, r.status_code, r.text[:120])


def test_draft_list_requires_login_and_only_shows_my_leagues(world):
    assert requests.get(f"{API_URL}/api/drafts", timeout=20).status_code == 401
    for headers in (world["mem"]["headers"],):
        ids = {d["_id"] for d in requests.get(f"{API_URL}/api/drafts", params={"include_orphans": "true"}, headers=headers, timeout=20).json()}
        assert world["draft"] in ids
        assert world["other_draft"] not in ids
    r = requests.get(f"{API_URL}/api/drafts", params={"league_id": world["league"]}, headers=world["out"]["headers"], timeout=20)
    assert r.status_code == 403


def test_outsider_cannot_post_to_draft_chat(world, security_db):
    r = requests.post(f"{API_URL}/api/drafts/{world['draft']}/chat", json={"text": "spam"}, headers=world["out"]["headers"], timeout=20)
    assert r.status_code == 403
    assert not any(m.get("text") == "spam" for m in security_db.drafts.find_one({"_id": ObjectId(world["draft"])}).get("chat_messages", []))
    ok = requests.post(f"{API_URL}/api/drafts/{world['draft']}/chat", json={"text": "hello"}, headers=world["mem"]["headers"], timeout=20)
    assert ok.status_code == 200


def test_draft_queue_is_private_to_owner_and_commissioner(world):
    url = f"{API_URL}/api/teams/{world['teams']['mem']}/draft-queue"
    assert requests.get(url, timeout=20).status_code == 401
    assert requests.get(url, headers=world["out"]["headers"], timeout=20).status_code == 403
    assert requests.get(url, headers=world["com"]["headers"], timeout=20).status_code == 200  # commissioner
    assert requests.get(url, headers=world["mem"]["headers"], timeout=20).json()["draft_queue"] == ["secret-1"]
    # a rival manager must not read another team's queue
    rival_url = f"{API_URL}/api/teams/{world['teams']['com']}/draft-queue"
    assert requests.get(rival_url, headers=world["mem"]["headers"], timeout=20).status_code == 403


def _trade_body(w, **extra):
    body = {"proposer_team_id": w["teams"]["mem"], "receiver_team_id": w["teams"]["com"],
            "proposer_assets": [{"type": "pick", "year": 2030, "round": 1}], "receiver_assets": []}
    body.update(extra)
    return body


def test_outsider_cannot_propose_a_pick_trade(world, security_db):
    r = requests.post(f"{API_URL}/api/drafts/{world['league']}/propose-pick-trade", json=_trade_body(world),
                      headers=world["out"]["headers"], timeout=20)
    assert r.status_code == 403, r.text
    assert security_db.trades.count_documents({"league_id": world["league"]}) == 0


def test_member_cannot_propose_a_trade_for_someone_elses_team(world, security_db):
    body = _trade_body(world, proposer_team_id=world["teams"]["com"], receiver_team_id=world["teams"]["mem"])
    r = requests.post(f"{API_URL}/api/drafts/{world['league']}/propose-pick-trade", json=body, headers=world["mem"]["headers"], timeout=20)
    assert r.status_code == 403, r.text
    assert security_db.trades.count_documents({"league_id": world["league"]}) == 0


def test_player_assets_must_be_on_the_proposing_roster(world, security_db):
    body = _trade_body(world, proposer_assets=[{"type": "player", "player_id": "000000000000000000000abc"}])
    r = requests.post(f"{API_URL}/api/drafts/{world['league']}/propose-pick-trade", json=body, headers=world["mem"]["headers"], timeout=20)
    assert r.status_code == 400, r.text


def test_teams_must_belong_to_the_league(world, security_db):
    foreign = str(security_db.teams.insert_one({"name": "foreign", "league_id": world["other_league"], "owner_id": world["out"]["id"], "roster": []}).inserted_id)
    body = _trade_body(world, receiver_team_id=foreign)
    r = requests.post(f"{API_URL}/api/drafts/{world['league']}/propose-pick-trade", json=body, headers=world["mem"]["headers"], timeout=20)
    assert r.status_code in (400, 404), r.text


def test_owner_can_propose_and_only_members_can_vote(world, security_db):
    r = requests.post(f"{API_URL}/api/drafts/{world['league']}/propose-pick-trade", json=_trade_body(world), headers=world["mem"]["headers"], timeout=20)
    assert r.status_code == 200, r.text
    tid = r.json()["trade_id"]
    vote = f"{API_URL}/api/drafts/{world['league']}/pick-trade/{tid}/vote"
    # the receiving team (com) must accept before the league can vote
    acc = requests.post(f"{API_URL}/api/drafts/{world['league']}/pick-trade/{tid}/accept", headers=world["com"]["headers"], timeout=20)
    assert acc.status_code == 200, acc.text
    assert requests.post(vote, json={"choice": "veto"}, headers=world["out"]["headers"], timeout=20).status_code == 403
    assert requests.post(vote, json={"choice": "approve"}, timeout=20).status_code == 401
    assert requests.get(f"{API_URL}/api/drafts/{world['league']}/pick-trade/{tid}", headers=world["out"]["headers"], timeout=20).status_code == 403
    ok = requests.post(vote, json={"choice": "approve"}, headers=world["com"]["headers"], timeout=20)
    assert ok.status_code == 200, ok.text

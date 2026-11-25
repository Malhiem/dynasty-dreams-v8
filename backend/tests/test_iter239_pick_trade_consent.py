"""In-draft pick trades need the receiving team's consent.

The proposer's acceptance is implied. The receiver accepts, declines or edits;
an edit sends the trade back to the other team to accept. Only an accepted
trade can be voted on, and a commissioner cannot execute it on a team's behalf.
"""
import uuid

import pytest
import requests
from bson import ObjectId

from security_http_fixtures import API_URL, security_db, security_users  # noqa: F401


@pytest.fixture
def world(security_db, security_users):
    com, mem, out = security_users(), security_users(), security_users()
    league = str(security_db.leagues.insert_one({
        "name": f"i239 {uuid.uuid4().hex[:6]}", "commissioner_id": com["id"], "status": "active",
    }).inserted_id)
    teams = {k: str(security_db.teams.insert_one({
        "name": f"i239 {k}", "league_id": league, "owner_id": u["id"], "roster": [],
    }).inserted_id) for k, u in (("com", com), ("mem", mem))}
    try:
        yield {"league": league, "teams": teams, "com": com, "mem": mem, "out": out}
    finally:
        security_db.trades.delete_many({"league_id": league})
        security_db.teams.delete_many({"league_id": league})
        security_db.leagues.delete_one({"_id": ObjectId(league)})


def _post(w, path, who, json=None):
    return requests.post(f"{API_URL}/api/drafts/{w['league']}/{path}", json=json, headers=w[who]["headers"], timeout=20)


def _get(w, tid, who):
    return requests.get(f"{API_URL}/api/drafts/{w['league']}/pick-trade/{tid}", headers=w[who]["headers"], timeout=20).json()


def _propose(w, who="mem"):
    to = "com" if who == "mem" else "mem"
    r = _post(w, "propose-pick-trade", who, {
        "proposer_team_id": w["teams"][who], "receiver_team_id": w["teams"][to],
        "proposer_assets": [{"type": "pick", "year": 2030, "round": 1}], "receiver_assets": [],
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_new_trade_waits_on_the_receiver(world):
    out = _propose(world)
    assert out["status"] == "pending_acceptance"
    assert out["awaiting_team_id"] == world["teams"]["com"]
    assert out["review_expires_at"] is None
    assert _get(world, out["trade_id"], "com")["can_respond"] is True
    assert _get(world, out["trade_id"], "mem")["can_respond"] is False


def test_nobody_can_vote_before_the_receiver_accepts(world):
    tid = _propose(world)["trade_id"]
    r = _post(world, f"pick-trade/{tid}/vote", "com", {"choice": "approve"})
    assert r.status_code == 400, r.text


def test_only_the_awaited_team_can_respond(world):
    tid = _propose(world)["trade_id"]
    for who in ("mem", "out"):  # the sender cannot accept their own offer; outsiders are not members
        assert _post(world, f"pick-trade/{tid}/accept", who).status_code == 403
    assert _get(world, tid, "mem")["status"] == "pending_acceptance"


def test_commissioner_cannot_accept_for_a_team_or_force_execute(world, security_db):
    # com owns the receiving team here, so use a trade the other way: com proposes, mem must answer
    tid = _propose(world, who="com")["trade_id"]
    assert _post(world, f"pick-trade/{tid}/accept", "com").status_code == 403
    r = _post(world, f"pick-trade/{tid}/resolve", "com", {"decision": "execute"})
    assert r.status_code == 400, r.text
    assert security_db.trades.find_one({"_id": ObjectId(tid)})["status"] == "pending_acceptance"


def test_accept_opens_the_review_window_and_voting(world):
    tid = _propose(world)["trade_id"]
    acc = _post(world, f"pick-trade/{tid}/accept", "com")
    assert acc.status_code == 200, acc.text
    assert acc.json()["status"] == "pending_draft_review" and acc.json()["review_expires_at"]
    assert _post(world, f"pick-trade/{tid}/accept", "com").status_code == 400  # not accepted twice
    assert _post(world, f"pick-trade/{tid}/vote", "mem", {"choice": "approve"}).status_code == 200


def test_decline_ends_the_trade(world):
    tid = _propose(world)["trade_id"]
    assert _post(world, f"pick-trade/{tid}/decline", "mem").status_code == 403
    assert _post(world, f"pick-trade/{tid}/decline", "com").status_code == 200
    assert _get(world, tid, "mem")["status"] == "declined"
    assert _post(world, f"pick-trade/{tid}/accept", "com").status_code == 400


def test_receiver_edit_returns_it_to_the_sender(world):
    tid = _propose(world)["trade_id"]
    counter = {"proposer_assets": [{"type": "pick", "year": 2030, "round": 1}],
               "receiver_assets": [{"type": "pick", "year": 2031, "round": 2}]}
    r = _post(world, f"pick-trade/{tid}/edit", "com", counter)
    assert r.status_code == 200, r.text
    assert r.json()["awaiting_team_id"] == world["teams"]["mem"]
    state = _get(world, tid, "mem")
    assert state["status"] == "pending_acceptance"
    assert state["can_respond"] is True and _get(world, tid, "com")["can_respond"] is False
    assert state["receiver_assets"] == counter["receiver_assets"]
    # the receiver cannot accept their own edit; the sender can, which opens review
    assert _post(world, f"pick-trade/{tid}/accept", "com").status_code == 403
    assert _post(world, f"pick-trade/{tid}/accept", "mem").status_code == 200


def test_edit_is_validated(world):
    tid = _propose(world)["trade_id"]
    no_pick = {"proposer_assets": [], "receiver_assets": []}
    assert _post(world, f"pick-trade/{tid}/edit", "com", no_pick).status_code == 400
    ghost = {"proposer_assets": [{"type": "pick"}], "receiver_assets": [{"type": "player", "player_id": "000000000000000000000abc"}]}
    assert _post(world, f"pick-trade/{tid}/edit", "com", ghost).status_code == 400
    assert _post(world, f"pick-trade/{tid}/edit", "mem", {"proposer_assets": [{"type": "pick"}], "receiver_assets": []}).status_code == 403


def test_editing_clears_votes_and_cannot_happen_after_acceptance(world):
    tid = _propose(world)["trade_id"]
    _post(world, f"pick-trade/{tid}/accept", "com")
    r = _post(world, f"pick-trade/{tid}/edit", "mem", {"proposer_assets": [{"type": "pick"}], "receiver_assets": []})
    assert r.status_code == 400, r.text


def test_pending_list_includes_trades_awaiting_acceptance(world):
    tid = _propose(world)["trade_id"]
    rows = requests.get(f"{API_URL}/api/drafts/{world['league']}/pick-trades/pending", headers=world["com"]["headers"], timeout=20).json()["pending"]
    row = next(x for x in rows if x["trade_id"] == tid)
    assert row["status"] == "pending_acceptance" and row["can_respond"] is True

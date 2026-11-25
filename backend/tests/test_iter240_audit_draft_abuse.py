"""The abuse-audit script's detection rules (pure functions, no database)."""
from bson import ObjectId

from scripts.audit_draft_abuse import early_and_burst_auto_picks, pick_trade_findings


def _draft(picks, per_pick=90):
    return {"_id": ObjectId(), "league_id": "L", "time_per_pick": per_pick, "picks": picks}


def _pick(n, taken, source="timeout", ts="2026-03-01T12:00:00+00:00", auto=True):
    return {"overall": n, "auto_picked": auto, "auto_pick_source": source, "time_taken_seconds": taken, "timestamp": ts, "team_id": "T"}


def test_auto_pick_before_the_clock_ran_out_is_flagged():
    found = early_and_burst_auto_picks(_draft([_pick(1, 3)]))
    assert [f["kind"] for f in found] == ["early_auto_pick"] and found[0]["severity"] == "HIGH"


def test_legitimate_auto_picks_are_not_flagged():
    minute = lambda m: f"2026-03-01T12:{m:02d}:00+00:00"  # spread out, so no burst
    picks = [_pick(1, 90, ts=minute(1)), _pick(2, 88, ts=minute(5)), _pick(3, 5, "commissioner_skip", minute(9)),
             _pick(4, 2, "eviction", minute(13)), _pick(5, 10, auto=False), _pick(6, None, ts=minute(17))]
    assert early_and_burst_auto_picks(_draft(picks)) == []


def test_rapid_fire_burst_is_flagged_once():
    picks = [_pick(n, 90, ts=f"2026-03-01T12:00:0{n}+00:00") for n in range(1, 6)]
    found = early_and_burst_auto_picks(_draft(picks))
    assert [f["kind"] for f in found] == ["auto_pick_burst"]


LEAGUE = {"commissioner_id": "com", "co_commissioners": []}


def _teams(**over):
    return {"P": {"_id": "P", "league_id": "L", "owner_id": "alice"}, "R": {"_id": "R", "league_id": "L", "owner_id": "bob"}, **over}


def _trade(**kw):
    return {"_id": ObjectId(), "league_id": "L", "proposer_team_id": "P", "receiver_team_id": "R",
            "created_by": "alice", "status": "pending_draft_review", "votes": {"voters": []}, **kw}


def _kinds(trade, teams=None, members=("alice", "bob", "com"), league=LEAGUE):
    return {f["kind"] for f in pick_trade_findings(trade, league, teams or _teams(), set(), set(members))}


def test_normal_trade_is_clean():
    assert _kinds(_trade()) == set()


def test_outsider_proposal_and_votes_are_flagged():
    assert "creator_not_in_league" in _kinds(_trade(created_by="mallory"))
    assert "votes_from_non_members" in _kinds(_trade(votes={"voters": ["mallory"]}))


def test_member_trading_for_someone_elses_team_is_flagged():
    assert "creator_not_on_proposing_team" in _kinds(_trade(created_by="bob"))
    assert _kinds(_trade(created_by="com")) == set()  # commissioners may act for any team


def test_cross_league_and_dangling_references():
    assert "cross_league_team" in _kinds(_trade(), teams=_teams(R={"_id": "R", "league_id": "OTHER", "owner_id": "bob"}))
    assert _kinds(_trade(), league=None) == {"dangling_reference"}


def test_executed_trade_the_receiver_never_touched_is_a_review_lead():
    assert "executed_without_receiver_involvement" in _kinds(_trade(status="executed"))
    assert "executed_without_receiver_involvement" not in _kinds(_trade(status="executed", votes={"voters": ["bob"]}))

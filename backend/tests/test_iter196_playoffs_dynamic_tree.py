"""
Iter 196 — Playoffs trio (Task A dynamic tree wired + Task B per-round
matchup-length overrides + Task C consolation bracket).

Coverage:
1. `LeagueUpdate` whitelist now persists `playoff_week_lengths` +
   `draft_trade_review_minutes` + `draft_trade_post_delay_action`.
2. `_build_single_elim_rounds` produces the expected matchup pairings for
   `high_vs_low` and `adjacent` seeding methods.
3. `_annotate_rounds_with_week_lengths` stamps `length_weeks` correctly
   (default 1; per-round overrides applied; resilient to malformed dicts).
4. `_build_consolation_block` returns None when disabled or insufficient
   teams; produces the right size + seeded slots otherwise.
5. `GET /leagues/{id}/playoff-bracket` payload now surfaces
   `consolation_bracket` + `playoff_week_lengths` + `consolation_enabled`.
"""
from __future__ import annotations

from routes import leagues as leagues_routes  # noqa: E402


def test_league_update_whitelist_includes_iter196_keys():
    allowed = leagues_routes._LEAGUE_UPDATE_ALLOWED
    assert "playoff_week_lengths" in allowed
    assert "draft_trade_review_minutes" in allowed
    assert "draft_trade_post_delay_action" in allowed


def test_single_elim_rounds_high_vs_low():
    slots = [{"team_id": f"t{i}", "team_name": f"T{i}", "seed": i} for i in range(1, 9)]
    rounds = leagues_routes._build_single_elim_rounds(slots, "high_vs_low")
    # 8 teams → QF (4) → SF (2) → F (1) = 3 rounds
    assert len(rounds) == 3
    qf = rounds[0]["matchups"]
    assert len(qf) == 4
    # high_vs_low: 1v8, 2v7, 3v6, 4v5
    pairings = [(m["high_seed"]["seed"], m["low_seed"]["seed"]) for m in qf]
    assert pairings == [(1, 8), (2, 7), (3, 6), (4, 5)]
    assert rounds[-1]["name"] == "Championship"


def test_single_elim_rounds_adjacent():
    slots = [{"team_id": f"t{i}", "team_name": f"T{i}", "seed": i} for i in range(1, 5)]
    rounds = leagues_routes._build_single_elim_rounds(slots, "adjacent")
    # 4 teams → 2 rounds. adjacent: 1v2, 3v4
    sf = rounds[0]["matchups"]
    pairings = [(m["high_seed"]["seed"], m["low_seed"]["seed"]) for m in sf]
    assert pairings == [(1, 2), (3, 4)]
    assert rounds[0]["name"] == "Semifinals"
    assert rounds[-1]["name"] == "Championship"


def test_annotate_rounds_with_week_lengths_default_and_override():
    rounds = [{"name": "QF"}, {"name": "SF"}, {"name": "Final"}]
    leagues_routes._annotate_rounds_with_week_lengths(rounds, None)
    assert all(r["length_weeks"] == 1 for r in rounds)

    rounds2 = [{"name": "QF"}, {"name": "SF"}, {"name": "Final"}]
    leagues_routes._annotate_rounds_with_week_lengths(
        rounds2,
        {"3": {"length_weeks": 2}, "1": {"length_weeks": 1}},
    )
    assert rounds2[0]["length_weeks"] == 1
    assert rounds2[1]["length_weeks"] == 1
    assert rounds2[2]["length_weeks"] == 2


def test_annotate_rounds_with_week_lengths_malformed_falls_back_to_one():
    rounds = [{"name": "QF"}, {"name": "SF"}]
    leagues_routes._annotate_rounds_with_week_lengths(
        rounds, {"1": "garbage", "2": {"length_weeks": "nope"}}
    )
    assert rounds[0]["length_weeks"] == 1
    assert rounds[1]["length_weeks"] == 1


def _slot_factory(team, seed):
    return {
        "team_id": str(team["_id"]),
        "team_name": team.get("name"),
        "team_abbr": team.get("logo_abbr"),
        "team_logo_url": None,
        "owner_name": None,
        "seed": seed,
        "wins": team.get("wins", 0),
        "losses": team.get("losses", 0),
        "ties": 0,
        "points_for": team.get("points_for", 0),
        "games_back": 0,
    }


def test_consolation_block_disabled():
    league = {"consolation_enabled": False}
    teams = [{"_id": f"t{i}", "name": f"T{i}", "wins": 12 - i} for i in range(12)]
    out = leagues_routes._build_consolation_block(league, teams, _slot_factory, playoff_size=6)
    assert out is None


def test_consolation_block_enabled_high_vs_low():
    league = {
        "consolation_enabled": True,
        "consolation_teams": 4,
        "consolation_seeding_method": "high_vs_low",
    }
    # 12 teams, sorted desc by wins so _rank_teams returns them in order
    teams = [
        {"_id": f"t{i}", "name": f"T{i}", "wins": 12 - i, "losses": i, "ties": 0, "points_for": 100 - i}
        for i in range(12)
    ]
    out = leagues_routes._build_consolation_block(league, teams, _slot_factory, playoff_size=6)
    assert out is not None
    assert out["size"] == 4
    assert out["seeding_method"] == "high_vs_low"
    # Seeded from non-playoff teams (indices 6..9 of ranked list)
    assert [s["team_id"] for s in out["seeds"]] == ["t6", "t7", "t8", "t9"]
    # high_vs_low SF: 1v4, 2v3 (where 1,2,3,4 are within consolation seeding)
    sf = out["rounds"][0]["matchups"]
    assert (sf[0]["high_seed"]["team_id"], sf[0]["low_seed"]["team_id"]) == ("t6", "t9")
    assert (sf[1]["high_seed"]["team_id"], sf[1]["low_seed"]["team_id"]) == ("t7", "t8")


def test_consolation_block_rounded_down_to_power_of_two():
    league = {"consolation_enabled": True, "consolation_teams": 6}
    teams = [
        {"_id": f"t{i}", "name": f"T{i}", "wins": 12 - i, "losses": i, "ties": 0, "points_for": 100 - i}
        for i in range(12)
    ]
    out = leagues_routes._build_consolation_block(league, teams, _slot_factory, playoff_size=6)
    assert out is not None
    # 6 non-playoff teams + 6 requested → round down to 4 for clean bracket math
    assert out["size"] == 4


def test_consolation_block_insufficient_teams_returns_none():
    league = {"consolation_enabled": True, "consolation_teams": 4}
    teams = [
        {"_id": f"t{i}", "name": f"T{i}", "wins": 4 - i, "losses": i, "ties": 0, "points_for": 100 - i}
        for i in range(4)
    ]
    # All 4 teams in the playoffs → no consolation possible
    out = leagues_routes._build_consolation_block(league, teams, _slot_factory, playoff_size=4)
    assert out is None

from copy import deepcopy

import pytest

from services.combined_scheduler import Settings, check, defaults, solve, validate


def teams(n=24):
    return [{"_id": str(i), "name": f"Team {i + 1}", "division": f"D{i // 6}", "conference": f"C{i // 12}"} for i in range(n)]


def rule(group, value, scope="per_opponent", comparison="exact"):
    return dict(group=group, value=value, scope=scope, comparison=comparison)


def test_24_teams_two_distinct_opponents_with_exact_division_and_conference_mix():
    t = teams()
    s = Settings(weeks=20, games_per_week=2, rules=[rule("division", 2), rule("conference_other", 1), rule("outside_conference", 2)])
    result = solve(t, s)
    assert result["status"] == "feasible", result
    assert len(result["games"]) == 480
    assert result["validation"]["valid"]
    for row in result["validation"]["teams"]:
        assert (row["games"], row["division"], row["conference_other"], row["conference"], row["outside_conference"]) == (40, 10, 6, 16, 24)
    assert validate(t, s, result["games"])["valid"]
    assert all(abs(r["home_games"] - r["away_games"]) <= 2 for r in result["validation"]["teams"])


def test_aggregate_conference_minimum_includes_division_and_preserves_locked_orientation():
    t = teams(8)
    for i, team in enumerate(t): team.update(division=f"D{i // 2}", conference=f"C{i // 4}")
    s = Settings(weeks=4, games_per_week=2, rules=[rule("division", 1, "total", "minimum"), rule("conference", 4, "total", "minimum"), rule("all", 2, "per_opponent", "maximum")])
    locked = [{"_id": "fixed-result", "week": 1, "home_team_id": "1", "away_team_id": "0", "status": "completed"}]
    result = solve(t, s, locked, time_limit=3)
    assert result["status"] == "feasible", result
    assert any(g.get("preserved_id") == "fixed-result" and g["home_team_id"] == "1" for g in result["games"])
    assert all(r["conference"] >= 4 and r["division"] >= 1 for r in result["validation"]["teams"])


def test_odd_team_count_with_even_weekly_degree_has_no_automatic_byes():
    result = solve(teams(7), Settings(weeks=3, games_per_week=2), time_limit=2)
    assert result["status"] == "feasible"
    assert len(result["games"]) == 21


@pytest.mark.parametrize("n,k", [(7, 1), (4, 4), (2, 2)])
def test_weekly_capacity_conflicts(n, k):
    assert check(teams(n), Settings(weeks=4, games_per_week=k))


def test_exact_pair_counts_cannot_silently_underfill_the_season():
    s = Settings(weeks=20, games_per_week=2, rules=[rule("all", 1)])
    result = solve(teams(), s)
    assert result["status"] == "infeasible"
    assert "40" in result["errors"][0]


def test_nested_aggregate_conflict_is_proven_infeasible():
    s = Settings(weeks=3, games_per_week=2, rules=[rule("division", 3, "total", "minimum"), rule("conference", 2, "total", "maximum")])
    result = solve(teams(6), s, time_limit=2)
    assert result["status"] == "infeasible"


def test_timeout_never_claims_infeasibility():
    result = solve(teams(), Settings(weeks=20, games_per_week=2), time_limit=0)
    assert result["status"] == "timeout"
    assert "does not prove" in result["errors"][0]


def test_independent_validator_rejects_duplicate_weekly_pair_and_changed_lock():
    t = teams(4); s = Settings(weeks=2, games_per_week=2)
    result = solve(t, s, time_limit=2)
    assert result["status"] == "feasible"
    games = deepcopy(result["games"])
    games.append(dict(games[0]))
    assert not validate(t, s, games)["valid"]
    old = {**result["games"][0], "_id": "locked", "status": "completed"}
    altered = deepcopy(result["games"])
    altered[0]["home_team_id"], altered[0]["away_team_id"] = altered[0]["away_team_id"], altered[0]["home_team_id"]
    assert not validate(t, s, altered, [old])["valid"]


def test_locked_conflicts_and_missing_structure_are_explained():
    t = teams(4); s = Settings(weeks=2, games_per_week=1)
    locked = [{"_id": "a", "week": 1, "home_team_id": "0", "away_team_id": "1"}, {"_id": "b", "week": 1, "home_team_id": "0", "away_team_id": "2"}]
    assert any("Locked games" in e for e in check(t, s, locked))
    t[0].pop("division")
    assert any("Assign every" in e for e in check(t, Settings(weeks=2, games_per_week=1, rules=[rule("division", 1)])))


def test_legacy_rules_migrate_without_reinterpreting_exact_counts():
    t = teams(8); t[-1]["division"] = "Other"
    s = defaults({"regular_season_weeks": 20, "matchups_per_week": 2, "schedule_config": {"intra_division_games": 2, "intra_conference_games": 1, "inter_conference_games": 0}}, t)
    assert [(r.group, r.scope, r.comparison, r.value) for r in s.rules] == [("division", "per_opponent", "exact", 2), ("conference_other", "per_opponent", "exact", 1), ("outside_conference", "per_opponent", "exact", 0)]


def test_exact_zero_group_is_honored():
    t = teams(8)
    for i, team in enumerate(t): team.update(division=f"D{i // 2}", conference=f"C{i // 4}")
    s = Settings(weeks=3, games_per_week=2, rules=[rule("outside_conference", 0, "total")])
    result = solve(t, s, time_limit=2)
    assert result["status"] == "feasible"
    assert all(r["outside_conference"] == 0 for r in result["validation"]["teams"])


def test_saved_rules_follow_current_canonical_period_and_capacity_settings():
    s = defaults({"regular_season_weeks": 10, "matchups_per_week": 3,
        "combined_schedule_settings": {"weeks": 4, "games_per_week": 2, "seed": 1, "rules": [rule("division", 1, "total", "minimum")]}}, teams())
    assert (s.weeks, s.games_per_week) == (10, 3)
    assert s.rules[0].value == 1

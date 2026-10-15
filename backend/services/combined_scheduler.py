"""One constraint model for weekly capacities and season opponent requirements."""
from collections import Counter, defaultdict
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group: Literal["division", "conference", "conference_other", "outside_conference", "all"]
    scope: Literal["total", "per_opponent"] = "total"
    comparison: Literal["minimum", "exact", "maximum"] = "minimum"
    value: int = Field(ge=0, le=5148, strict=True)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weeks: int = Field(ge=1, le=52, strict=True)
    games_per_week: int = Field(ge=1, le=99, strict=True)
    rules: list[Rule] = Field(default_factory=list, max_length=20)
    seed: int = Field(default=1, ge=0, le=2147483647, strict=True)


def protected(game):
    return game.get("status", "scheduled") != "scheduled" or bool(game.get("locked") or game.get("is_locked"))


def matches(a, b, group):
    division = bool(a.get("division") and a.get("division") == b.get("division"))
    conference = bool(a.get("conference") and a.get("conference") == b.get("conference"))
    return {"all": True, "division": division, "conference": conference,
            "conference_other": conference and not division, "outside_conference": not conference}[group]


def defaults(league, teams):
    saved = league.get("combined_schedule_settings")
    if saved:
        return Settings.model_validate({**saved,
            "weeks": int(league.get("regular_season_weeks") or saved["weeks"]),
            "games_per_week": int(league.get("matchups_per_week") or league.get("opponents_per_matchup_period") or saved["games_per_week"])})
    rules = []
    legacy = league.get("schedule_config")
    if legacy and len({t.get("division") for t in teams if t.get("division")}) >= 2:
        for group, key in [("division", "intra_division_games"), ("conference_other", "intra_conference_games"),
                           ("outside_conference", "inter_conference_games")]:
            rules.append(Rule(group=group, scope="per_opponent", comparison="exact", value=int(legacy.get(key) or 0)))
    return Settings(weeks=int(league.get("regular_season_weeks") or 18),
                    games_per_week=int(league.get("matchups_per_week") or league.get("opponents_per_matchup_period") or 1), rules=rules)


def bounds(value, rule):
    if rule.comparison == "minimum": return value, None
    if rule.comparison == "maximum": return 0, value
    return value, value


def pair_bounds(teams, settings):
    limits = {}
    for i, j in combinations(range(len(teams)), 2):
        low, high = 0, settings.weeks
        for r in settings.rules:
            if r.scope == "per_opponent" and matches(teams[i], teams[j], r.group):
                lo, hi = bounds(r.value, r)
                low, high = max(low, lo), min(high, hi if hi is not None else high)
        limits[i, j] = low, high
    return limits


def check(teams, settings, locked=()):
    n, k, w = len(teams), settings.games_per_week, settings.weeks
    errors = []
    if n < 2 or k >= n: errors.append(f"{n} teams cannot each face {k} distinct opponents per week.")
    if n * k % 2: errors.append("The weekly game count is odd. Change matchups per week or the team count; automatic byes are not enabled.")
    if any(r.group != "all" for r in settings.rules):
        if any(not t.get("conference") or not t.get("division") for t in teams):
            errors.append("Assign every team and open slot to a division and conference before using group rules.")
        for d in {t.get("division") for t in teams}:
            if len({t.get("conference") for t in teams if t.get("division") == d}) > 1:
                errors.append("A division cannot belong to multiple conferences.")
    limits = pair_bounds(teams, settings)
    for (i, j), (low, high) in limits.items():
        if low > high: errors.append(f"Conflicting requirements for {teams[i]['name']} vs {teams[j]['name']}.")
    total = w * k
    for i, team in enumerate(teams):
        relevant = [v for pair, v in limits.items() if i in pair]
        minimum, maximum = sum(v[0] for v in relevant), sum(v[1] for v in relevant)
        if minimum > total or maximum < total:
            errors.append(f"{team['name']}: opponent requirements allow {minimum}–{maximum} games, but {w} weeks × {k} requires {total}.")
        for r in settings.rules:
            if r.scope != "total": continue
            eligible = [v for pair, v in limits.items() if i in pair and matches(teams[pair[0]], teams[pair[1]], r.group)]
            lo, hi = bounds(r.value, r)
            if lo > min(total, sum(v[1] for v in eligible)) or hi is not None and hi < sum(v[0] for v in eligible):
                errors.append(f"{team['name']}: the {r.group} {r.comparison} of {r.value} conflicts with available opponents or game capacity.")
    ids = {str(t["_id"]) for t in teams}
    seen, counts = set(), Counter()
    for g in locked:
        a, b, week = g.get("home_team_id"), g.get("away_team_id"), g.get("week", 0)
        key = (week, tuple(sorted([str(a), str(b)])))
        if a not in ids or b not in ids or a == b or not 1 <= week <= w or key in seen:
            errors.append("A locked game has an invalid team/week or repeats an opponent within its week.")
        seen.add(key)
        for team in [a, b]: counts[week, team] += 1
    if any(v > k for v in counts.values()): errors.append("Locked games already exceed the weekly matchup limit.")
    return list(dict.fromkeys(errors))


def validate(teams, settings, games, locked=()):
    """Independent validation of solver output; never trust solver status alone."""
    errors = check(teams, settings, locked)
    ids = {str(t["_id"]): t for t in teams}
    appearances, pair_counts, seen = Counter(), Counter(), set()
    for g in games:
        a, b, week = g.get("home_team_id"), g.get("away_team_id"), g.get("week", 0)
        if a not in ids or b not in ids or a == b or not 1 <= week <= settings.weeks:
            errors.append("Schedule contains an invalid team or week."); continue
        pair = tuple(sorted([a, b]))
        if (week, pair) in seen: errors.append("The same opponents play twice in one week.")
        seen.add((week, pair)); pair_counts[pair] += 1
        appearances[week, a] += 1; appearances[week, b] += 1
    report = []
    for tid, team in ids.items():
        if any(appearances[week, tid] != settings.games_per_week for week in range(1, settings.weeks + 1)):
            errors.append(f"{team['name']} does not have exactly {settings.games_per_week} matchups each week.")
        achieved = {}
        for group in ["division", "conference", "conference_other", "outside_conference"]:
            achieved[group] = sum(count for pair, count in pair_counts.items() if tid in pair and matches(ids[pair[0]], ids[pair[1]], group))
        checks = []
        for r in settings.rules:
            opponents = [oid for oid, other in ids.items() if oid != tid and matches(team, other, r.group)]
            values = [pair_counts[tuple(sorted([tid, oid]))] for oid in opponents]
            tested = values if r.scope == "per_opponent" else [sum(values)]
            lo, hi = bounds(r.value, r)
            passed = all(v >= lo and (hi is None or v <= hi) for v in tested)
            if not passed: errors.append(f"{team['name']} fails its {r.group} {r.comparison} requirement.")
            checks.append({**r.model_dump(), "achieved": sum(values), "per_opponent": values, "passed": passed})
        report.append({"team_id": tid, "name": team["name"], "games": sum(appearances[w, tid] for w in range(1, settings.weeks + 1)), **achieved, "home_games": sum(g["home_team_id"] == tid for g in games), "away_games": sum(g["away_team_id"] == tid for g in games), "requirements": checks})
    for g in locked:
        if not any(all(row.get(k) == g.get(k) for k in ["week", "home_team_id", "away_team_id"]) for row in games):
            errors.append("A locked game was changed or removed.")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)), "teams": report}


def solve(teams, settings, locked=(), time_limit=12):
    errors = check(teams, settings, locked)
    if errors: return {"status": "infeasible", "errors": errors}
    n, w, k = len(teams), settings.weeks, settings.games_per_week
    if n * (n - 1) // 2 * w > 200000 or n * w * k // 2 > 10000:
        return {"status": "limit", "errors": ["This configuration exceeds the interactive scheduler size limit. Reduce teams, weeks, or matchups."]}
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()
    pairs = list(combinations(range(n), 2))
    x = {(i, j, week): model.new_bool_var(f"{i}_{j}_{week}") for i, j in pairs for week in range(1, w + 1)}
    for i in range(n):
        for week in range(1, w + 1): model.add(sum(x[a, b, week] for a, b in pairs if i in (a, b)) == k)
    counts = {}
    for (i, j), (low, high) in pair_bounds(teams, settings).items():
        count = model.new_int_var(0, w, f"count_{i}_{j}")
        model.add(count == sum(x[i, j, week] for week in range(1, w + 1)))
        model.add(count >= low); model.add(count <= high); counts[i, j] = count
    for i in range(n):
        for r in settings.rules:
            if r.scope != "total": continue
            expr = sum(counts[a, b] for a, b in pairs if i in (a, b) and matches(teams[a], teams[b], r.group))
            lo, hi = bounds(r.value, r)
            model.add(expr >= lo)
            if hi is not None: model.add(expr <= hi)
    index = {str(t["_id"]): i for i, t in enumerate(teams)}
    fixed = {}
    for g in locked:
        a, b = sorted([index[g["home_team_id"]], index[g["away_team_id"]]])
        model.add(x[a, b, g["week"]] == 1); fixed[g["week"], a, b] = g
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 2
    solver.parameters.random_seed = settings.seed
    status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {"status": "infeasible" if status == cp_model.INFEASIBLE else "timeout",
                "errors": ["These requirements cannot fit together. Reduce exact/minimum counts, loosen maximums, or add weeks." if status == cp_model.INFEASIBLE else "No schedule found within the time limit. This does not prove the settings are impossible. Try again or simplify the rules."]}
    # Optimize only after securing a feasible schedule, retaining it if improvement times out.
    maximum = model.new_int_var(0, w, "maximum_repeats")
    model.add_max_equality(maximum, list(counts.values()))
    penalties = []
    for i, j in pairs:
        for distance, weight in [(1, 4), (2, 2), (3, 1)]:
            for week in range(1, w - distance + 1):
                adjacent = model.new_bool_var(f"near_{i}_{j}_{week}_{distance}")
                model.add(adjacent >= x[i, j, week] + x[i, j, week + distance] - 1)
                penalties.extend([adjacent] * weight)
    if all(t.get("division") and t.get("conference") for t in teams):
        for i in range(n):
            for group in ["division", "conference_other", "outside_conference"]:
                eligible = [(a, b) for a, b in pairs if i in (a, b) and matches(teams[a], teams[b], group)]
                difference = model.new_int_var(0, w * k, f"spread_{i}_{group}")
                early = sum(x[a, b, week] for a, b in eligible for week in range(1, w // 2 + 1))
                model.add_abs_equality(difference, 2 * early - sum(counts[a, b] for a, b in eligible))
                penalties.append(difference)
    model.minimize(maximum * (len(penalties) * w * k + 1) + sum(penalties))
    first = {key: solver.value(var) for key, var in x.items()}
    for key, var in x.items(): model.add_hint(var, first[key])
    better = cp_model.CpSolver(); better.parameters.max_time_in_seconds = min(4, time_limit)
    better.parameters.num_search_workers = 2; better.parameters.random_seed = settings.seed
    improved = better.solve(model)
    chosen = {key: better.value(var) for key, var in x.items()} if improved in (cp_model.FEASIBLE, cp_model.OPTIMAL) else first
    games, home_balance, previous_home = [], Counter(), {}
    for week in range(1, w + 1):
        for i, j in pairs:
            if not chosen[i, j, week]: continue
            a, b = str(teams[i]["_id"]), str(teams[j]["_id"])
            old = fixed.get((week, i, j))
            if old:
                home, away = old["home_team_id"], old["away_team_id"]
            elif (home_balance[a], previous_home.get((i, j)) == a) > (home_balance[b], previous_home.get((i, j)) == b):
                home, away = b, a
            else: home, away = a, b
            home_balance[home] += 1; home_balance[away] -= 1; previous_home[i, j] = home
            row = {"week": week, "home_team_id": home, "away_team_id": away,
                   "home_team_name": teams[index[home]]["name"], "away_team_name": teams[index[away]]["name"]}
            if old: row["preserved_id"] = str(old["_id"])
            games.append(row)
    from services.schedule_preferences import orient
    games = orient(games)
    validation = validate(teams, settings, games, locked)
    return {"status": "feasible" if validation["valid"] else "invalid", "games": games, "validation": validation,
            "errors": validation["errors"], "optimization_complete": improved == cp_model.OPTIMAL}

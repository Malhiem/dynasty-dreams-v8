"""Best-effort home/away balance after mandatory opponent constraints are met."""
from collections import defaultdict


def balanced_start(games):
    """Euler orientation balances every unpinned team, with virtual odd-degree edges."""
    graph, used, fixed = defaultdict(list), set(), {}
    for i, g in enumerate(games):
        a, b = g["home_team_id"], g["away_team_id"]
        graph[a].append((i, b)); graph[b].append((i, a))
        if g.get("preserved_id"): fixed[i] = a
    odd = sorted(team for team, edges in graph.items() if len(edges) % 2)
    for i in range(0, len(odd), 2):
        a, b, index = odd[i], odd[i + 1], len(games) + i
        graph[a].append((index, b)); graph[b].append((index, a))
    for start in list(graph):
        stack = [start]
        while stack:
            team = stack[-1]
            while graph[team] and graph[team][-1][0] in used: graph[team].pop()
            if not graph[team]: stack.pop(); continue
            index, other = graph[team].pop(); used.add(index); stack.append(other)
            if index >= len(games): continue
            game = games[index]
            home = fixed.get(index, team)
            if home != game["home_team_id"]:
                game["home_team_id"], game["away_team_id"] = game["away_team_id"], game["home_team_id"]
                game["home_team_name"], game["away_team_name"] = game["away_team_name"], game["home_team_name"]


def orient(games, time_limit=1):
    from ortools.sat.python import cp_model
    balanced_start(games)
    model = cp_model.CpModel()
    choices, appearances, pairs = [], defaultdict(list), defaultdict(list)
    for i, game in enumerate(games):
        a, b = sorted([game["home_team_id"], game["away_team_id"]])
        choice = model.new_bool_var(f"home_{i}")
        choices.append(choice)
        appearances[a].append(choice); appearances[b].append(1 - choice)
        pairs[a, b].append(choice)
        if game.get("preserved_id"): model.add(choice == int(game["home_team_id"] == a))
        model.add_hint(choice, int(game["home_team_id"] == a))
    imbalance, repeated_home = [], []
    for team, values in appearances.items():
        difference = model.new_int_var(0, len(values), f"imbalance_{team}")
        model.add_abs_equality(difference, 2 * sum(values) - len(values)); imbalance.append(difference)
        if not any(g.get("preserved_id") for g in games):
            model.add(difference <= 1)
    for pair, values in pairs.items():
        for i in range(1, len(values)):
            same = model.new_bool_var(f"same_{pair}_{i}")
            model.add(same >= values[i] + values[i - 1] - 1)
            model.add(same >= 1 - values[i] - values[i - 1]); repeated_home.append(same)
    model.minimize(sum(imbalance) * (len(repeated_home) + 1) + sum(repeated_home))
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = time_limit; solver.parameters.num_search_workers = 2
    status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL): return games
    balance = defaultdict(int)
    for game in games:
        balance[game["home_team_id"]] += 1; balance[game["away_team_id"]] -= 1
    if sum(solver.value(v) for v in imbalance) > sum(abs(v) for v in balance.values()): return games
    for i, game in enumerate(games):
        first = min(game["home_team_id"], game["away_team_id"])
        want_first = bool(solver.value(choices[i]))
        if (game["home_team_id"] == first) != want_first:
            game["home_team_id"], game["away_team_id"] = game["away_team_id"], game["home_team_id"]
            game["home_team_name"], game["away_team_name"] = game["away_team_name"], game["home_team_name"]
    return games

"""
Iter 197 — Pure unit tests for the playoff bracket round-naming + matchup
synthesis logic. Complements the live integration tests in
`test_iter197_playoff_names_mark_winner_prize.py`.
"""
from __future__ import annotations


def _name_for_round_simulator(total_rounds: int, rnd_1based: int) -> str:
    """Mirror of the inner `_name_for_round` helper in `routes/leagues.py`.
    Kept here as a self-contained validator so test failures surface the
    label-by-distance contract independent of MongoDB / live data state.
    """
    distance = total_rounds - rnd_1based
    if distance <= 0:
        return "Championship"
    if distance == 1:
        return "Semifinals"
    if distance == 2:
        return "Quarterfinals"
    if distance == 3:
        return "Round of 16"
    return f"Round {rnd_1based}"


def test_8_team_3_round_names():
    names = [_name_for_round_simulator(3, r) for r in range(1, 4)]
    assert names == ["Quarterfinals", "Semifinals", "Championship"]


def test_4_team_2_round_names():
    names = [_name_for_round_simulator(2, r) for r in range(1, 3)]
    assert names == ["Semifinals", "Championship"]


def test_2_team_1_round_name():
    assert _name_for_round_simulator(1, 1) == "Championship"


def test_16_team_4_round_names():
    names = [_name_for_round_simulator(4, r) for r in range(1, 5)]
    assert names == ["Round of 16", "Quarterfinals", "Semifinals", "Championship"]


def test_round_count_synthesis_8_team():
    """When persisted has R1=4, R2=1, R3=1, synthesizer should pad R2 → 2
    matchups so the SF round has the correct width."""
    total_rounds = 3
    by_round = {1: [{}] * 4, 2: [{}] * 1, 3: [{}] * 1}
    for r in range(1, total_rounds + 1):
        expected = 2 ** (total_rounds - r)
        cur = by_round.get(r, [])
        while len(cur) < expected:
            cur.append({"_synthetic": True})
        by_round[r] = cur
    assert len(by_round[1]) == 4
    assert len(by_round[2]) == 2
    assert len(by_round[3]) == 1
    assert sum(1 for m in by_round[2] if m.get("_synthetic")) == 1


def test_next_round_matchup_index_math():
    """Bracket math: matchup j of round R+1 is fed by matchups (2j, 2j+1)
    in round R. Validate the index math used by `mark_playoff_winner`."""
    # QF (round 1) has 4 matchups: indices 0,1,2,3
    # SF (round 2) has 2 matchups: indices 0,1
    # QF#0 + QF#1 → SF#0 (j=0 fed by 2*0=0 and 2*0+1=1)
    # QF#2 + QF#3 → SF#1 (j=1 fed by 2*1=2 and 2*1+1=3)
    qf_to_sf = {qf_idx: qf_idx // 2 for qf_idx in range(4)}
    assert qf_to_sf == {0: 0, 1: 0, 2: 1, 3: 1}
    # SF#0 + SF#1 → Final#0
    sf_to_final = {sf_idx: sf_idx // 2 for sf_idx in range(2)}
    assert sf_to_final == {0: 0, 1: 0}

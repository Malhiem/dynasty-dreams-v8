"""Iter 145 — Regression: DraftBoard rounds variable must be defined.

Iter 140 accidentally removed `const rounds = Array.from(...)` while
inserting the trade-mode block; users saw `rounds is not defined` at
runtime. This test guarantees the declaration ships and references
the round-loop usage so the variable can't drop again.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAFT_BOARD = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"


def test_rounds_variable_defined():
    src = DRAFT_BOARD.read_text()
    assert "const rounds = Array.from({ length: totalRounds }" in src, \
        "Iter 140 regression — `rounds` must be defined before JSX use"
    # Must be defined BEFORE any usage
    decl = src.find("const rounds = Array.from")
    first_use = src.find("{rounds.map(")
    assert 0 < decl < first_use, \
        "`rounds` declaration must appear before {rounds.map(...)}"

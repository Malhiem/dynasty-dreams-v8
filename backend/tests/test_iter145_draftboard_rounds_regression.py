"""Iter 145 — Regression: DraftBoard rounds variable must be defined.

Iter 140 accidentally removed `const rounds = Array.from(...)` while
inserting the trade-mode block; users saw `rounds is not defined` at
runtime. This test guarantees the declaration ships and references
the round-loop usage so the variable can't drop again.
"""
from tests.source_tree import read_source
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAFT_BOARD = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"


def test_rounds_variable_defined():
    src = read_source(DRAFT_BOARD, include_imports=False)
    # The live grid now maps an inline round array using the selected draft's size.
    declaration = src.index("const totalRounds = Number(selectedDraft?.total_rounds) || totalRoundsDefault;")
    use = src.index("{Array.from({ length: totalRounds }, (_, i) => i + 1).map((round) => (")
    assert declaration < use
    assert "Rd {round}" in src[use:]

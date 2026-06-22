"""
Iter 198 — Frontend bracket vertical-centering invariant.

The classic single-elimination bracket layout requires every matchup in
round R+1 to be centered between the two feeding matchups of round R.
This is achieved by wrapping each matchup in a fixed-height slot that
doubles per round (`BRACKET_SLOT_H * 2^rdx`).

This pytest file is a guard against accidental regression of the
container styling — it greps the source for the slot-doubling formula
so future agents don't unwittingly switch back to `justify-around` +
`space-y-4` (which fights itself).
"""
from pathlib import Path


def _src() -> str:
    p = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lovable" / "pages" / "PlayoffBracket.tsx"
    return p.read_text()


def test_bracket_slot_height_constant_present():
    s = _src()
    assert "BRACKET_SLOT_H" in s, "BRACKET_SLOT_H constant missing — bracket centering will break"
    # Sanity: must be at least 140 to fit a 2-team card + score + mark buttons.
    # We accept any value >= 140 here.
    import re
    m = re.search(r"const\s+BRACKET_SLOT_H\s*=\s*(\d+)", s)
    assert m, "BRACKET_SLOT_H assignment not found"
    val = int(m.group(1))
    assert val >= 140, f"BRACKET_SLOT_H={val} is too small for the 2-team card layout"


def test_bracket_slot_height_doubles_per_round():
    """Each matchup wrapper must use `Math.pow(2, rdx)` (or `2 ** rdx`) so
    the slot height doubles per round — classic bracket centering."""
    s = _src()
    assert "Math.pow(2, rdx)" in s or "2 ** rdx" in s, (
        "Per-round slot doubling formula missing. Each round's slot height "
        "must be BRACKET_SLOT_H * 2^rdx to keep matchups centered."
    )


def test_old_justify_around_pattern_removed():
    """The previous (broken) layout used `space-y-4 justify-around flex
    flex-col` with a constant min-height. That combo fights itself and
    breaks centering. Make sure we don't accidentally re-introduce it."""
    s = _src()
    assert "space-y-4 justify-around" not in s, (
        "Old bracket layout pattern detected. Use the slot-doubling wrapper "
        "approach instead."
    )

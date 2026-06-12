"""
Iter 161 — DraftRoom.tsx TDZ regression test.

The previous structure declared a `useEffect` (line ~388) that depended on
`activeLeagueCtx?.id` *before* the `useActiveLeague()` hook (line 432) was
called — triggering a temporal-dead-zone error at runtime:

    can't access lexical declaration 'activeLeagueCtx' before initialization

This test guards against that ordering ever regressing.
"""
from pathlib import Path

DR = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


def test_use_active_league_called_before_first_use():
    src = DR.read_text()
    decl_pos = src.find("const { league: activeLeagueCtx")
    first_use = src.find("activeLeagueCtx?.id")
    assert decl_pos > 0, "useActiveLeague destructure should still exist"
    assert first_use > 0, "activeLeagueCtx?.id must be used somewhere"
    assert decl_pos < first_use, (
        f"useActiveLeague destructure (pos {decl_pos}) must come BEFORE "
        f"the first reference to activeLeagueCtx (pos {first_use}) to avoid the TDZ bug."
    )


def test_only_one_use_active_league_call():
    """Guards against the duplicate hook call that was introduced during the fix."""
    src = DR.read_text()
    assert src.count("const { league: activeLeagueCtx") == 1, (
        "useActiveLeague must be called exactly once in DraftRoom"
    )

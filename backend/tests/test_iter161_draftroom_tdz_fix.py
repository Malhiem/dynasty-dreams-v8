"""
Iter 161 — DraftRoom.tsx TDZ regression test.

The previous structure declared a `useEffect` (line ~388) that depended on
`activeLeagueCtx?.id` *before* the `useActiveLeague()` hook (line 432) was
called — triggering a temporal-dead-zone error at runtime:

    can't access lexical declaration 'activeLeagueCtx' before initialization

This test guards against that ordering ever regressing.
"""
from pathlib import Path

# Iter 171 — DraftRoom.tsx was split into sub-components. Resolve the legacy
# "read the entire draft room source" pattern as the concatenation of the
# parent + extracted draftroom/* files so existing grep-style assertions
# keep working without rewriting every spec.
def _iter171_draftroom_concat() -> str:
    from pathlib import Path as _P
    paths = [
        _P("/app/frontend/src/lovable/pages/DraftRoom.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/draftConstants.ts"),
    ]
    return chr(10).join(p.read_text() for p in paths if p.exists())


class _Iter171DraftRoomShim:
    def read_text(self, *a, **kw) -> str:
        return _iter171_draftroom_concat()


def _iter171_install_shim_after_imports():
    pass


DR = _Iter171DraftRoomShim()


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

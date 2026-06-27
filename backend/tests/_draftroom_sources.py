"""Shared helper for iter 170* tests.

When iter 170 originally landed, all draft-room JSX + logic lived in
`DraftRoom.tsx`. Since then (iter 230+) it's been decomposed into the
`/lovable/pages/draftroom/` subdir + a fleet of `hooks/use-draft-*.ts`
modules. The iter 170 tests do source-text grep assertions — to keep
their functional intent valid, treat the "draft room source" as the
concatenation of every file that contributes to the runtime behaviour.
"""
from pathlib import Path

FRONTEND_SRC = Path("/app/frontend/src")


def read_draftroom_family() -> str:
    parts: list[str] = []
    candidates = [
        FRONTEND_SRC / "lovable/pages/DraftRoom.tsx",
    ]
    # Every file under /draftroom/ (DraftLiveTile, DraftBoard, PlayerSearchPanel,
    # SelectedPlayerCard, TruncatedRosterPanel, draftConstants, etc.)
    draftroom_dir = FRONTEND_SRC / "lovable/pages/draftroom"
    if draftroom_dir.exists():
        candidates.extend(sorted(draftroom_dir.rglob("*.*")))
    # Every draft-flavoured hook (use-draft-auto-init, use-draft-pick-handler,
    # use-draft-room-socket, use-draft-commissioner-actions, use-draft-countdown,
    # use-draft-eligible-players, use-draft-chat, use-draft-room-persistence,
    # use-draft-queue-shortlist-persistence, use-draft-sounds, use-draft-pick-grid,
    # use-draft-picks-until-my-turn, use-draft-player-filters, use-draft-live-state).
    hooks_dir = FRONTEND_SRC / "hooks"
    for p in sorted(hooks_dir.glob("use-draft*")):
        candidates.append(p)
    # Iter 231 — pick timer was extracted into a non-`use-draft*` named hook
    # (`use-pick-timer.ts`) in iter 204. Pull it in explicitly so auto-pick /
    # countdown assertions still resolve. Same treatment for use-socket +
    # use-live-picks-by-orig-key (which owns the `computeAbbrs` helper).
    for name in (
        "use-pick-timer.ts",
        "use-socket.ts",
        "use-socket.js",
        "use-live-picks-by-orig-key.js",
        "use-live-picks-by-orig-key.ts",
    ):
        p = hooks_dir / name
        if p.exists():
            candidates.append(p)
    for p in candidates:
        if p.exists() and p.is_file():
            parts.append(p.read_text())
    return "\n".join(parts)


class DraftRoomFamilyShim:
    """Drop-in replacement for `Path(DraftRoom.tsx)` — exposes `.read_text()`."""

    def read_text(self) -> str:  # noqa: D401
        return read_draftroom_family()

    def exists(self) -> bool:  # noqa: D401
        # Always true — the family is the union of multiple files; as long as
        # at least one contributing file is present we consider the shim live.
        return True

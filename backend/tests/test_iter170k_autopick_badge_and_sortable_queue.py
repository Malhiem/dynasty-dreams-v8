"""Iter 170k — Visual auto-pick badge + drag-to-reorder Queue UI.

Frontend changes:
  (1) Pick tiles render a small clock pip with a tooltip when
      `pick.auto_picked` is true. Tooltip distinguishes the resolution
      ("queue" vs "top-ranked eligible").
  (2) Picks state now carries `auto_picked` + `auto_pick_via` (hydrated
      from backend on every refresh + the initial auto-init).
  (3) New `SortableQueue` component (built on @dnd-kit/sortable) lets
      managers drag-and-drop rows to set auto-pick fallback order.
      Reorder calls back into the parent which mutates `queue` state →
      debounced `PUT /teams/{id}/draft-queue` persists.
"""
from pathlib import Path

# Iter 171 — DraftRoom.tsx parent was refactored. Draft Live tile + Draft Board
# JSX now live in /draftroom/DraftLiveTile.tsx + DraftBoard.tsx. We treat
# `DRAFT_ROOM.read_text()` as the concatenation of the parent and the
# extracted subcomponents so existing grep-style assertions keep passing.
def _read_draftroom_family() -> str:
    from pathlib import Path as _P
    paths = [
        _P("/app/frontend/src/lovable/pages/DraftRoom.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/draftConstants.ts"),
    ]
    return chr(10).join(p.read_text() for p in paths if p.exists())


class _DraftRoomShim:
    def read_text(self) -> str:
        return _read_draftroom_family()


DRAFT_ROOM = _DraftRoomShim()
SORTABLE_QUEUE = Path("/app/frontend/src/lovable/pages/draftroom/SortableQueue.tsx")


def test_auto_pick_badge_present_on_tile():
    src = DRAFT_ROOM.read_text()
    # Conditional render on auto_picked, with a stable testid keyed by
    # overall so QA can grab the badge per-pick.
    # Iter 171 — tile JSX moved to DraftBoard.tsx (which has @ts-nocheck
    # so the cast was dropped); accept either form.
    assert "(pick as any).auto_picked" in src or "pick.auto_picked" in src
    assert 'data-testid={`draft-board-auto-pick-${pick.overall}`}' in src
    # Tooltip explains the resolution (queue vs top eligible).
    assert "Auto-picked on timeout" in src
    assert (
        '(pick as any).auto_pick_via === "queue"' in src
        or 'pick.auto_pick_via === "queue"' in src
    )
    # Uses the existing Clock icon (already imported from lucide).
    assert "<Clock className=\"h-2.5 w-2.5\"" in src


def test_picks_hydration_carries_auto_pick_metadata():
    src = DRAFT_ROOM.read_text()
    # Both hydration paths (initial auto-init + refresh after backend
    # write + post-pick refetch) must carry the auto-pick metadata so
    # the badge survives across reloads/socket events.
    assert src.count("auto_picked: !!p.auto_picked") >= 3
    assert src.count("auto_pick_via: p.auto_pick_via") >= 3


def test_sortable_queue_component_present():
    src = SORTABLE_QUEUE.read_text()
    # Built on @dnd-kit primitives.
    assert 'from "@dnd-kit/core"' in src
    assert 'from "@dnd-kit/sortable"' in src
    # Vertical strategy + closest-center collision detection.
    assert "verticalListSortingStrategy" in src
    assert "closestCenter" in src
    # PointerSensor with 4px activation so a click doesn't accidentally
    # drag.
    assert "activationConstraint: { distance: 4 }" in src
    # arrayMove drives the reorder + parent callback gets the new id
    # list (parent does the state set + debounced PUT).
    assert "onReorder(arrayMove(ids, oldIdx, newIdx))" in src


def test_sortable_queue_renders_drag_handles_and_remove():
    src = SORTABLE_QUEUE.read_text()
    # Per-row handle testid + remove testid.
    assert 'data-testid={`draft-room-queue-handle-${player.id}`}' in src
    assert 'data-testid={`draft-room-queue-remove-${player.id}`}' in src
    # Container testid for the sortable list.
    assert 'data-testid="draft-room-sortable-queue"' in src


def test_draftroom_uses_sortable_queue():
    src = DRAFT_ROOM.read_text()
    assert 'import SortableQueue from "@/lovable/pages/draftroom/SortableQueue"' in src
    # Renders inside the existing Queue tab and wires reorder + remove.
    assert "<SortableQueue" in src
    assert "onReorder={(orderedIds) => setQueue(orderedIds)}" in src
    assert "onRemove={(id) => removeFromQueue(id)}" in src

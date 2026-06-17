"""Iter 170n — Chat outbound persistence + Quick Promote + Criteria fix.

  (1) Outbound chat: DraftRoom's `handleSendChat` now POSTs to the
      existing `/drafts/{id}/chat` when a backend draft is present,
      so every connected manager + a reload all see the message.
      Local optimistic append remains for pre-init / demo mode.
  (2) Quick Promote: SortableQueue gained optional `onPromote` +
      `isPromoted` props. DraftRoom wires them on the Shortlist tab so
      a small ⤴ icon copies a shortlisted player into the auto-pick
      queue in one click (clean two-stage workflow).
  (3) Criteria fix: investigation showed the players collection holds
      only NHL-active skaters/goalies (no prospect pool). The
      auto-init default flipped from "entry" → "open" so the metadata
      reflects what the data supports. A surfaced badge on the Draft
      Live tile (`draft-room-criteria-badge`) makes the format visible.
"""
from pathlib import Path

DRAFTS_ROUTE = Path("/app/backend/routes/drafts.py")
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


def test_auto_init_default_criteria_is_open():
    src = DRAFTS_ROUTE.read_text()
    # The old "entry" default is gone — the player pool is NHL-only
    # so "open" is the honest default.
    block = src.split("async def auto_init_draft")[1].split("# ─── Iter 170h")[0]
    assert '"player_criteria": "open"' in block
    assert '"player_criteria": "entry"' not in block


def test_chat_send_round_trips_through_backend():
    src = DRAFT_ROOM.read_text()
    # When a backend draft exists, POST to /drafts/{id}/chat instead of
    # doing a local-only append (the WS subscription seeds the message
    # back into chatMessages for the sender too).
    assert "api.post(`/drafts/${currentDraft._id}/chat`, { text })" in src
    # Fallback path still appends locally on POST failure / no draft.
    assert "Iter 170n — Persist outbound chat" in src


def test_sortable_queue_optional_promote_affordance():
    src = SORTABLE_QUEUE.read_text()
    # New props are optional so the existing Queue-tab usage doesn't
    # surface the promote button.
    assert "onPromote?: (id: string) => void" in src
    assert "isPromoted?: (id: string) => boolean" in src
    # Row renders the ⤴ button only when `onPromote` is supplied,
    # disabled state when already promoted, with a stable testid.
    assert "{onPromote && (" in src
    assert 'data-testid={`draft-room-queue-promote-${player.id}`}' in src
    assert "disabled={isPromoted?.(String(player.id))}" in src


def test_shortlist_tab_wires_promote_to_queue():
    src = DRAFT_ROOM.read_text()
    block = src.split('<TabsContent value="shortlist"')[1].split("</TabsContent>")[0]
    # Shortlist tab passes promote handler that pushes the id onto the
    # queue (deduped), with `isPromoted` resolving against `queue`.
    assert "onPromote={(id) => {" in block
    assert "if (!queue.includes(id)) setQueue((prev) => [...prev, id])" in block
    assert "isPromoted={(id) => queue.includes(id)}" in block
    assert 'promoteLabel="Promote to auto-pick queue"' in block


def test_draft_live_tile_shows_criteria_badge():
    src = DRAFT_ROOM.read_text()
    # Surfaced from currentDraft.player_criteria so the manager can
    # see what pool the eligible list is drawn from.
    assert 'data-testid="draft-room-criteria-badge"' in src
    assert 'Open · all eligible NHL players' in src
    assert 'Entry / Rookies' in src

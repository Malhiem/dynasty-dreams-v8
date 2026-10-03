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

from tests._drafts_route_sources import DraftsRouteFamilyShim
DRAFTS_ROUTE = DraftsRouteFamilyShim()
# Iter 231 — DraftRoom.tsx + draftroom/* + hooks/use-draft-* have been
# decomposed across many iterations. The DraftRoomFamilyShim concatenates
# every file that contributes to the runtime draft room behaviour so the
# original grep-style assertions still resolve.
from tests._draftroom_sources import DraftRoomFamilyShim

DRAFT_ROOM = DraftRoomFamilyShim()
SORTABLE_QUEUE = Path("/app/frontend/src/lovable/pages/draftroom/SortableQueue.tsx")


def test_auto_init_default_criteria_is_open():
    src = DRAFTS_ROUTE.read_text()
    # Iter 231 — split marker loosened (no longer pins on iter-170h).
    block = src.split("async def auto_init_draft")[1].split("\n@router.")[0]
    assert '"player_criteria": "open"' in block
    # Auto-init MUST NOT default new drafts to "entry" — the players
    # collection holds only NHL-active skaters / goalies.
    assert '"player_criteria": "entry"' not in block


def test_chat_send_round_trips_through_backend():
    src = DRAFT_ROOM.read_text()
    # Iter 231 — outbound chat moved into use-draft-chat hook. Variable
    # renamed `currentDraft._id` → `currentDraftId`. Functional intent
    # (POST to /drafts/{id}/chat when a backend draft exists) preserved.
    assert "api.post(`/drafts/${currentDraftId}/chat`, { text })" in src


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

"""Iter 170l — Drag-to-reorder Shortlist + Auto-pick badge in chat panel.

  (1) Shortlist refactored from Set<string> → ordered string[] so it
      can be drag-reordered using the same SortableQueue component.
      `shortlistedPlayers` memo now preserves the manager's manual
      ranking (was sorted by global ranking before).
  (2) DraftChatPanel's `ChatBubble` adds a small clock pip next to the
      sender label on auto-pick rows. Detection uses the explicit
      `auto_picked` meta field (now also stamped on the backend chat
      message), with a tolerant text-sniff fallback for older msgs.
"""
from pathlib import Path

# Iter 231 — DraftRoom.tsx + draftroom/* + hooks/use-draft-* have been
# decomposed across many iterations. The DraftRoomFamilyShim concatenates
# every file that contributes to the runtime draft room behaviour so the
# original grep-style assertions still resolve.
from tests._draftroom_sources import DraftRoomFamilyShim

DRAFT_ROOM = DraftRoomFamilyShim()
CHAT_PANEL = Path("/app/frontend/src/lovable/pages/draftroom/DraftChatPanel.tsx")
DRAFTS_ROUTE = Path("/app/backend/routes/drafts.py")


def test_shortlist_is_ordered_array_and_uses_includes():
    src = DRAFT_ROOM.read_text()
    # Iter 170l — string[] (not Set).
    assert "useState<string[]>([])" in src
    # All has-checks rewritten to includes-checks.
    assert "shortlist.has(" not in src
    # toggleShortlist mutates as a list (push / filter).
    assert "prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]" in src


def test_shortlist_renders_in_sortable_queue():
    src = DRAFT_ROOM.read_text()
    block = src.split('<TabsContent value="shortlist"')[1].split("</TabsContent>")[0]
    # SortableQueue is used with shortlist-specific wiring.
    assert "<SortableQueue" in block
    assert "onReorder={(orderedIds) => setShortlist(orderedIds)}" in block
    assert "onRemove={(id) => toggleShortlist(id)}" in block


def test_shortlisted_players_preserves_drag_order():
    src = DRAFT_ROOM.read_text()
    block = src.split("const shortlistedPlayers = useMemo")[1].split("}, [players, shortlist]);")[0]
    # Order driven by the shortlist array (manager's drag rank), not
    # by a `players.filter` (which would re-sort by ranking).
    assert "shortlist" in block
    assert "shortlist\n      .map((id) => players.find((p) => p.id === id))" in block


def test_chat_panel_renders_auto_pick_badge():
    src = CHAT_PANEL.read_text()
    # Detection — accepts explicit meta + tolerant text sniff.
    assert "msg.auto_picked || /auto.pick/i.test(msg.text || \"\")" in src
    # Testid for QA grab.
    assert "draft-chat-auto-pick-" in src
    # Clock icon rendered with sky-tinted badge.
    assert "<Clock className=\"h-2 w-2\"" in src


def test_backend_autopick_chat_carries_meta():
    # Iter 231n — chat meta moved to `routes/draft_helpers.py` along
    # with the rest of the auto-pick logic. Anchor on the new module.
    from pathlib import Path
    helpers_src = Path("/app/backend/routes/draft_helpers.py").read_text()
    block = helpers_src.split("async def perform_one_auto_pick")[1]
    # The system chat msg now carries `auto_picked: True` + the via
    # tag so the frontend doesn't need to sniff free text.
    assert '"auto_picked": True' in block
    assert '"auto_pick_via": via' in block

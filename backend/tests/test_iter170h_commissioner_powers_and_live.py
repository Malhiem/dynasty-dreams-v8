"""Iter 170h — Commissioner draft powers + roster live refresh + WebSocket.

Backend changes:
  (1) `POST /drafts/{id}/undo` — undo the last N picks. Commissioner-only.
      Pops picks, decrements current_pick, pulls drafted players off
      their team's roster, broadcasts `draft_undo` + a system chat msg.
  (2) `PATCH /drafts/{id}/picks/{overall}` — swap a drafted player.
      Commissioner-only. Removes old player from roster, adds new one,
      rejects already-drafted replacements, broadcasts
      `draft_pick_swapped` + a chat msg.

Frontend changes:
  (3) TruncatedRosterPanel takes a `reloadTrigger` prop; DraftRoom
      bumps `rosterReloadTick` on each successful pick so My Roster
      refetches without a full page reload.
  (4) SelectedPlayerCard takes a `canPick` prop that hides the Draft
      Player button when the user can't legally pick (not commissioner
      AND not their team on the clock).
  (5) Live Socket.IO subscription to the `draft_{id}` room — every
      pick/undo/swap broadcast refreshes the draft state on all
      connected managers (no polling).
  (6) Commissioner-only "Undo Last Pick" button in the Draft Live tile.
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
SELECTED_CARD = Path("/app/frontend/src/lovable/pages/draftroom/SelectedPlayerCard.tsx")
ROSTER_PANEL = Path("/app/frontend/src/lovable/pages/draftroom/TruncatedRosterPanel.tsx")


# ─── Backend ──────────────────────────────────────────────────────────


def test_undo_endpoint_present_with_validation():
    src = DRAFTS_ROUTE.read_text()
    assert '@router.post("/drafts/{draft_id}/undo")' in src
    assert "class UndoDraftPicksRequest(BaseModel):" in src
    # count: 1..50
    assert "count: int = Field(default=1, ge=1, le=50" in src


def test_undo_commissioner_only_and_pulls_roster():
    src = DRAFTS_ROUTE.read_text()
    block = src.split("async def undo_draft_picks")[1].split("class SwapPickPlayerRequest")[0]
    # Commissioner gate
    assert 'league["commissioner_id"] != user["_id"]' in block
    # Pulls drafted players off the picking team's roster.
    assert '"$pull": {"roster": pid}' in block
    # Broadcasts an undo event + system chat.
    assert '"draft_undo"' in block
    assert '"draft_chat"' in block


def test_swap_pick_endpoint_present_and_pulls_old_adds_new():
    src = DRAFTS_ROUTE.read_text()
    assert '@router.patch("/drafts/{draft_id}/picks/{overall}")' in src
    block = src.split("async def swap_pick_player")[1].split("async def pause_draft")[0]
    # Commissioner gate
    assert 'league["commissioner_id"] != user["_id"]' in block
    # Reject if the replacement is already drafted elsewhere.
    assert "already drafted on another pick" in block
    # Pull old + add new on the roster.
    assert '"$pull": {"roster": old_player_id}' in block
    assert '"$addToSet": {"roster": str(new_player["_id"])}' in block
    # Broadcasts a swap event + chat.
    assert '"draft_pick_swapped"' in block
    assert '"draft_chat"' in block


# ─── Frontend ─────────────────────────────────────────────────────────


def test_draftroom_uses_socket_for_live_updates():
    src = DRAFT_ROOM.read_text()
    assert 'import { useSocket } from "@/hooks/use-socket";' in src
    # Subscribes to the `draft_{id}` room when a draft exists.
    assert "const draftRoomId = currentDraft?._id ? `draft_${currentDraft._id}` : null;" in src
    # Listens for the three draft events backend broadcasts.
    for evt in ("draft_pick", "draft_undo", "draft_pick_swapped", "draft_chat"):
        assert evt in src


def test_draftroom_refresh_helper_bumps_roster_tick():
    src = DRAFT_ROOM.read_text()
    block = src.split("const refreshDraftState =")[1].split("// Iter 170h — Subscribe")[0]
    # Refetch GETs the canonical draft + bumps the roster reload tick.
    assert "api.get(`/drafts/${currentDraft._id}`)" in block
    assert "setRosterReloadTick((t) => t + 1)" in block


def test_draftroom_passes_canpick_and_roster_tick():
    src = DRAFT_ROOM.read_text()
    # SelectedPlayerCard receives canPick.
    assert "canPick={canPickForCurrentTurn}" in src
    # TruncatedRosterPanel receives reloadTrigger.
    assert "reloadTrigger={rosterReloadTick}" in src
    # Commissioner check considers co-commissioners too.
    assert "activeLeagueCtx.co_commissioners.includes(userId)" in src


def test_undo_button_renders_and_calls_handler():
    src = DRAFT_ROOM.read_text()
    assert 'data-testid="draft-room-undo-pick"' in src
    # Iter 170i — handler is invoked with the user-chosen count, not a
    # hardcoded 1.
    assert "handleUndoPicks(undoCount)" in src
    # Handler POSTs to /drafts/{id}/undo when backend draft exists.
    assert "/drafts/${currentDraft._id}/undo`" in src
    # And swap handler PATCHes the specific pick.
    assert "/drafts/${currentDraft._id}/picks/${overall}`" in src


def test_selected_card_canpick_gate():
    src = SELECTED_CARD.read_text()
    # New prop with default true (Storybook backward compat).
    assert "canPick = true," in src
    # Button is gated by canPick.
    assert "{canPick && (" in src


def test_truncated_roster_panel_supports_reload_trigger():
    src = ROSTER_PANEL.read_text()
    assert "reloadTrigger = 0" in src
    # Dep array of the fetch effect must include reloadTrigger.
    assert "}, [selectedTeamId, statFilter, reloadTrigger]);" in src

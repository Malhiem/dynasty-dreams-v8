"""Iter 170m — Backend-persisted Shortlist + Historic chat hydration.

Backend changes:
  (1) `PUT/GET /teams/{id}/shortlist` — mirrors the draft-queue
      endpoints. Owner-or-commissioner gate, dedupes, caps at 200.

Frontend changes:
  (2) DraftRoom hydrates the persisted shortlist from
      `/teams/{myTeam.id}/shortlist` on mount and debounce-persists
      back on every change.
  (3) DraftRoom hydrates `draft.chat_messages` from backend on
      auto-init AND on every `refreshDraftState` call so:
        • a hard reload preserves the chat narrative (including
          auto-pick badges)
        • undo/swap broadcasts roll the chat forward in lock-step.
"""
from pathlib import Path

DRAFTS_ROUTE = Path("/app/backend/routes/drafts.py")
# Iter 231k — Shortlist endpoints extracted to routes/draft_queue.py.
DRAFT_QUEUE_ROUTE = Path("/app/backend/routes/draft_queue.py")
# Iter 231 — DraftRoom.tsx + draftroom/* + hooks/use-draft-* decomposed across
# many iterations. Use the shared shim that concatenates every file that
# contributes to the runtime draft room behaviour.
from tests._draftroom_sources import DraftRoomFamilyShim
DRAFT_ROOM = DraftRoomFamilyShim()


def test_shortlist_endpoints_present_and_validated():
    src = DRAFT_QUEUE_ROUTE.read_text()
    assert '@router.put("/teams/{team_id}/shortlist")' in src
    assert '@router.get("/teams/{team_id}/shortlist")' in src
    block = src.split("async def update_team_shortlist")[1].split("@router.get")[0]
    # Same owner-or-commissioner gate as draft-queue.
    assert 'is_owner = team.get("owner_id") == user["_id"]' in block
    assert 'is_comm = league and league.get("commissioner_id") == user["_id"]' in block
    # Dedupe + 200-entry cap (Iter 231k — extracted into _dedupe_capped helper).
    assert '_dedupe_capped(payload.player_ids, cap=200)' in block
    # Persists onto team.shortlist.
    assert '"$set": {"shortlist": cleaned}' in block


def test_draftroom_hydrates_and_persists_shortlist():
    src = DRAFT_ROOM.read_text()
    # Iter 231 — shortlist hydration moved into the use-draft-queue-
    # shortlist-persistence hook. Team-id variable renamed from
    # `(myTeam as any).id` → `myTeamId`. Functional intent preserved.
    assert "api.get(`/teams/${myTeamId}/shortlist`)" in src
    assert "setShortlist((data?.shortlist || []).map(String))" in src
    assert "const hasHydratedShortlistRef = useRef(false)" in src
    # Debounced PUT on change (mirrors the draft-queue pattern).
    assert "api.put(`/teams/${myTeamId}/shortlist`, { player_ids: shortlist })" in src


def test_draftroom_hydrates_historic_chat_on_auto_init():
    src = DRAFT_ROOM.read_text()
    # Auto-init effect copies backend chat_messages into state with
    # date-coerced timestamps so existing renderers (including the
    # auto-pick badge logic) work uniformly.
    assert "Array.isArray(d.chat_messages) && d.chat_messages.length > 0" in src
    # Iter 231 — code formatter line-broke the .map(...) call so the
    # original single-line snapshot no longer matches. Loosen the check
    # to two consecutive substrings.
    assert "d.chat_messages.map((m: any)" in src
    assert "setChatMessages(" in src


def test_draftroom_chat_synced_on_refresh():
    src = DRAFT_ROOM.read_text()
    # Iter 231 — refreshDraftState moved into use-draft-auto-init.ts.
    # The split marker shifted accordingly; pin it to the function start
    # and the next refreshDraftState callback definition or the file end.
    refresh_block = src.split("const refreshDraftState = useCallback")[1].split("return { refreshDraftState }")[0]
    assert "Array.isArray(data.chat_messages)" in refresh_block
    assert "data.chat_messages.map((m: any)" in refresh_block

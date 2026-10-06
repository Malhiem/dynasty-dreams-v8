"""Iter 170f — Draft Room v3 polish from user feedback:

  (1) Player tile updates on pick — clicking Draft Player on the
      SelectedPlayerCard now actually advances the draft via the
      unified `handleDraftPlayer` handler (used by Simulate Pick too).
  (2) Tile defaults to last drafted player (Live View · Last Pick).
      A small "Live View" button shows when the user previews a
      different card; clicking reverts to default.
  (3) localStorage-backed persistence keyed by active league id so the
      draft state survives page reloads. (Real backend wiring to
      POST /api/drafts/{id}/pick remains queued as P3.)
"""
from pathlib import Path

# Iter 231 — DraftRoom.tsx + draftroom/* + hooks/use-draft-* decomposed across
# many iterations. Use the shared shim that concatenates every file that
# contributes to the runtime draft room behaviour.
from tests._draftroom_sources import DraftRoomFamilyShim
DRAFT_ROOM = DraftRoomFamilyShim()
SEED_SCRIPT = Path("/app/backend/scripts/iter170f_seed_pick_trade.py")


def _src() -> str:
    return DRAFT_ROOM.read_text()


def test_unified_draft_handler_replaces_old_simulate():
    src = _src()
    # Iter 229h — handler was extracted into useDraftPickHandler (useCallback wrapper).
    assert "const handleDraftPlayer = useCallback(async (chosen?: DraftEligiblePlayer | null, destination?: string) => {" in src
    # Old name kept as a thin alias so the Simulate Pick button binding stays.
    assert "const handleSimulatePick = useCallback(() => { handleDraftPlayer(); }" in src


def test_on_draft_player_actually_picks():
    src = _src()
    # The SelectedPlayerCard's onDraftPlayer callback must call
    # handleDraftPlayer with the player so the click on Draft Player
    # actually progresses the draft.
    assert "handleDraftPlayer(p as DraftEligiblePlayer)" in src


def test_last_picked_player_state_present():
    src = _src()
    assert "const [lastPickedPlayerId, setLastPickedPlayerId] = useState<string | null>" in src
    # Handler must update lastPickedPlayerId on each pick.
    assert "setLastPickedPlayerId(String(nextPlayer.id))" in src


def test_live_view_button_renders_and_reverts():
    src = _src()
    assert 'data-testid="draft-room-live-view-btn"' in src
    # Default preview tile reads lastPickedPlayerId when selectedPlayerId is null.
    assert "const previewId = selectedPlayerId ?? lastPickedPlayerId" in src
    # Clicking the Live View button clears the manual selection.
    assert "onClick={() => setSelectedPlayerId(null)}" in src


def test_persistence_to_localstorage_keyed_by_league():
    src = _src()
    # Iter 231 — storage key still namespaces by league id, but the
    # variable name changed from `activeLeagueCtx.id` → `leagueId` when
    # persistence moved into the use-draft-room-persistence hook.
    assert "draftroom-state-v1:${leagueId}" in src
    # Hydration + persist effects both present.
    assert "localStorage.getItem(draftStorageKey)" in src
    assert "localStorage.setItem(" in src
    # Persists the 4 state slices the user needs to recover on reload.
    assert "picks," in src
    assert "currentPick: draftConfig.currentPick" in src
    assert "draftStarted: draftConfig.draftStarted" in src
    assert "lastPickedPlayerId," in src


def test_persistence_hydration_marks_players_drafted():
    src = _src()
    # On hydration, the eligible-list `drafted` flag must be flipped
    # for any player id that appears in the saved picks so the list
    # doesn't immediately re-pick them on the next Simulate Pick.
    assert "const draftedIds = new Set(" in src
    assert "draftedIds.has(String(p.id))" in src


def test_seed_pick_trade_script_is_idempotent_and_records_trade():
    src = SEED_SCRIPT.read_text()
    # Idempotency guard
    assert 'pick_a.get("current_team_id") != zarek_id' in src
    assert 'pick_b.get("current_team_id") != ice_id' in src
    # Updates both picks' current_team_id + appends trade_history entries.
    assert 'current_team_id' in src and 'trade_history' in src
    # Records an executed trade so Transactions page reflects it.
    assert '"status": "accepted"' in src
    assert '"asset_type": "pick"' in src

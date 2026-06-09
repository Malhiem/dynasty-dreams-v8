"""Iter 140 — Three user-requested polish items.

Coverage
--------
1. CommissionerSettings → Draft tab renames the card to "Create a Draft"
   AND embeds the DraftOrderConfigCard BELOW the Draft Type selector.
2. DraftOrderConfigCard supports `embedded` mode (skips its own Card
   shell so it renders inline inside the parent card).
3. Backend socket presence wiring: emits `presence_state` on join and
   `user_left` on disconnect / leave so the frontend can paint online
   indicators.
4. useDraftSocket exposes `onlineUserIds` populated from the three
   presence events.
5. DraftRoom paints a green outline + dot when a team's owner is
   currently in the room, regardless of on-clock state, and uses gold
   (instead of cyan) when on the clock.
6. DraftBoard has a "Propose Trade" toggle in the header that, when
   active, surfaces a per-pick trade button (`draft-board-pick-trade-…`)
   wired into the existing TradeBuilder context.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
CARD = REPO / "frontend/src/lovable/pages/commissioner/DraftOrderConfigCard.tsx"
SERVER = REPO / "backend/server.py"
SOCKET = REPO / "frontend/src/hooks/use-socket.js"
DRAFT_ROOM = REPO / "frontend/src/pages/DraftRoomPage.jsx"
DRAFT_BOARD = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"


# ── 1. League Admin → Draft tab now renders "Create a Draft" ───
def test_admin_renames_to_create_a_draft():
    src = ADMIN.read_text()
    draft_tab_idx = src.find('TabsContent value="draft"')
    assert draft_tab_idx > 0
    block = src[draft_tab_idx:draft_tab_idx + 8000]
    assert "<CardTitle>Create a Draft</CardTitle>" in block, "Title must be 'Create a Draft'"
    # DraftOrderConfigCard is inside the Create a Draft card AFTER the Draft Type select
    type_pos = block.find("First-Time Team Draft")  # inside the Select
    config_pos = block.find("<DraftOrderConfigCard")
    assert 0 < type_pos < config_pos, \
        "DraftOrderConfigCard must render BELOW the Draft Type selector"
    # Embedded prop
    assert "embedded={true}" in block, "Card must render in embedded mode inside the parent card"


# ── 2. Card supports embedded mode ─────────────────────────────
def test_config_card_embedded_mode():
    src = CARD.read_text()
    assert "embedded?: boolean" in src, "Embedded prop type missing"
    assert "if (embedded)" in src, "Embedded short-circuit missing"
    assert "Draft Order &amp; Schedule" in src, "Inner Label still rendered"


# ── 3. Backend emits presence_state + user_left ────────────────
def test_backend_presence_events():
    src = SERVER.read_text()
    assert "'presence_state'" in src, "presence_state emit missing"
    assert "'user_left'" in src, "user_left emit missing"
    # presence_state goes ONLY to the joining sid
    assert "to=sid" in src, "presence_state should target the joining sid"


# ── 4. useDraftSocket exposes onlineUserIds ────────────────────
def test_use_draft_socket_presence():
    src = SOCKET.read_text()
    assert "onlineUserIds" in src, "Presence Set missing"
    assert "presence_state" in src, "Handler missing"
    assert "user_left" in src, "user_left handler missing"


# ── 5. DraftRoom paints green online outline + gold on-clock ───
def test_draft_room_online_outline():
    src = DRAFT_ROOM.read_text()
    assert "onlineUserIds" in src, "Online presence not consumed in DraftRoom"
    assert "ownerOnline" in src, "Per-team online flag missing"
    # Green outline class
    assert "border-[#34C759]" in src, "Green outline class missing"
    # Gold (#FFD700) replaces the prior cyan on-clock highlight
    assert "#FFD700" in src, "On-clock gold colour missing"
    # Testids for QA
    assert "draft-team-header-${abbr}" in src, "Per-team header testid missing"
    assert "draft-team-online-dot-${abbr}" in src, "Online dot testid missing"


# ── 6. DraftBoard trade toggle + per-pick trade buttons ────────
def test_draft_board_trade_toggle_and_buttons():
    src = DRAFT_BOARD.read_text()
    assert 'data-testid="draft-board-trade-toggle"' in src, "Trade toggle button missing"
    assert "tradeMode" in src, "Trade-mode state missing"
    assert "handleAddPickToTrade" in src, "Trade handler missing"
    assert "useTradeBuilder" in src, "TradeBuilder context not consumed"
    # Per-pick buttons rendered conditionally on tradeMode
    assert "draft-board-pick-trade-${team.abbr}-r${round}" in src, \
        "Per-pick trade button testid missing"
    # Toggle uses emerald visual when ON
    assert "Trade Mode: ON" in src, "On-state label missing"

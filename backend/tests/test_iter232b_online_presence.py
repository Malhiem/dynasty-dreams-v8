"""Iter 232b — Online presence indicators in Draft Room + League Chat.

User: "Create an online status in the draft room but also in the
league chat so we can see at a quick glance who might be currently
online."

Implementation reuses the existing Socket.IO `presence_state` /
`user_joined` / `user_left` events the server already emits on every
connect / join / leave (see backend/server.py iter 140 wiring).
No new endpoints, no polling, no separate "presence" collection —
the source of truth is whoever currently has a live websocket in the
room.

  • `OnlinePresenceBadge` — count pill rendered next to the section
    title ("X in room" for the draft, "X online" for the league
    chat). Pulsing green dot.
  • `OnlineDot` — per-user dot. Used next to each chat message
    author so users see at a glance who is around to respond.

Both built so they no-op (return null / fall back to grey) when the
underlying `Set<string>` is empty, so layouts never jump on first
render.
"""
from pathlib import Path


BADGE = Path("/app/frontend/src/components/OnlinePresenceBadge.tsx")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
DRAFT_SOCKET = Path("/app/frontend/src/hooks/use-draft-room-socket.ts")
CHAT = Path("/app/frontend/src/lovable/pages/Chat.tsx")
SOCKET_LIB = Path("/app/frontend/src/hooks/use-socket.js")


def test_presence_badge_component_exists():
    src = BADGE.read_text()
    # Exports both pieces (pill + per-user dot).
    assert "export function OnlinePresenceBadge(" in src
    assert "export function OnlineDot(" in src
    # Renders nothing when the underlying set is empty so the layout
    # never jumps.
    assert "if (count <= 0) return null;" in src
    # Pulsing dot signals liveness without being noisy.
    assert "animate-ping" in src
    # data-testid hooks for Playwright.
    assert 'data-testid={`online-presence-badge' in src
    assert 'data-online' in src


def test_draft_room_socket_hook_tracks_presence():
    src = DRAFT_SOCKET.read_text()
    # The hook now owns a `onlineUserIds` Set<string>.
    assert "useState<Set<string>>" in src
    # Three socket events feed it.
    assert "presence_state:" in src
    assert "user_joined:" in src
    assert "user_left:" in src
    # Hook returns the set so the page can render the badge.
    assert "return { lastChatEvent, setLastChatEvent, onlineUserIds };" in src
    # Reset on room change so we don't carry stale "online" markers
    # between drafts / leagues.
    assert "setOnlineUserIds(new Set());" in src


def test_draft_room_page_renders_presence_badge():
    src = DRAFT_ROOM.read_text()
    # Import.
    assert 'import { OnlinePresenceBadge } from "@/components/OnlinePresenceBadge"' in src
    # Hook returns the set + the page renders the badge.
    assert "onlineUserIds" in src
    assert "OnlinePresenceBadge" in src
    # "in room" copy reads naturally inside a draft.
    assert 'label="in room"' in src


def test_use_league_socket_tracks_presence():
    src = SOCKET_LIB.read_text()
    # Same presence wiring as the draft-room hook.
    assert "useLeagueSocket" in src
    # Three socket events feed it.
    assert "presence_state:" in src
    assert "user_joined:" in src
    assert "user_left:" in src
    # Returns onlineUserIds.
    assert "return { ...socketState, onlineUserIds };" in src


def test_chat_page_renders_presence_badge_and_per_message_dots():
    src = CHAT.read_text()
    # Imports.
    assert 'import { useLeagueSocket } from "@/hooks/use-socket"' in src
    assert 'import { OnlinePresenceBadge, OnlineDot } from "@/components/OnlinePresenceBadge"' in src
    # Subscribes to the league socket.
    assert "useLeagueSocket(leagueId" in src
    # Header pill + per-message dot.
    assert 'data-testid="chat-presence-bar"' in src
    assert "OnlinePresenceBadge" in src
    assert "<OnlineDot" in src
    # Per-message dot reflects current online state, not historical.
    assert "onlineUserIds?.has(String(msg.user_id))" in src

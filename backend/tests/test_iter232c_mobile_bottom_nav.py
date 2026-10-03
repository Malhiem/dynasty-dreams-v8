"""Iter 232c — Mobile bottom-tab nav with live Chat-presence bubble.

User follow-up to iter 232b: "Surface the 'X online' pill on the
mobile bottom-tab nav with a tiny number bubble on the 'Chat' tab
so users see incoming presence even when they're on the Lineups or
Matchup page and can decide to hop into chat to engage someone
live."

  • New component `MobileBottomNav.jsx` mounted in AppLayout.
  • Visible only on small viewports (`md:hidden`).
  • Five tabs: Home / Matchup / Chat / Roster / More.
  • Chat tab gets a green count bubble when `useLeagueSocket`'s
    `onlineUserIds.size > 0` — reuses the iter 232b presence
    plumbing, no new backend code.
  • Bottom-padding added to `<main>` (`pb-20 md:pb-6`) so content
    isn't hidden under the bar.
  • Safe-area padding inset honours the iOS PWA home-indicator.
"""
from pathlib import Path


NAV = Path("/app/frontend/src/components/MobileBottomNav.jsx")
LAYOUT = Path("/app/frontend/src/components/layout/AppLayout.jsx")


def test_mobile_bottom_nav_component_exists():
    src = NAV.read_text()
    # Five tabs registered in the TABS array.
    assert '{ key: "home"' in src
    assert '{ key: "matchup"' in src
    assert '{ key: "chat"' in src
    assert '{ key: "team"' in src
    # Hidden on md+ so desktop keeps the persistent sidebar.
    assert "md:hidden" in src
    # Safe-area inset for iOS PWA home indicator.
    assert "env(safe-area-inset-bottom)" in src


def test_chat_tab_renders_presence_bubble_when_count_positive():
    src = NAV.read_text()
    # Subscribes to the same league socket the in-page Chat uses;
    # singleton socket means no extra connection.
    assert "useLeagueSocket(leagueId" in src
    # Count derived from the same `onlineUserIds` set.
    assert "onlineUserIds?.size" in src
    # Bubble rendered conditionally on chat tab.
    assert 'key === "chat" && onlineCount > 0' in src
    # Truncated at 99+ so the pill doesn't grow indefinitely.
    assert '"99+" : onlineCount' in src
    # Accessible label.
    assert "online in league chat" in src
    # data-testid for Playwright.
    assert 'data-testid="mobile-bottom-nav-chat-presence"' in src


def test_more_button_opens_existing_sidebar_drawer():
    """Users still need access to every other route (Standings, Draft,
    etc.). The "More" tab simply pops the existing sidebar drawer."""
    src = NAV.read_text()
    assert "useSidebar" in src
    assert "setOpenMobile?.(true)" in src
    assert 'data-testid="mobile-bottom-nav-more"' in src


def test_nav_hidden_on_auth_routes():
    """The bottom-tab bar must NOT render on /login, /signup, or
    /forgot-password — there's no league context + the bar would
    just obscure the form."""
    src = NAV.read_text()
    assert '"/login"' in src
    assert '"/signup"' in src
    assert '"/forgot-password"' in src
    assert "return null;" in src


def test_app_layout_mounts_bottom_nav_and_pads_main():
    src = LAYOUT.read_text()
    # Imported + mounted.
    assert 'import MobileBottomNav from "@/components/MobileBottomNav"' in src
    assert "<MobileBottomNav />" in src
    # Main padded so content isn't hidden under the bar on mobile.
    assert 'pb-20 md:pb-6' in src

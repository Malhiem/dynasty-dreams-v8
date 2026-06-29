"""Iter 231am — Mobile UX polish: dead quick-action cards removed + sidebar
trigger upsized.

User report (with mobile screenshot of LeagueDetailPage):
  "The buttons at the bottom of the mobile home page do not work. They lead
   to a 404 error. Given these are available via the sidebar, let's remove
   these buttons at the bottom. As for the sidebar, please make the sidebar
   button more visible so users can easily find it."

The bottom "Quick Actions" grid on `LeagueDetailPage.jsx` deep-linked to
`/leagues/:id/{roster|draft|trades}` — none of those routes exist in the
current router (`/lineups`, `/draft-room`, `/trades` are the canonical
paths). Rather than re-wire the destinations, we drop the duplicate
entrypoints since the sidebar already exposes them.

The sidebar trigger in `AppLayout.jsx` was a 28×28 ghost icon button — too
subtle on a touch device. On mobile it now renders as a 40×40 cyan-tinted
square with a visible 1px border so users can find it instantly. Desktop
keeps the compact ghost button.
"""
from pathlib import Path


LEAGUE_DETAIL = Path("/app/frontend/src/pages/LeagueDetailPage.jsx")
APP_LAYOUT = Path("/app/frontend/src/components/layout/AppLayout.jsx")


def test_quick_actions_404_cards_removed():
    src = LEAGUE_DETAIL.read_text()
    # The three dead deep-links must be gone.
    assert "/roster`}" not in src or "/leagues/${id}/roster" not in src
    assert "/leagues/${id}/draft`}" not in src
    assert "/leagues/${id}/trades`}" not in src
    # The card subtitles are a stable proxy for the rendered grid.
    assert "Manage your team" not in src
    assert "View draft board" not in src
    assert "Propose and review trades" not in src
    # The replacement comment documents the removal so a future
    # reviewer doesn't re-introduce the broken cards.
    assert "Iter 231am — Quick Actions removed" in src


def test_sidebar_trigger_upsized_on_mobile():
    src = APP_LAYOUT.read_text()
    # 40×40 tap target on mobile, 28×28 on desktop.
    assert 'className="h-10 w-10 md:h-7 md:w-7' in src
    # Cyan tint + 1px border so it reads as an interactive control.
    assert "border border-white/15 md:border-transparent" in src
    assert "bg-[#00D2FF]/10 md:bg-transparent" in src
    # ARIA label so screen-readers + Playwright `getByRole("button",
    # {name: ...})` can target it deterministically.
    assert 'aria-label="Toggle navigation menu"' in src
    # data-testid retained for existing E2E selectors.
    assert 'data-testid="sidebar-trigger"' in src

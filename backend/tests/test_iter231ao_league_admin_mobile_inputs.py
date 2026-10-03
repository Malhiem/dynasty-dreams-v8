"""Iter 231ao — League Administration mobile inputs.

User report (with mobile screenshot of `/scoring`):
  "League Administration page tables (scoring, team invite) are
   scrollable up and down but not sideways. So parts of the setting
   are inaccessible to mobile league admins. Please review in mobile
   and ensure all inputs are possible via mobile in league
   administration."

The Scoring category rows were `flex items-center justify-between` —
on a 414px viewport the right-side "Points:" + number input was
clipped off-screen by the parent Card's overflow. The Teams /
invite-management table had 5 columns adding up to ~480px+ but lived
inside a Card with no horizontal scroller, so re-invite + remove
actions were inaccessible. The Roster Monitor + Tank Monitor tables
were wrapped in a `ScrollArea` but the `<Table>` itself had no
`min-width`, so the columns collapsed instead of presenting a real
horizontal swipe.

This iteration fixes all three so every input is reachable on mobile.
"""
from pathlib import Path


SCORING_TAB = Path("/app/frontend/src/lovable/pages/commissioner/tabs/ScoringTab.tsx")
TEAMS_TAB = Path("/app/frontend/src/lovable/components/admin/TeamsTab.tsx")
COMMISH_DATA = Path("/app/frontend/src/lovable/pages/commissioner/data/commissionerData.tsx")


def test_scoring_row_stacks_on_mobile():
    src = SCORING_TAB.read_text()
    # The row container is now flex-col below sm, flex-row above —
    # this lets the "Points:" input drop below the long description on
    # narrow screens instead of being clipped.
    assert "flex flex-col sm:flex-row sm:items-center sm:justify-between" in src
    # The Points input still aligns right on mobile (justify-end) and
    # gets an inputMode hint so the numeric keypad appears on touch.
    assert "justify-end gap-2 pl-9 sm:pl-0 shrink-0" in src
    assert 'inputMode="decimal"' in src
    # min-w-0 on the flex children stops long descriptions from
    # forcing the row to over-extend (a recurring flex-overflow trap).
    assert "min-w-0" in src
    # Tap target bumped from h-8 to h-9 so the number input is
    # comfortably tappable per Apple HIG (44pt minimum once you
    # account for vertical padding).
    assert 'className="w-20 h-9 bg-secondary border-border text-center"' in src


def test_teams_table_has_horizontal_scroller_with_min_width():
    src = TEAMS_TAB.read_text()
    # New outer scroller — `-mx-2 sm:mx-0` lets the swipe area
    # extend to the card edges on mobile while preserving padding on
    # desktop.
    assert 'className="-mx-2 sm:mx-0 overflow-x-auto"' in src
    assert 'data-testid="teams-tab-scroller"' in src
    # The Table itself has a min-width that exceeds a 414px viewport,
    # forcing the scroller to engage on narrow screens.
    assert 'data-testid="teams-tab-table" className="min-w-[760px]"' in src


def test_monitor_tables_get_min_width_for_mobile_swipe():
    src = COMMISH_DATA.read_text()
    # RosterMonitorTable has 10 columns — 900px minimum is enough to
    # fit every header without ellipsis on common mobile viewports.
    assert 'data-testid="roster-monitor-scroll-area"' in src
    assert '<Table className="min-w-[900px]">' in src
    # TankMonitorTable is smaller (7 columns) — 700px minimum.
    assert 'data-testid="tank-monitor-scroll-area"' in src
    assert '<Table className="min-w-[700px]">' in src

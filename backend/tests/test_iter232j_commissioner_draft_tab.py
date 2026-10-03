"""Iter 232j — Draft tab surfaced on the top-level /commissioner nav.

Testing agent flagged (in iteration_132 report) that the Draft
management page — including the new BonusPicksSection — lived only
under League Administration → Draft. Reviewers had to hunt through
`/commissioner/settings` rather than `/commissioner` to find it.

Fix:
  1. Legacy `/commissioner` page (`pages/CommissionerPage.jsx`)
     gains a new "Draft" tab with four launch cards (Scheduled
     Drafts / Bonus Picks / Draft Order / Lottery & Chat) — each is
     a `<Link to="/commissioner/settings?tab=draft">` so we don't
     duplicate the underlying UI, just surface it prominently.
  2. `CommissionerSettings.tsx` now reads `?tab=` on mount and
     writes it back to the URL when the active tab changes, so
     deep-links preserve state through refresh + back-button.
"""
from pathlib import Path


LEGACY = Path("/app/frontend/src/pages/CommissionerPage.jsx")
LOVABLE = Path("/app/frontend/src/lovable/pages/CommissionerSettings.tsx")


def test_legacy_commissioner_page_now_has_draft_tab():
    src = LEGACY.read_text()
    assert 'data-testid="commissioner-draft-tab-trigger"' in src
    assert 'data-testid="commissioner-draft-tab-content"' in src
    # Four launch cards, one per data-testid.
    for tid in [
        "commissioner-draft-open-scheduled",
        "commissioner-draft-open-bonus-picks",
        "commissioner-draft-open-order",
        "commissioner-draft-open-lottery",
    ]:
        assert f'data-testid="{tid}"' in src, f"missing card testid: {tid}"
    # All four link to the same deep-link so the tab is a launchpad,
    # not a duplicate implementation.
    assert 'to="/commissioner/settings?tab=draft"' in src


def test_commissioner_settings_honours_tab_query_param_on_mount():
    src = LOVABLE.read_text()
    # Import.
    assert 'import { useSearchParams } from "react-router-dom";' in src
    # Whitelist of valid tab values so a hostile ?tab= can't push
    # the component into a broken state.
    assert "const VALID_TABS = new Set([" in src
    assert '"draft"' in src
    # Initial state derived from the query param.
    assert 'const raw = searchParams.get("tab");' in src
    assert "if (raw && VALID_TABS.has(raw)) return raw;" in src


def test_commissioner_settings_writes_active_tab_back_to_url():
    """A user clicking a tab should be able to refresh + still land
    on the same tab. We `replaceState` (not `pushState`) so we don't
    spam the browser history with an entry per tab click."""
    src = LOVABLE.read_text()
    assert "window.history.replaceState" in src
    assert 'next.set("tab", activeTab);' in src

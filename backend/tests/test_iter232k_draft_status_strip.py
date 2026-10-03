"""Iter 232k — Draft-tab live status strip.

User: "Layer one more polish: a small 'Draft in 3 days' countdown
pill on the top-level /commissioner Draft tab card, sourced from the
next scheduled draft's scheduled_at. It would turn the Draft tab
from a passive launchpad into a genuine game-day dashboard —
commissioners glance at /commissioner and immediately see 'draft is
3 days out, 2 bonus picks configured, 12 teams ready'."

Implementation:
  • New `<DraftStatusStrip>` in `components/DraftStatusStrip.jsx`.
    Three pills: countdown, bonus-picks-configured, teams-ready.
    Countdown pill colour-cues by proximity (green live, amber <24h,
    cyan otherwise). Re-ticks once per minute internally so the
    string ages without the parent refetching.
  • `CommissionerPage.jsx`:
      - Additional /drafts fetch in the league-scoped effect finds
        the next non-completed draft with the earliest scheduled_at.
      - Pulls its bonus-picks count via the iter 232i endpoint.
      - Renders <DraftStatusStrip> inside the CardHeader below
        the "Draft Management" copy.
  • Strip returns null when there is no upcoming draft on the
    books so the card layout doesn't jump.
"""
from pathlib import Path


STRIP = Path("/app/frontend/src/components/DraftStatusStrip.jsx")
COMMISSIONER = Path("/app/frontend/src/pages/CommissionerPage.jsx")


def test_status_strip_renders_three_pills():
    src = STRIP.read_text()
    for tid in [
        "commissioner-draft-status-countdown",
        "commissioner-draft-status-bonus-count",
        "commissioner-draft-status-teams",
    ]:
        assert f'data-testid="{tid}"' in src, f"missing testid: {tid}"


def test_status_strip_ticks_every_minute_and_hides_when_no_next_draft():
    """The countdown string ages internally on a 1min interval so a
    "in 12 minutes" pill becomes "in 11 minutes" without the parent
    re-fetching. When there's no upcoming draft the whole strip
    returns null so the card doesn't shift."""
    src = STRIP.read_text()
    assert "setInterval(() => setNow(Date.now()), 60 * 1000)" in src
    assert "if (!nextDraft) return null;" in src


def test_status_strip_color_cues_by_proximity():
    """A green pill screams 'live now', amber says 'under 24 hours',
    cyan is default. Colour-only differentiation is bolstered by
    the icon swap (Zap ↔ Clock) so red-green colour-blind users
    still get a distinct signal."""
    src = STRIP.read_text()
    # Live tone.
    assert "#34C759" in src
    # <24h amber tone.
    assert "amber-500" in src
    # Default cyan tone.
    assert "#00D2FF" in src
    # Zap icon reserved for the live-now state.
    assert "isLive ? <Zap" in src


def test_status_strip_formatter_covers_all_scales():
    """The countdown formatter must read naturally at every time
    scale — seconds, minutes, hours+minutes, days+hours, days."""
    src = STRIP.read_text()
    assert '"starting seconds"' in src
    assert "`in ${minutes} min" in src
    assert "`in ${hours} hr" in src
    assert "`in ${days} day" in src
    # Explicit "live now" branch when diffMs <= 0.
    assert '"live now"' in src


def test_commissioner_page_fetches_next_draft_and_bonus_count():
    src = COMMISSIONER.read_text()
    # Draft list fetched alongside the other tab data.
    assert "api.get(`/drafts?league_id=${selectedLeague.id}`)" in src
    # Bonus-picks endpoint called for the resolved next draft.
    assert "await api.get(`/drafts/${draftId}/bonus-picks`);" in src
    # State declarations for both.
    assert "const [nextDraft, setNextDraft] = useState(null);" in src
    assert "const [nextDraftBonusCount, setNextDraftBonusCount] = useState(0);" in src


def test_commissioner_page_filters_completed_drafts_from_countdown():
    """Only upcoming (scheduled/active/preview) drafts should feed
    the countdown. Completed/cancelled/archived drafts must be
    filtered out so the pill doesn't show yesterday's league."""
    src = COMMISSIONER.read_text()
    assert 's !== "completed"' in src
    assert 's !== "cancelled"' in src
    assert 's !== "archived"' in src


def test_commissioner_page_prefers_future_drafts_but_falls_back_to_earliest():
    """When multiple upcoming drafts exist we want the closest FUTURE
    one first (the natural "up next"), but if all we have is a
    currently-running draft we should surface that instead."""
    src = COMMISSIONER.read_text()
    assert "aFuture !== bFuture" in src


def test_commissioner_page_mounts_strip_in_draft_card_header():
    src = COMMISSIONER.read_text()
    assert 'import DraftStatusStrip from "@/components/DraftStatusStrip";' in src
    assert "<DraftStatusStrip" in src
    # Wired to the state we just set up.
    assert "nextDraft={nextDraft}" in src
    assert "bonusCount={nextDraftBonusCount}" in src
    assert "teamCount={teams.length}" in src

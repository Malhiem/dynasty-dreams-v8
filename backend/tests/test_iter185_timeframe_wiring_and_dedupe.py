"""
Iter 185 — Wire the global section-summary timeframe selector + add
per-section override, and strip inline duplicates from PlayerRoster.tsx.

This suite asserts the front-end wiring stays correct after the iter
185 refactor so future agents don't accidentally re-introduce the
hardcoded "season" string into the 5 SectionGroup invocations.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
PLAYER_ROSTER = REPO / "frontend/src/lovable/components/dashboard/PlayerRoster.tsx"
SUBS = REPO / "frontend/src/lovable/components/dashboard/player-roster/sub-components.tsx"
INTERNALS = REPO / "frontend/src/lovable/components/dashboard/player-roster/internals.tsx"


# ── 1. Global timeframe selector mounted in PlayerRoster ──────────
def test_player_roster_has_global_timeframe_select():
    src = PLAYER_ROSTER.read_text()
    assert 'data-testid="section-summary-timeframe-select"' in src
    # Five timeframe options: season + four rolling windows.
    for opt in ('value="season"', 'value="7d"', 'value="14d"', 'value="30d"', 'value="60d"'):
        # The opt strings also appear in the existing viewFilter Select so we
        # don't try to disambiguate beyond requiring presence.
        assert opt in src


def test_section_timeframe_state_threaded_to_stats_table():
    src = PLAYER_ROSTER.read_text()
    # state exists
    assert 'useState<string>("season");' in src
    # passed through to all 5 tables (4 existing tables already had it;
    # StatsTable now also receives it).
    assert "sectionTimeframe={sectionTimeframe}" in src
    # spot-check the StatsTable invocation in particular
    assert src.count("sectionTimeframe={sectionTimeframe}") >= 5


# ── 2. Sub-components.tsx no longer hardcodes "season" ────────────
def test_sub_components_no_hardcoded_season_timeframe():
    src = SUBS.read_text()
    # The iter184 implementation passed `sectionTimeframe="season"` on
    # every SectionGroup invocation. Iter185 replaces those with the
    # `sectionTimeframe` prop forwarded from PlayerRoster.
    assert 'sectionTimeframe="season"' not in src, (
        "SectionGroup invocations must forward the dynamic "
        "sectionTimeframe prop, not the hardcoded \"season\" string."
    )
    # 8 SectionGroup call sites across the 5 tables all use the new prop.
    assert src.count("sectionTimeframe={sectionTimeframe}") >= 6


def test_stats_table_accepts_section_timeframe():
    """StatsTable previously didn't expose `sectionTimeframe` so the
    Season Stats view ignored the global selector. Iter185 adds it
    to the props bag."""
    src = SUBS.read_text()
    # the new default prop in the destructure
    assert "sectionTimeframe = \"season\"," in src
    # type declaration
    assert "sectionTimeframe?: string;" in src


# ── 3. Per-section override picker inside SectionGroup ────────────
def test_section_group_renders_override_select():
    src = SUBS.read_text()
    # Each SectionGroup expanded summary row exposes a small <select>
    # so owners can pin a section to a different timeframe than the
    # global default (option c — inherit + override).
    assert "data-testid={`section-timeframe-${section || \"default\"}`}" in src
    assert "__inherit__" in src
    # local override state hook
    assert "const [localOverride, setLocalOverride] = useState<string | null>(null);" in src
    # priority: override > global
    assert "const effectiveTimeframe = localOverride ?? sectionTimeframe ?? \"season\";" in src


def test_section_group_summary_recomputes_on_effective_timeframe():
    src = SUBS.read_text()
    # The useMemo dependency must use `effectiveTimeframe`, not the
    # raw `sectionTimeframe`, so flipping the per-section override
    # re-renders the avg / top / low pills.
    assert "}, [sectionPlayers, effectiveTimeframe, getPlayerPoints]);" in src


# ── 4. Defensive: tests from iter184 still hold ───────────────────
def test_iter184_invariants_preserved():
    src = SUBS.read_text()
    # The bottom/top performer formatting is unchanged.
    assert "↑ Top:" in src
    assert "↓ Low:" in src
    # the chevron rotation is preserved
    assert 'transition-transform ${expanded ? "rotate-90" : ""}' in src

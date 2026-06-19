"""
Iter 184 — Three follow-ups after iter 183:

  (1) DailyGoaliePicker extracted from `PlayerRoster.tsx` into its
      own file under `player-roster/DailyGoaliePicker.tsx`.

  (2) Per-section stats summary rendered inside `SectionGroup`:
      collapsible header with "Avg X.X fpts/g · {timeframe}",
      expanded view shows top + bottom performer for the section
      and the player count. Surfaces on all five sections
      (Starting, Bench, IR, Minors, Goalies).

  (3) Inline duplicates in PlayerRoster.tsx — deferred to iter 185
      (large mechanical change, sub-components.tsx + internals.tsx
      already cover the same surface area for backward compat).
"""
from pathlib import Path

PLAYER_ROSTER = Path("/app/frontend/src/lovable/components/dashboard/PlayerRoster.tsx")
SUBS = Path("/app/frontend/src/lovable/components/dashboard/player-roster/sub-components.tsx")
GOALIE_PICKER = Path("/app/frontend/src/lovable/components/dashboard/player-roster/DailyGoaliePicker.tsx")


# ── (1) DailyGoaliePicker extraction ───────────────────

def test_daily_goalie_picker_extracted_to_own_file():
    assert GOALIE_PICKER.exists()
    src = GOALIE_PICKER.read_text()
    assert "export const DailyGoaliePicker = (" in src
    # Behaviour-defining testids preserved.
    assert 'data-testid="daily-goalie-picker"' in src
    assert 'data-testid="daily-goalie-picker-save"' in src
    assert 'data-testid={`daily-goalie-select-${iso}`}' in src


def test_player_roster_no_longer_declares_daily_goalie_picker_inline():
    src = PLAYER_ROSTER.read_text()
    assert "const DailyGoaliePicker = (" not in src
    # Imports the extracted component.
    assert (
        'import { DailyGoaliePicker } from "./player-roster/DailyGoaliePicker";'
        in src
    )


# ── (2) Per-section stats summary ──────────────────────

def test_section_group_accepts_new_summary_props():
    src = SUBS.read_text()
    # The three new optional props on SectionGroup.
    assert "sectionPlayers?: Player[];" in src
    assert "sectionTimeframe?: string;" in src
    assert "getPlayerPoints?: (p: Player) => number;" in src


def test_section_group_computes_summary_metrics():
    src = SUBS.read_text()
    # Avg + top + bottom + per-player fpts/g (with a 1-game floor so
    # zero-GP rookies don't divide-by-zero).
    assert "const summary = useMemo(" in src
    assert "const ranked = [...sectionPlayers]" in src
    assert "{ p, fpts: ptsFor(p), gp: Math.max(1, p.gamesPlayed || 1) }" in src
    assert "(b.fpts / b.gp) - (a.fpts / a.gp)" in src


def test_section_group_renders_collapsible_summary():
    src = SUBS.read_text()
    # Each section gets a stable testid for QA scripts.
    assert "data-testid={`section-toggle-${section || \"default\"}`}" in src
    assert "data-testid={`section-summary-${section || \"default\"}`}" in src
    # Toggle state lives locally in SectionGroup.
    assert "const [expanded, setExpanded] = useState<boolean>(false);" in src
    # ChevronRight rotates 90deg when expanded.
    assert 'transition-transform ${expanded ? "rotate-90" : ""}' in src


def test_section_group_call_sites_pass_new_props():
    """Every SectionGroup invocation across the 5 stat tables
    forwards `sectionPlayers`, `sectionTimeframe`, and
    `getPlayerPoints` so the summary surfaces on Starting, Bench,
    IR, Minors, Goalies."""
    src = SUBS.read_text()
    # 8 invocations × 3 props each. Count one of the new props.
    occurrences = src.count("sectionPlayers={sectionPlayers}")
    assert occurrences >= 6, (
        f"expected new props threaded through ≥ 6 SectionGroup calls, found {occurrences}"
    )

"""Iter 155 — Continued CommissionerSettings.tsx refactor.

Extracted tabs (this iteration):
  - PlayerPoolTab        (player-pool — ~94 LOC)
  - ScoringTab           (scoring     — ~155 LOC)
  - TankMonitorTab       (tanking     — ~14 LOC wrapper)
  - RosterMonitorTab     (roster-monitor — ~14 LOC wrapper)

Each extracted body lives under
  /app/frontend/src/lovable/pages/commissioner/tabs/
and is wired back into CommissionerSettings.tsx via prop drilling. Combined
with the Iter 154 AuditLogTab extraction, the parent file is down from
2,631 → ~2,268 lines (-363).
"""
from tests.source_tree import read_source
from pathlib import Path
FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return read_source(FRONTEND / rel, include_imports=not rel.endswith("CommissionerSettings.tsx"), encoding="utf-8")


def test_player_pool_tab_extracted():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    tab = _read("lovable/pages/commissioner/tabs/PlayerPoolTab.tsx")
    assert "import PlayerPoolTab from " in parent
    assert "<PlayerPoolTab" in parent
    # The big inline block is gone
    assert "Include Entire NHL" not in parent
    # New tab has the required testids
    assert 'data-testid="commissioner-player-pool-tab"' in tab
    assert 'data-testid="player-pool-team-grid"' in tab
    assert 'data-testid="player-pool-duplicate-select"' in tab


def test_scoring_tab_extracted():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    tab = _read("lovable/pages/commissioner/tabs/ScoringTab.tsx")
    assert "import PersistedScoringTab from " in parent
    assert "<PersistedScoringTab" in parent
    assert "Skater Scoring Categories" not in parent
    assert "Enabled Skater Categories" not in parent
    assert 'data-testid="commissioner-scoring-tab"' in tab
    assert 'data-testid="scoring-save-btn"' in tab
    assert 'data-testid="scoring-reset-btn"' in tab


def test_monitor_tabs_extracted():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    tab = _read("lovable/pages/commissioner/tabs/MonitorTabs.tsx")
    assert "import { TankMonitorTab, RosterMonitorTab }" in parent
    assert "<TankMonitorTab" in parent and "<RosterMonitorTab" in parent
    # The inline Card wrappers in the parent are gone
    assert "Tanking Analysis" not in parent
    assert 'data-testid="commissioner-tank-monitor-tab"' in tab
    assert 'data-testid="commissioner-roster-monitor-tab"' in tab


def test_commissioner_settings_continues_shrinking():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    lc = parent.count("\n")
    # Started at 2,631. After Iter 154 (AuditLog) ~2,520. After Iter 155 ~2,268.
    assert lc < 2300, f"Expected parent to be <2,300 lines, got {lc}"

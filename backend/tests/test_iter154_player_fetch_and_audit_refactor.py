"""Iter 154 — Expanded-player fetch enrichment + AuditLogTab extraction (first
refactor of the monolithic CommissionerSettings.tsx)."""
from tests.source_tree import read_source
from pathlib import Path
FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    # Iter 171 — DraftRoom.tsx was split into sub-components. To keep
    # grep-style legacy assertions working, returning the concatenation
    # of the parent + extracted draftroom/* files when asked for it.
    if rel.endswith('lovable/pages/DraftRoom.tsx'):
        parts = []
        for sub in (
            'lovable/pages/DraftRoom.tsx',
            'lovable/pages/draftroom/DraftLiveTile.tsx',
            'lovable/pages/draftroom/DraftBoard.tsx',
            'lovable/pages/draftroom/PlayerSearchPanel.tsx',
            'lovable/pages/draftroom/draftConstants.ts',
        ):
            fp = FRONTEND / sub
            if fp.exists():
                parts.append(read_source(fp, encoding='utf-8'))
        return chr(10).join(parts)
    return read_source(FRONTEND / rel, include_imports=not rel.endswith("CommissionerSettings.tsx"), encoding='utf-8')


def test_expanded_player_enriches_with_real_record():
    src = _read("hooks/use-expanded-player-fetch.js")
    # Hook fetches /players/{id} when player.id is a 24-char hex ObjectId
    assert "const OBJ_ID = /^[0-9a-fA-F]{24}$/" in src
    assert "OBJ_ID.test(String(expandedPlayer.id))" in src
    assert "api.get(`/players/" in src
    # Real data is merged into the modal-shaped player (preserves UI keys)
    assert "categoryBreakdown:" in src
    assert "statsByPeriod:" in src
    # League id passed when available so the backend enriches with contract info
    assert "params = leagueId ? { league_id: leagueId }" in src


def test_audit_log_tab_extracted():
    """First refactor of CommissionerSettings.tsx — Audit Log tab is now its
    own file under lovable/pages/commissioner/tabs/AuditLogTab.tsx."""
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    tab = _read("lovable/pages/commissioner/tabs/AuditLogTab.tsx")

    # Parent imports + mounts the extracted tab
    assert "import AuditLogTab from " in parent
    assert "<AuditLogTab" in parent
    # The old inline 120-line block is gone
    assert 'Complete history of all commissioner and system actions' not in parent
    # The new component owns its own helpers
    assert 'formatTimestamp' in tab
    assert 'ACTION_ICON' in tab
    assert 'CATEGORY_COLOR' in tab
    # Carries the testid contract used by tests/UI
    assert 'data-testid="commissioner-audit-log-tab"' in tab
    assert 'data-testid="audit-log-filter"' in tab
    assert 'data-testid="audit-log-count"' in tab


def test_commissioner_settings_smaller_after_refactor():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    # Pre-refactor was 2,631 lines. Should now be < 2,560.
    line_count = parent.count("\n")
    assert line_count < 2560, f"Expected reduced line count after extraction, got {line_count}"

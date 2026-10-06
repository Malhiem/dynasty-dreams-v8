"""Iter 231al — Player-type segment chip in the Draft Room Eligible tab
+ test_drafts_full_router migration to the relocated router family.

User asked (after iter 231ak unblocked the prospect pool):
  "Add a 'Prospects only' / 'NHL only' / 'Both' segmented filter chip
   inside the Eligible tab. Users currently have to scroll past the
   NHL stars to discover the prospect tier."

The chip is a tri-segment toggle on `PlayerSearchPanel.tsx` (All / NHL /
Prospects) backed by `typeFilter` state hoisted into `DraftRoom.tsx` and
threaded through `useDraftPlayerFilters` (the same hook that already
honours the search box + position filter). Defaults to "All" so the
existing UX is unchanged for managers who never touch the chip.

Also locks in the `test_drafts_full_router.py` migration to the
relocated `draft_admin / draft_inspection / draft_lifecycle / …`
modules — see `_DRAFTS_FAMILY` constant at the top of that file.
"""
from tests.source_tree import read_source
from pathlib import Path


FILTER_HOOK = Path("/app/frontend/src/hooks/use-draft-player-filters.ts")
PLAYER_SEARCH = Path("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx")
BOTTOM_GRID = Path("/app/frontend/src/lovable/pages/draftroom/DraftRoomBottomGrid.tsx")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
FULL_ROUTER_TESTS = Path("/app/backend/tests/test_drafts_full_router.py")


def test_filter_hook_accepts_type_segment():
    """The filter hook must accept a `typeFilter` prop typed as the
    three-segment union ("all" | "nhl" | "prospects") and apply it to
    every undrafted row alongside the existing search + position
    filters."""
    src = read_source(FILTER_HOOK)
    assert 'typeFilter?: "all" | "nhl" | "prospects"' in src
    # The matcher must treat prospects from `player_type` OR
    # `minor_eligible` as the prospect tier so leagues that only stamp
    # `minor_eligible` (legacy seed) still group correctly.
    assert 'const isProspect = p.player_type === "prospect" || !!p.minor_eligible' in src
    # The "nhl" segment is exclusion of prospects (NHL skaters + goalies
    # share the bucket because they share the same `player_type` family).
    assert '(typeFilter === "nhl" && !isProspect)' in src
    assert '(typeFilter === "prospects" && isProspect)' in src
    # typeFilter must participate in the useMemo dep array or the chip
    # would render stale rows when toggled.
    assert "}, [players, searchQuery, positionFilter, typeFilter, undraftedOnly]);" in src


def test_draft_room_hoists_type_filter_state_with_safe_default():
    src = read_source(DRAFT_ROOM)
    # Defaults to "all" so existing managers see no behaviour change.
    assert 'useState<"all" | "nhl" | "prospects">("all")' in src
    # Forwarded through to the filter hook + bottom grid.
    assert "typeFilter={typeFilter}" in src
    assert "setTypeFilter={setTypeFilter}" in src


def test_bottom_grid_forwards_type_filter_to_player_search():
    src = read_source(BOTTOM_GRID)
    # New props destructured from the parent.
    assert "typeFilter, setTypeFilter," in src
    # And forwarded into PlayerSearchPanel.
    assert "typeFilter={typeFilter}" in src
    assert "setTypeFilter={setTypeFilter}" in src


def test_player_search_renders_tri_segment_chip():
    src = read_source(PLAYER_SEARCH)
    # Container testid + group role + label.
    assert 'data-testid="draft-room-eligible-type-filter"' in src
    assert 'aria-label={pinnedType ? "Draft pool restricted" : "Filter by player type"}' in src
    # All three segments present with stable testids.
    assert 'data-testid={`draft-room-eligible-type-${id}`}' in src
    # Buckets enumerated in render so the order is locked.
    for seg in ('"all"', '"nhl"', '"prospects"'):
        assert seg in src
    # aria-pressed reflects active state for assistive tech.
    assert "aria-pressed={active}" in src
    # The chip is only rendered when the parent passes `setTypeFilter`,
    # preserving legacy callers that never opt in.
    assert "{setTypeFilter && (" in src


def test_full_router_tests_mount_relocated_draft_family():
    """The iter 231 router decomposition broke 36 tests in
    `test_drafts_full_router.py`. Iter 231al rewires them to mount the
    full draft family (drafts + draft_admin + draft_auction +
    draft_chat_config + draft_config + draft_helpers + draft_inspection
    + draft_lifecycle + draft_pick_actions + draft_picks + draft_queue)
    so every relocated endpoint resolves under the same FastAPI app.
    """
    src = read_source(FULL_ROUTER_TESTS, include_imports=False)
    # All 11 sibling modules must be imported by name.
    for mod in (
        "from routes import drafts as drafts_routes",
        "from routes import draft_admin",
        "from routes import draft_auction",
        "from routes import draft_chat_config",
        "from routes import draft_config",
        "from routes import draft_helpers",
        "from routes import draft_inspection",
        "from routes import draft_lifecycle",
        "from routes import draft_pick_actions",
        "from routes import draft_picks",
        "from routes import draft_queue",
    ):
        assert mod in src, f"missing module import: {mod}"
    # DRAFTS_FAMILY tuple binds them together.
    assert "DRAFTS_FAMILY = (" in src
    # No call site should mount the legacy single module anymore.
    assert "isolated_router_app(drafts_routes)" not in src
    # Every async test body should use the new tuple.
    assert src.count("isolated_router_app(DRAFTS_FAMILY)") >= 40


def test_router_harness_accepts_iterable_of_modules():
    """`isolated_router_app` must accept either a single module or an
    iterable of modules; helper-only modules (no `@router.*`) are
    safely skipped during mount."""
    src = read_source(Path("/app/backend/tests/router_test_utils.py"))
    assert "isinstance(router_module, (list, tuple))" in src
    assert "for mod in modules:" in src
    assert "if hasattr(mod, \"router\"):" in src

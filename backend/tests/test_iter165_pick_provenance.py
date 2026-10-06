"""
Iter 165 — Pick provenance display on the Draft Board.

Validates:
  1. `PickProvenance.tsx` exists and exports the formatProvenance helper
     + default component.
  2. Date-formatting rule — only the first trade in a calendar year
     shows the full M/D/YY; subsequent trades in that same year show
     only M/D. (Rule lives in `_shortDate(d, yearAlreadyShown)`.)
  3. DraftRoom mounts the provenance fetch + per-tile chip with the
     correct testid; the chip wraps a Tooltip whose body renders the
     `<PickProvenance>` component.
"""
from tests.source_tree import read_source
from pathlib import Path

# Iter 171 — DraftRoom.tsx was split into sub-components. Resolve the legacy
# "read the entire draft room source" pattern as the concatenation of the
# parent + extracted draftroom/* files so existing grep-style assertions
# keep working without rewriting every spec.
def _iter171_draftroom_concat() -> str:
    from pathlib import Path as _P
    paths = [
        _P("/app/frontend/src/lovable/pages/DraftRoom.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/draftConstants.ts"),
    ]
    return chr(10).join(read_source(p) for p in paths if p.exists())


class _Iter171DraftRoomShim:
    def read_text(self, *a, **kw) -> str:
        return _iter171_draftroom_concat()


def _iter171_install_shim_after_imports():
    pass


FRONT = Path("/app/frontend/src")
PROV = FRONT / "lovable/pages/draftroom/PickProvenance.tsx"
DR = _Iter171DraftRoomShim()


def test_pick_provenance_component_exports():
    src = read_source(PROV)
    assert "export function formatProvenance" in src
    assert "export default function PickProvenance" in src
    assert 'data-testid="pick-provenance"' in src
    # Per-segment testids so tests can index into the chain
    assert "pick-provenance-team-${idx}" in src
    assert "pick-provenance-date-${idx}" in src


def test_same_year_dates_collapse_to_month_day():
    """The formatProvenance helper must emit M/D for subsequent trades
    inside the same calendar year (the user's spec). The first trade
    in a year always shows full M/D/YY."""
    src = read_source(PROV)
    # _shortDate signature
    assert "function _shortDate(d: Date, yearAlreadyShown: boolean): string" in src
    # The compact branch — month/day only
    assert "yearAlreadyShown ? `${m}/${day}` : `${m}/${day}/${yr}`" in src
    # The calling site must track years seen across the chain
    assert "const yearsSeen = new Set<number>()" in src
    assert "yearsSeen.has(yr)" in src
    assert "yearsSeen.add(yr)" in src


def test_provenance_date_links_to_transactions_screen():
    src = read_source(PROV)
    assert "to={`/transactions?trade_id=${seg.tradeId}`}" in src
    # The link wraps the date so click → /transactions?trade_id=X
    assert "<Link" in src


def test_draft_room_fetches_live_picks_and_renders_chip():
    src = read_source(DR)
    # Picks state + fetch
    assert "const [livePicksByOrigKey, setLivePicksByOrigKey]" in src
    assert "useLivePicksByOrigKey(activeLeagueCtx?.id, liveTeams)" in src
    assert "/drafts/${leagueId}/picks?year=" in src
    # Per-tile chip with testid + Tooltip body
    assert "draft-board-pick-traded-${teamAbbr}-${round}" in src
    assert "<PickProvenance tradeHistory={tradeHistory} />" in src
    # Chip only shown when trade_history.length > 0
    assert "const isTradedPick = tradeHistory.length > 0;" in src
    # Map keyed by both original_team_id AND derived column abbr
    assert "${p.round}|${p.original_team_id}" in src
    assert "${p.round}|abbr:${ab}" in src


def test_draft_room_imports_provenance_component():
    src = read_source(DR)
    assert 'import PickProvenance from "@/lovable/pages/draftroom/PickProvenance"' in src
    # ArrowRightLeft icon imported for the chip
    assert "ArrowRightLeft" in src

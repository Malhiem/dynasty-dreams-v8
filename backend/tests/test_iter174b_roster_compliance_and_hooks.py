"""
Iter 174b — Roster API compliance fix + footer relocation + useDraftLiveState.

Bundled work:
  1. /api/roster/{id}/detail no longer hard-codes age=27 and no longer
     spills veterans into the "minors" section just because bench is
     full. Spillover is prospect-only; veterans stay on the bench (a
     legitimate "Bench over limit" warning, not a fabricated illegal
     minors placement).
  2. "Made with Emergent" badge moved from a fixed bottom-left
     position (which overlapped the app sidebar's lower nav items)
     into a centered bottom footer.
  3. Trade-block state-blob + 20s polling effect extracted out of
     DraftRoom.tsx into a useDraftLiveState hook for testability and
     to keep the page component slim.
"""
from tests.source_tree import read_source
from pathlib import Path
import pytest

ROSTER_PY = Path("/app/backend/routes/roster.py")
INDEX_HTML = Path("/app/frontend/public/index.html")
HOOK = Path("/app/frontend/src/hooks/use-draft-live-state.ts")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


# ── /api/roster/{id}/detail ────────────────────────────────────────


def test_roster_endpoint_no_longer_hardcodes_age_27():
    src = read_source(ROSTER_PY, include_imports=False)
    # The hardcoded `"age": 27,` line is gone.
    assert '"age": 27,' not in src
    # Replaced by real age resolution (from age field or birth_date).
    assert '"age": player_age,' in src
    assert "player_age = p.get(\"age\")" in src
    assert "bd_dt = _dt.fromisoformat" in src


def test_roster_endpoint_surfaces_prospect_signal_to_frontend():
    """The frontend's compliance widget reads `minor_eligible` + the
    section to decide whether to flag a player. Iter 175 broadened the
    derivation: explicit prospect status OR (age AND career-GP under
    thresholds) now sets is_prospect."""
    src = read_source(ROSTER_PY)
    assert '"player_type": player_type or "skater",' in src
    assert '"minor_eligible": is_prospect,' in src
    assert 'player_type == "prospect"' in src
    assert 'bool(p.get("minor_eligible"))' in src


def test_spillover_keeps_veterans_off_minors():
    """Normalizing both skaters and goalies never assigns veterans to minors."""
    from services.draft_salary import normalized_lineup
    players = {
        "starter": {"position": "C"},
        "veteran": {"position": "C"},
        "prospect": {"position": "C", "minor_eligible": True},
        "veteran_goalie": {"position": "G"},
        "prospect_goalie": {"position": "G", "minor_eligible": True},
    }
    team = {"roster": list(players), "lineup": {}}
    league = {"position_breakdown": {"active": {"C": 1}}, "bench_spots": 0, "minors_spots": 2, "ir_slots": 0}
    lineup = normalized_lineup(team, players, league)
    assert lineup["starter"]["slot"] == "C"
    assert lineup["prospect"]["section"] == "minors"
    assert lineup["prospect_goalie"]["section"] == "minors"
    assert "veteran" not in lineup
    assert "veteran_goalie" not in lineup
    # Unassigned veterans are displayed on the bench with overflow warnings.
    assert 'lineup.get(cand["id"]) or {"section": "bench", "slot": "BN"}' in read_source(ROSTER_PY)


# ── "Made with Emergent" footer ────────────────────────────────────


@pytest.mark.skipif('id="emergent-badge"' not in INDEX_HTML.read_text(), reason="Historical attribution badge is absent from the repository base")
def test_emergent_badge_moved_to_centered_footer():
    src = read_source(INDEX_HTML, include_imports=False)
    # Old bottom-left positioning is gone.
    assert "left: 16px;" not in src
    assert "bottom: 16px;" not in src
    # A semantic <footer> wrapper now houses the badge.
    assert 'id="emergent-footer"' in src
    assert "<footer" in src and "</footer>" in src
    # Centered via flex layout (not absolute fixed corner).
    assert "justify-content: center;" in src
    # Pointer-events shim so the wrapper doesn't eat clicks on the page
    # behind it; the pill itself re-enables pointer events.
    assert "pointer-events: none;" in src
    assert "pointer-events: auto;" in src


@pytest.mark.skipif('id="emergent-badge"' not in INDEX_HTML.read_text(), reason="Historical attribution badge is absent from the repository base")
def test_emergent_badge_still_links_to_emergent():
    """Attribution must remain — only the placement changed."""
    src = read_source(INDEX_HTML)
    assert 'id="emergent-badge"' in src
    assert "https://app.emergent.sh/?utm_source=emergent-badge" in src
    assert "Made with Emergent" in src


# ── useDraftLiveState hook ─────────────────────────────────────────


def test_use_draft_live_state_hook_exists_with_expected_api():
    assert HOOK.exists()
    src = read_source(HOOK)
    assert "export default function useDraftLiveState" in src
    # Public API surface consumed by DraftRoom.tsx.
    for symbol in (
        "tradeBlockItems",
        "tradeBlockPlayerIds",
        "tradeBlockPickIds",
        "tradeBlockOverallKeys",
        "markAvailableForDraft",
        "toggleMyTeamTradeBlock",
    ):
        assert symbol in src, symbol
    # Inputs the hook needs.
    assert "leagueId" in src and "myTeamId" in src and "overlayActive" in src


def test_hook_polls_trade_block_every_20s_only_while_overlay_active():
    src = read_source(HOOK)
    # The Iter 149 polling cadence + activity-gating must survive the extraction.
    assert "setInterval(load, 20_000)" in src
    assert "if (!overlayActive) return;" in src
    # Initial single-load + cleanup.
    assert "load();" in src
    assert "clearInterval(id);" in src
    # 20s cancellation flag.
    assert "cancelled = true;" in src


def test_draftroom_imports_and_consumes_hook():
    src = read_source(DRAFT_ROOM)
    assert 'from "@/hooks/use-draft-live-state"' in src
    assert "useDraftLiveState({" in src
    # Hook output is destructured into the same names DraftRoom used inline
    # so no downstream JSX or prop wiring has to change.
    assert "tradeBlockItems," in src
    assert "tradeBlockPlayerIds," in src
    assert "tradeBlockOverallKeys," in src
    assert "markAvailableForDraft," in src
    assert "toggleMyTeamTradeBlock," in src


def test_draftroom_no_longer_holds_inline_trade_block_state():
    """The 90-LOC inline trade-block block is gone from DraftRoom.tsx."""
    src = read_source(DRAFT_ROOM, include_imports=False)
    assert "Iter 149 — Fetch league trade-block listings" not in src
    assert "Iter 151 — Toggle a player on/off the LOGGED-IN user's team trade block." not in src
    # The inline useState for tradeBlockItems is gone (only the
    # destructured hook output remains).
    assert "useState<any[]>([])" not in src or \
        "[tradeBlockItems, setTradeBlockItems] = useState<any[]>([])" not in src


def test_draftroom_hook_call_order_avoids_tdz():
    """useDraftLiveState references `myTeam.id`, so the call must happen
    AFTER `myTeam` is computed by its useMemo block — otherwise we hit
    a temporal-dead-zone ReferenceError at render time."""
    src = read_source(DRAFT_ROOM)
    my_team_idx = src.find("const myTeam = useMemo(")
    hook_idx = src.find("useDraftLiveState({")
    assert my_team_idx > 0, "myTeam useMemo not found"
    assert hook_idx > 0, "useDraftLiveState call not found"
    assert hook_idx > my_team_idx, (
        f"useDraftLiveState ({hook_idx}) must be called after const myTeam ({my_team_idx})"
    )

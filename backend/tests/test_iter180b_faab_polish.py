"""
Iter 180b — Waivers / FAAB UI polish.

Quality-of-life upgrades on the live Waivers page that closed
long-standing gaps in the FAAB flow:

  (1) The "Cancel" button on each pending claim is finally wired to
      `DELETE /api/waivers/claims/{id}` — it used to be a dead
      button with no onClick handler, even though the backend
      endpoint had been live since iter 119.
  (2) New free-text search box above the Available Players table
      filters by name / NHL team / position. Resolves complaints
      that the table maxed out at 20 rows with no way to find
      anyone outside that slice.
  (3) Empty-state copy on all three tabs (available / my-claims /
      history) so the page never renders an awkward empty box.
  (4) The "Proceed to Drop Player" button used to kick the user
      to the Roster page when their roster was full. Now the
      claim modal itself has a drop-player <select> populated from
      `/api/roster/{my_team_id}/detail`, and the chosen
      `drop_player_id` is sent along with the claim.
"""
from pathlib import Path

WAIVERS = Path("/app/frontend/src/lovable/pages/Waivers.tsx")


def test_cancel_button_wired_to_delete_endpoint():
    src = WAIVERS.read_text()
    assert "const handleCancelClaim = async (claimId: string) =>" in src
    assert "await api.delete(`/waivers/claims/${claimId}`);" in src
    # And the button hooks up to it (per-claim testid for QA).
    assert "data-testid={`waiver-claim-cancel-${claim.id}`}" in src
    assert "onClick={() => handleCancelClaim(String(claim.id))}" in src
    # Optimistic local removal + authoritative refresh.
    assert "setLiveClaims((prev) => prev.filter" in src


def test_available_players_search_filter_present():
    """Free-text filter on name / NHL team / position."""
    src = WAIVERS.read_text()
    assert 'placeholder="Search by player name, NHL team, or position…"' in src
    assert 'data-testid="waiver-available-search"' in src
    # Filter clears the value and re-renders the full slice.
    assert 'data-testid="waiver-available-search-clear"' in src
    # Filter is applied BEFORE the 20-row slice so matches outside
    # the default top-20 still surface.
    assert "const q = availableSearch.trim().toLowerCase();" in src
    assert "filtered.slice(0, 20)" in src
    # Count badge so QA can scriptably check filter effect.
    assert 'data-testid="waiver-available-count"' in src


def test_empty_state_copy_for_all_three_tabs():
    src = WAIVERS.read_text()
    assert 'data-testid="waiver-available-empty"' in src
    assert 'data-testid="waiver-my-claims-empty"' in src
    assert 'data-testid="waiver-history-empty"' in src
    # Available-tab empty state differentiates between "no players
    # match the active search" and "no waiver players at all".
    assert "No available players match" in src
    assert "No waiver claims have been processed" in src


def test_drop_player_selector_inside_claim_modal():
    """Iter 180 — picking the drop player no longer requires
    navigating away. The modal renders a <select> populated from
    the owner's actual roster."""
    src = WAIVERS.read_text()
    assert 'data-testid="precheck-drop-picker"' in src
    assert 'data-testid="precheck-drop-select"' in src
    assert "const [dropPlayerId, setDropPlayerId] = useState" in src
    assert "const [myRoster, setMyRoster] = useState" in src
    # On submit we POST the selected drop_player_id when applicable.
    assert "if (precheck?.requires_drop && dropPlayerId) {" in src
    assert "body.drop_player_id = dropPlayerId;" in src
    # The "manage roster directly" escape hatch is still available
    # but is now a tertiary action, not the only option.
    assert 'data-testid="precheck-proceed-to-drop"' in src

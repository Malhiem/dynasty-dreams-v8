"""Iter 231z — `/teams-owners` route now wires the live TeamsTab.

Recurring user report: "Revoke invite continues to not work in League
Administration > Teams & Owners". Root cause was that the sidebar route
`/teams-owners` pointed at `pages/TeamsOwners.tsx`, which was a mocked
stub from iter 226 — hardcoded `initialOwners = [{teamName: "Arctic
Wolves"...}, ...]` array with NO API calls. The trash button only
mutated local React state.

The real, API-backed revoke flow has lived in `components/admin/TeamsTab`
since iter 228z (and was hardened in iter 231p with the AlertDialog UX).
This iter rewires the sidebar route to render that same TeamsTab so the
"Teams & Owners" link in the sidebar finally drives the correct UX.
"""
from pathlib import Path

TEAMS_OWNERS_PAGE = Path("/app/frontend/src/lovable/pages/TeamsOwners.tsx")
TEAMS_TAB = Path("/app/frontend/src/lovable/components/admin/TeamsTab.tsx")


def test_teams_owners_page_no_longer_uses_mocked_initial_data():
    """The stub `initialOwners` array (12 teams: Arctic Wolves, Blizzard
    Kings, ...) must be GONE — that was the source of the silent-revoke
    bug. Allow the rationale comment to mention `initialOwners` once
    (the iter 231z explanation block) but no live code references."""
    src = TEAMS_OWNERS_PAGE.read_text()
    # Mock team names must be gone entirely.
    assert "Arctic Wolves" not in src
    assert "Mike Johnson" not in src
    assert "loginCount" not in src
    # And the local-state removal handler must be gone.
    assert "handleRemoveOwner" not in src
    # The `initialOwners` symbol can appear ONCE inside the rationale
    # comment block, but never as a JS identifier (i.e. no `=`).
    assert "const initialOwners" not in src
    assert "initialOwners = [" not in src


def test_teams_owners_page_renders_live_teams_tab():
    src = TEAMS_OWNERS_PAGE.read_text()
    assert 'import TeamsTab from "@/lovable/components/admin/TeamsTab"' in src
    assert "<TeamsTab" in src
    # Smoke testid for the testing agent to drive the route.
    assert 'data-testid="teams-owners-page"' in src


def test_teams_tab_still_owns_the_revoke_flow():
    """Sanity guard: the AlertDialog + DELETE /api/team-invites/{id}
    integration must continue to live in TeamsTab so the page wrapper
    inherits it."""
    src = TEAMS_TAB.read_text()
    assert "setRevokeTarget" in src
    assert "AlertDialog" in src
    assert "/team-invites/" in src
    assert 'data-testid="teams-tab-revoke-dialog"' in src
    assert 'data-testid="teams-tab-revoke-confirm"' in src
    assert 'data-testid="teams-tab-revoke-cancel"' in src


def test_revoke_button_data_testid_pattern_unchanged():
    """The testing agent + any external test fixtures depend on the
    `teams-tab-invite-revoke-{inv.id}` testid pattern. Lock it in."""
    src = TEAMS_TAB.read_text()
    assert "`teams-tab-invite-revoke-${inv.id}`" in src

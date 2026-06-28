"""Iter 231p — Sidebar collapsible/reorderable groups + revoke-invite UX hardening.

Frontend-only iter (sidebar + admin tab). The tests in this file are
file-introspection guards rather than live HTTP / Playwright tests
because the behaviour is visual + localStorage-driven; the testing
agent already validates the end-to-end interaction.
"""
from pathlib import Path

SIDEBAR = Path("/app/frontend/src/components/layout/AppSidebar.jsx")
TEAMS_TAB = Path("/app/frontend/src/lovable/components/admin/TeamsTab.tsx")
OWNER_INVITES = Path("/app/frontend/src/lovable/pages/commissioner/OwnerInvites.tsx")


# ─── Sidebar collapsible + reorder ────────────────────────────────


def test_sidebar_persists_order_and_collapsed_to_localstorage():
    src = SIDEBAR.read_text()
    assert 'SIDEBAR_GROUPS_LS_ORDER = "dd_sidebar_group_order_v1"' in src
    assert 'SIDEBAR_GROUPS_LS_COLLAPSED = "dd_sidebar_group_collapsed_v1"' in src
    # Both load functions defend against bad / missing data.
    assert "function loadOrder()" in src
    assert "function loadCollapsed()" in src


def test_sidebar_default_order_matches_known_groups():
    src = SIDEBAR.read_text()
    assert (
        'DEFAULT_GROUP_ORDER = ["league_hub", "social", "team_mgmt", "draft"]' in src
    )


def test_sidebar_renders_collapsible_header_with_chevrons():
    src = SIDEBAR.read_text()
    # Header toggle button + the two chevron states.
    assert 'data-testid={`sidebar-group-toggle-${group.key}`}' in src
    assert "ChevronDown" in src and "ChevronRight" in src
    # aria-expanded mirrors the open/closed state.
    assert "aria-expanded={!isCollapsed}" in src


def test_sidebar_groups_are_draggable_and_handle_visible():
    src = SIDEBAR.read_text()
    # draggable + HTML5 drag handlers wired.
    assert "draggable={!collapsed}" in src
    assert "onDragStart={onDragStart(group.key)}" in src
    assert "onDragOver={onDragOver(group.key)}" in src
    assert "onDragEnd={onDragEnd}" in src
    # GripVertical handle is rendered (visible on hover).
    assert "GripVertical" in src


def test_user_and_league_dropdown_remain_pinned():
    src = SIDEBAR.read_text()
    # User + CurrentLeagueDropdown are rendered OUTSIDE the reorderable
    # map — they stay at the top regardless of how user reorders the
    # rest. The fixed-position renderStaticGroup is used for "User".
    assert "renderStaticGroup(\"User\"" in src
    assert "<CurrentLeagueDropdown collapsed={collapsed} />" in src


# ─── Revoke invite — TeamsTab ─────────────────────────────────────


def test_teams_tab_revoke_uses_alert_dialog():
    """The old `window.confirm` was unreliable in some embedded
    browsers — replaced with shadcn AlertDialog."""
    src = TEAMS_TAB.read_text()
    assert "AlertDialog," in src
    assert "AlertDialogAction" in src and "AlertDialogCancel" in src
    assert 'data-testid="teams-tab-revoke-dialog"' in src
    assert 'data-testid="teams-tab-revoke-confirm"' in src
    assert 'data-testid="teams-tab-revoke-cancel"' in src
    # State variable that drives the dialog open/close lifecycle.
    assert "const [revokeTarget, setRevokeTarget] = useState(null);" in src
    # Old confirm() path is gone.
    assert 'window.confirm("Revoke this invite link?")' not in src


def test_teams_tab_revoke_guards_missing_id():
    """Defensive guard against malformed invite docs ("nothing happens"
    silent fail when `inv.id` was undefined)."""
    src = TEAMS_TAB.read_text()
    assert "if (!inv?.id)" in src
    assert 'invite id missing' in src


def test_owner_invites_also_guards_missing_id():
    src = OWNER_INVITES.read_text()
    assert "if (!inv?.id)" in src
    assert 'invite id missing' in src

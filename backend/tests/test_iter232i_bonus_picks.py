"""Iter 232i — Commissioner-granted bonus draft picks.

User story: "As a league admin, I would like the ability to grant
compensation or expansion draft picks so that I can cover edge cases
and situations where compensation or expansion picks may be needed."

Acceptance criteria (from the user's request):
  • Settings should be configurable in League Administration > Draft.
    → Delivered via the Edit Draft dialog's new `<BonusPicksSection>`.
  • It should be set while scheduling an upcoming draft AND can be
    done mid-draft.
    → Backend allows adds/removes for positions > current_pick.
  • Admin determines how many picks, what teams receive them, and
    when they occur in a draft.
    → Position mode is `end_of_round` OR `overall` (both supported).
  • Tradeability — admin decides per pick.
    → `tradeable: bool` field on each pick.

Design notes:
  • Bonus picks live on the draft doc as `draft.bonus_picks[]` so
    the engine has O(1) access. When the draft has pick trading
    enabled, we ALSO mirror the pick into the `draft_picks`
    collection so the trade center can operate on it.
  • `get_team_for_pick(...)` in `draft_engine.py` now takes an
    optional `bonus_picks` arg. When supplied:
      - Exact-overall match → the bonus team is on the clock.
      - Otherwise the pick's *effective* position (overall minus
        the count of prior bonuses) is used for the standard snake
        formula so the underlying round order is preserved.
  • `total_picks_in_draft(...)` accounts for bonus extras so the
    "draft complete" transition doesn't fire early.
"""
from pathlib import Path


ROUTER = Path("/app/backend/routes/draft_bonus_picks.py")
ENGINE = Path("/app/backend/draft_engine.py")
PICK_ACTIONS = Path("/app/backend/routes/draft_pick_actions.py")
SERVER = Path("/app/backend/server.py")
FE_SECTION = Path("/app/frontend/src/lovable/pages/commissioner/BonusPicksSection.tsx")
FE_DIALOG = Path("/app/frontend/src/lovable/pages/commissioner/EditDraftDialog.tsx")
FE_TAB = Path("/app/frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx")


# ─── Backend engine ─────────────────────────────────────────────────


def test_engine_get_team_for_pick_accepts_bonus_picks():
    src = ENGINE.read_text()
    # New optional argument.
    assert "bonus_picks: Optional[list[dict]] = None" in src
    # Exact-match returns the bonus team directly.
    assert 'if int(bp.get("overall", 0)) == overall_pick:' in src
    # Effective-pick offset (count of bonuses BEFORE this position).
    assert "offset = sum(1 for bp in bonus_picks if int(bp.get" in src
    assert "effective_pick = overall_pick - offset" in src


def test_engine_total_picks_helper_exists():
    src = ENGINE.read_text()
    assert "def total_picks_in_draft(" in src
    # Bonuses add to the base.
    assert "extras = len(bonus_picks or [])" in src
    assert "return base + extras" in src


def test_pick_actions_thread_bonus_picks_through_every_get_team_for_pick_call():
    """All calls to `get_team_for_pick` in the pick-actions router
    must now pass `draft.get('bonus_picks')` so the engine can honour
    them. Any missed call site would silently under-report which team
    is on the clock during a bonus-heavy draft."""
    src = PICK_ACTIONS.read_text()
    # Count all invocations — the `from ...` import doesn't count.
    lines = [l for l in src.splitlines() if "get_team_for_pick(" in l and "from " not in l]
    assert len(lines) >= 6, f"expected >=6 call sites, got {len(lines)}"
    for line in lines:
        assert "bonus_picks" in line, f"missing bonus_picks in: {line.strip()}"


def test_pick_actions_total_picks_accounts_for_bonuses():
    src = PICK_ACTIONS.read_text()
    # Total-picks computation now adds bonus extras.
    assert 'total_picks = draft["total_rounds"] * total_teams + len(draft.get("bonus_picks") or [])' in src


# ─── Backend router ─────────────────────────────────────────────────


def test_router_registered_in_server():
    src = SERVER.read_text()
    # Import.
    assert "draft_bonus_picks as draft_bonus_picks_routes" in src
    # Setup + include.
    assert "draft_bonus_picks_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_bonus_picks_routes.router)" in src


def test_router_exposes_get_post_delete_endpoints():
    src = ROUTER.read_text()
    assert '@router.get("/drafts/{draft_id}/bonus-picks")' in src
    assert '@router.post("/drafts/{draft_id}/bonus-picks")' in src
    assert '@router.delete("/drafts/{draft_id}/bonus-picks/{bonus_id}")' in src


def test_router_authorizes_commissioner_only():
    src = ROUTER.read_text()
    # Both routes share `_load_draft_and_authorise`.
    assert "async def _load_draft_and_authorise(" in src
    assert 'league.get("commissioner_id") != user["_id"]' in src
    assert '"co_commissioners"' in src


def test_router_validates_request_body_with_pydantic():
    src = ROUTER.read_text()
    assert 'Literal["compensation", "expansion"]' in src
    assert 'Literal["end_of_round", "overall"]' in src
    # Position-specific field validation raises 422 with clear detail.
    assert "after_round is required for end_of_round mode" in src
    assert "overall_position is required for overall mode" in src


def test_router_blocks_inserts_at_or_before_current_pick_in_active_drafts():
    """Guardrail — a commissioner can't insert a bonus pick at a
    position that's already passed. The server returns 409 with a
    clear message so the UI can show it in a toast."""
    src = ROUTER.read_text()
    assert 'if overall <= current_pick and draft.get("status") == "active":' in src
    assert "409" in src
    assert "already on pick" in src


def test_router_shifts_existing_picks_when_inserting_or_removing():
    src = ROUTER.read_text()
    # Insert: existing bonuses at overall >= new pos shift up.
    assert "def _shift_bonus_and_picks(" in src
    assert 'bp2["overall"] = ov + 1' in src
    # Delete: everything > deleted overall shifts down.
    assert 'bp2["overall"] = int(bp2["overall"]) - 1' in src
    # draft_picks collection also shifts when pick trading is on.
    assert '"draft_id": draft_id, "overall": {"$gte": overall}' in src
    assert '{"$inc": {"overall": 1}}' in src
    assert '{"$inc": {"overall": -1}}' in src


def test_router_mirrors_tradeable_bonus_into_draft_picks_collection():
    src = ROUTER.read_text()
    assert 'trading_on = bool(draft.get("pick_trading_enabled"))' in src
    assert 'await _db().draft_picks.insert_one(' in src
    assert '"is_bonus": True' in src


# ─── Frontend section ───────────────────────────────────────────────


def test_frontend_bonus_picks_section_supports_both_modes():
    src = FE_SECTION.read_text()
    # Both position modes are wired.
    assert 'data-testid="bonus-pick-mode-end-of-round"' in src
    assert 'data-testid="bonus-pick-mode-overall"' in src
    # Both position inputs render based on mode.
    assert 'data-testid="bonus-pick-after-round-input"' in src
    assert 'data-testid="bonus-pick-overall-input"' in src


def test_frontend_bonus_picks_section_supports_both_kinds():
    src = FE_SECTION.read_text()
    assert 'data-testid="bonus-pick-kind-compensation"' in src
    assert 'data-testid="bonus-pick-kind-expansion"' in src


def test_frontend_bonus_picks_section_supports_admin_set_tradeability_and_note():
    src = FE_SECTION.read_text()
    assert 'data-testid="bonus-pick-tradeable-checkbox"' in src
    assert 'data-testid="bonus-pick-note-input"' in src


def test_frontend_bonus_picks_section_hides_delete_for_used_picks():
    src = FE_SECTION.read_text()
    # "used" tag renders and the delete X is gated behind `!alreadyUsed`.
    assert "const alreadyUsed = draftStatus" in src
    assert "p.overall <= currentPick" in src
    assert "{!alreadyUsed && (" in src


def test_edit_draft_dialog_mounts_bonus_picks_section_when_context_supplied():
    src = FE_DIALOG.read_text()
    assert 'import BonusPicksSection from "@/lovable/pages/commissioner/BonusPicksSection";' in src
    assert "<BonusPicksSection" in src
    # Section only renders when the parent wires the required context.
    assert "{draftId && leagueTeams && Array.isArray(leagueTeams) && (" in src


def test_draft_tab_wires_context_to_edit_dialog():
    src = FE_TAB.read_text()
    # Editing meta state (current_pick + status) captured on open.
    assert "editingDraftMeta" in src
    # And passed to the dialog.
    assert "draftId={editingDraftId || undefined}" in src
    assert "leagueTeams={lotteryTeams}" in src
    assert "currentPick={editingDraftMeta?.currentPick}" in src
    assert "draftStatus={editingDraftMeta?.status}" in src

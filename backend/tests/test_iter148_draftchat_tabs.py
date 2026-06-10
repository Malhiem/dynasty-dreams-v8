"""Iter 148 — Draft Room chat tab split + vote wiring static checks.

Pytest-friendly file-content assertions to lock in:
  - DraftChatPanel exists with the 3 tab testids.
  - DraftRoom mounts DraftChatPanel and removed the old inline chat block.
  - api.js has dedupe cache for /leagues?my_leagues=true and /teams?league_id=.
  - SetupWizard moved HelpTooltips out of Button children.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_draft_chat_panel_file_present():
    src = _read("lovable/pages/draftroom/DraftChatPanel.tsx")
    # All three tab testids
    for tid in ("draft-chat-tab-all", "draft-chat-tab-chat", "draft-chat-tab-trades"):
        assert f'data-testid="{tid}"' in src, f"Missing tab testid: {tid}"
    # Vote buttons on a trade row use template ids
    assert 'data-testid={`draft-chat-trade-approve-${tradeId}`}' in src
    assert 'data-testid={`draft-chat-trade-veto-${tradeId}`}' in src
    # Status stamps
    assert "PROCESSED" in src and "VETOED" in src and "CANCELLED" in src
    # Pending stamp + veto meter
    assert 'data-testid={`draft-chat-trade-pending-${tradeId}`}' in src
    assert 'data-testid={`draft-chat-trade-veto-meter-${tradeId}`}' in src
    # Commish override
    assert 'data-testid={`draft-chat-trade-force-approve-${tradeId}`}' in src
    assert 'data-testid={`draft-chat-trade-force-veto-${tradeId}`}' in src
    # Calls the existing backend vote endpoint
    assert "/trades/${tradeId}/vote" in src
    assert "/trades/${tradeId}/execute" in src
    # Reads the league's veto threshold
    assert "/veto-threshold-preview" in src


def test_draft_room_mounts_chat_panel_and_removes_old_block():
    src = _read("lovable/pages/DraftRoom.tsx")
    assert "import DraftChatPanel from" in src
    assert "<DraftChatPanel" in src
    # Old inline chat title must be gone
    assert "Draft Chat\n                  </CardTitle>" not in src
    # Props plumbed
    for prop in ("chatMessages=", "chatInput=", "setChatInput=", "onSendChat=", "leagueId=", "myUserId=", "isCommissioner=", "league="):
        assert prop in src, f"Missing prop on DraftChatPanel: {prop}"


def test_api_client_has_dedupe_cache_for_hot_endpoints():
    src = _read("lib/api.js")
    # Patterns we expect to dedupe
    assert "my_leagues=true" in src
    assert "teams?league_id=" in src
    # Core wiring
    assert "INFLIGHT_GETS" in src
    assert "GET_CACHE" in src
    assert "CACHE_TTL_MS" in src
    # Public invalidator export
    assert "export function invalidateApiCache" in src


def test_setup_wizard_help_tooltips_outside_buttons():
    src = _read("lovable/pages/commissioner/SetupWizard.jsx")
    # The Set Up Later / Skip buttons must no longer wrap a HelpTooltip
    later_idx = src.index('data-testid="wizard-setup-later-btn"')
    skip_idx = src.index('data-testid="wizard-skip-btn"')
    # Slice from the testid to the first </Button> after it and assert no HelpTooltip in between
    later_chunk = src[later_idx : src.index("</Button>", later_idx)]
    skip_chunk = src[skip_idx : src.index("</Button>", skip_idx)]
    assert "HelpTooltip" not in later_chunk
    assert "HelpTooltip" not in skip_chunk
    # And the tooltips still exist (as siblings)
    assert 'testId="help-set-up-later"' in src
    assert 'testId="help-skip"' in src

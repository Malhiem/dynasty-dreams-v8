"""Iter 123 — Frontend gap fixes after iter122 testing-agent feedback.

Coverage
--------
1. Waivers.tsx now imports + renders an anonymous-mode banner
   (`waiver-anonymous-mode` testid) gated by `isAnonymousMode`.
2. WaiverPriorityOrderCard.tsx exposes an explicit `waiver-next-team-up`
   testid + crown highlight on rank-1 visible to all viewers.
3. OperationsConsole.tsx exposes a `health-deep-section` wrapper testid
   plus per-route latency override editor (`latency-threshold-input-{route}`).

These are file-presence assertions only — runtime + interaction coverage
is handled by the playwright smoke-test loop and the iter122 backend
tests for the anonymous claim-count + waiver-priority envelopes.
"""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
WAIVERS_TSX = REPO / "frontend/src/lovable/pages/Waivers.tsx"
WPRIO_TSX = REPO / "frontend/src/lovable/components/dashboard/WaiverPriorityOrderCard.tsx"
OPS_TSX = REPO / "frontend/src/lovable/pages/site-admin/OperationsConsole.tsx"


def test_waivers_anonymous_banner_present():
    src = WAIVERS_TSX.read_text()
    assert "waiver-anonymous-mode" in src, "Anonymous-mode banner testid missing"
    assert "isAnonymousMode" in src, "isAnonymousMode flag not derived"
    assert "all_teams_anonymous" in src, "Anonymous audience literal missing"
    assert "maskTeamName" in src, "Team-name masking helper missing"


def test_waiver_priority_card_next_team_up():
    src = WPRIO_TSX.read_text()
    assert "waiver-next-team-up" in src, "next-team-up testid missing"
    assert "waiver-next-team-up-name" in src, "next-team-up-name testid missing"
    assert "Next up" in src or "NEXT UP" in src.upper(), "'Next up' label missing"
    # Crown icon for rank #1 visible to all viewers
    assert "Crown" in src, "Crown icon import for rank-1 missing"


def test_ops_console_per_route_overrides_present():
    src = OPS_TSX.read_text()
    assert "health-deep-section" in src, "health-deep-section testid missing"
    assert "ops-per-route-section" in src, "per-route section testid missing"
    assert "ops-per-route-table" in src, "per-route table testid missing"
    assert "latency-threshold-input-" in src, "per-route input testid missing"
    assert "thresholdsForRoute" in src, "per-route threshold helper missing"
    assert "per_route" in src, "per_route override storage key missing"

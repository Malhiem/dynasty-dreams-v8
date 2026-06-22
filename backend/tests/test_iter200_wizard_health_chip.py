"""
Iter 200 — Wizard footer Health chip.

Source-invariant tests to guard against accidental regression of the
HealthChip component + its integration in the SetupWizard footer.
"""
from pathlib import Path


def _src() -> str:
    p = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lovable" / "pages" / "commissioner" / "SetupWizard.jsx"
    return p.read_text()


def test_health_chip_component_exported():
    s = _src()
    assert "function HealthChip(" in s, "HealthChip component missing"


def test_health_chip_rendered_in_footer():
    s = _src()
    assert "wizard-health-chip" in s, "HealthChip testid missing from wizard footer"
    assert "wizard-health-score" in s, "HealthChip score testid missing"
    assert "wizard-health-steps" in s, "HealthChip steps testid missing"


def test_stamp_progress_refreshes_health():
    """After stampProgress succeeds, refreshHealth() must be called so the
    chip animates on every save."""
    s = _src()
    # Look for the call inside stampProgress
    assert "await refreshHealth();" in s, "refreshHealth missing — chip will not bump after save"


def test_bump_animation_present():
    s = _src()
    assert "animate-ping" in s or "scale-110" in s, "Flash/bump animation missing on HealthChip"


def test_chip_color_tiers_present():
    """Verify the emerald/cyan/amber/rose progression so the chip visibly
    changes color as the score climbs."""
    s = _src()
    for tier in ["emerald", "cyan", "amber", "rose"]:
        assert tier in s, f"Color tier '{tier}' missing from HealthChip palette"

"""Iter 232d — Chat-tab bubble pulses on count increase.

User: "Make the Chat-tab bubble subtly pulse for ~3 seconds when the
count goes up (a manager just came online), so users feel the social
signal instead of having to glance at the number. Same socket data —
just a CSS animation triggered on a count-increase ref-compare."

Implementation:
  • `useRef` for the previous count value + `useState` for the
    `pulsing` boolean.
  • On every count change, the effect compares `prev` vs `next`; only
    a strict increase (`next > prev`) triggers the pulse. Decreases,
    equal values, and the very first observation (baseline) do NOT
    pulse — otherwise users would see a mystery pulse on page load.
  • Pulse duration is 3s (three 1.2s iterations of a ring-halo +
    subtle scale animation). Falls back to a static ring when the
    user has `prefers-reduced-motion: reduce`.
  • `data-pulsing="true"|"false"` on the bubble so Playwright can
    assert the state without inspecting CSS animations.
"""
from pathlib import Path


NAV = Path("/app/frontend/src/components/MobileBottomNav.jsx")
CSS = Path("/app/frontend/src/index.css")


def test_pulse_state_and_ref_compare_wired():
    src = NAV.read_text()
    # Ref for the previous count value.
    assert "prevCountRef = useRef(null);" in src
    # Boolean UI state driving the animation class.
    assert "const [pulsing, setPulsing] = useState(false);" in src
    # Baseline observation (first non-null) does NOT pulse — otherwise
    # every page load flashes the icon.
    assert "if (prev === null) return undefined;" in src
    # Only pulse on strict increase.
    assert "if (onlineCount > prev)" in src


def test_pulse_duration_matches_user_spec():
    """The user asked for '~3 seconds'. Verify the constant is 3000 ms
    so future tweaks don't silently regress the perception window."""
    src = NAV.read_text()
    assert "const PULSE_MS = 3000;" in src
    # setTimeout wired to the same constant.
    assert "setTimeout(() => setPulsing(false), PULSE_MS);" in src


def test_pulse_class_and_testid_on_bubble():
    src = NAV.read_text()
    # Animation class conditionally applied.
    assert 'pulsing && "mobile-nav-chat-pulse"' in src
    # data-pulsing attribute for Playwright.
    assert 'data-pulsing={pulsing ? "true" : "false"}' in src


def test_pulse_keyframes_defined_with_reduced_motion_fallback():
    src = CSS.read_text()
    # Two keyframes — ring halo + gentle scale — so the effect feels
    # like an "arrival" rather than a distracting flash.
    assert "@keyframes mobileNavChatPulseRing" in src
    assert "@keyframes mobileNavChatPulseScale" in src
    # Class fires three iterations of both animations (~3s total to
    # match `PULSE_MS`).
    assert ".mobile-nav-chat-pulse {" in src
    assert "mobileNavChatPulseRing 1.2s ease-out 0s 3" in src
    assert "mobileNavChatPulseScale 1.2s ease-in-out 0s 3" in src
    # Accessibility — reduced-motion users see a static ring instead.
    assert "@media (prefers-reduced-motion: reduce)" in src
    assert "animation: none;" in src

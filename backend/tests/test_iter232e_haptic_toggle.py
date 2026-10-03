"""Iter 232e — Haptic buzz on "manager came online", gated by a
Preferences toggle.

User: "Layer a haptic buzz (via navigator.vibrate?.(30)) alongside
the pulse when someone comes online, gated behind a Preferences
toggle. Same trigger point — a subtle 30ms tap on the wrist would
make the app feel genuinely alive during draft night or a hot trade
window without adding any new backend surface."

Implementation:
  • New `use-haptic-preference.ts` hook + `triggerHaptic()` helper.
    Preference persists in `localStorage['dd-haptics']`. Defaults to
    ON when `navigator.vibrate` is available and the user hasn't
    opted out. Guarded against `prefers-reduced-motion`.
  • `MobileBottomNav.jsx` fires `triggerHaptic(30)` alongside the
    existing 3-second pulse at the same ref-compare trigger point
    (strict increase in `onlineCount`).
  • `AppPreferencesMenu.jsx` renders a new "Haptic buzz on live
    events" toggle under an "Alerts" group. Toggle only surfaces
    when the device actually supports `navigator.vibrate` — hiding
    the row prevents a dangling UI knob on desktop browsers.
"""
from pathlib import Path


HOOK = Path("/app/frontend/src/hooks/use-haptic-preference.ts")
NAV = Path("/app/frontend/src/components/MobileBottomNav.jsx")
PREFS = Path("/app/frontend/src/components/layout/AppPreferencesMenu.jsx")


def test_haptic_hook_exports_helper_and_hook():
    src = HOOK.read_text()
    # Both public entry points present.
    assert "export function useHapticPreference()" in src
    assert "export function triggerHaptic(" in src
    # Persistent storage key is stable.
    assert 'const LS_KEY = "dd-haptics";' in src


def test_haptic_hook_gracefully_handles_unsupported_browsers():
    src = HOOK.read_text()
    # `supported` flag drives UI + no-op behaviour.
    assert "function hasVibrateApi()" in src
    assert 'typeof navigator.vibrate === "function"' in src
    # `triggerHaptic` short-circuits when the API is missing OR the
    # user has explicitly opted out OR reduced-motion is on.
    assert "if (!hasVibrateApi()) return false;" in src
    assert "if (prefersReducedMotion()) return false;" in src
    assert "if (stored === false) return false;" in src


def test_haptic_hook_confirmation_buzz_on_enable():
    """Firing a short buzz the moment the user turns the toggle on
    gives instant hardware-works feedback. Must be gated by the
    same accessibility checks as the main path."""
    src = HOOK.read_text()
    assert "if (v && supported && !prefersReducedMotion())" in src
    assert "navigator.vibrate(30);" in src


def test_haptic_hook_syncs_cross_tab():
    """Second tab flipping the preference should sync into the first
    tab without a page reload."""
    src = HOOK.read_text()
    assert 'window.addEventListener("storage", onStorage);' in src
    assert 'e.key !== LS_KEY' in src


def test_mobile_bottom_nav_fires_haptic_alongside_pulse():
    src = NAV.read_text()
    # Import.
    assert 'import { triggerHaptic } from "@/hooks/use-haptic-preference";' in src
    # Fires at the SAME trigger point as the pulse — a strict count
    # increase. The user was clear this should reuse the existing
    # ref-compare, not spawn a separate socket handler.
    assert "if (onlineCount > prev)" in src
    # 30 ms matches the user's spec ("a subtle 30ms tap on the wrist").
    assert "triggerHaptic(30);" in src


def test_preferences_menu_renders_haptic_toggle():
    src = PREFS.read_text()
    # Import.
    assert 'import { useHapticPreference } from "@/hooks/use-haptic-preference";' in src
    # Toggle DOM.
    assert 'data-testid="prefs-haptics-toggle"' in src
    # The row only renders when the device supports vibration —
    # avoids a UI knob that can't do anything on desktop.
    assert "{hapticsSupported && (" in src
    # ACTIVE badge when on (matches the theme toggle pattern).
    assert 'data-testid="prefs-haptics-active"' in src
    # Human-readable copy so users understand what the toggle does.
    assert "A tiny wrist tap when a manager comes online" in src

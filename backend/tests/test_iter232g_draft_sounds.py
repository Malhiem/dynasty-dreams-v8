"""Iter 232g — Draft-sounds chirps paired with iter 232f haptics.

User: "Layer a small audio chirp alongside these draft haptics (a
soft 'ding' at pick start, a slightly urgent 'buzz' tone in the
final 10s), gated by the same Preferences toggle plus a separate
'Draft sounds' volume."

Implementation:
  • `lib/draft-sounds.ts` — synthesizes both tones with Web Audio
    (no external audio files → no bundle bloat, no CORS/SW
    concerns). Shared `AudioContext` singleton, iOS-Safari
    `ensureAudioUnlocked()` on the Preferences toggle click.
  • Preference API:
      - `areDraftSoundsEnabled()` (default OFF; audio is more
        intrusive than haptics, must be explicitly opted in)
      - `setDraftSoundsEnabled(bool)`
      - `getDraftSoundsVolume()` (default 60)
      - `setDraftSoundsVolume(0–100)`
  • Two playback helpers:
      - `playDing()` — sine-wave C5 → G5 glide, ~250ms, gentle ADSR
      - `playBuzz()` — three 80ms square-wave pulses on A3
    Both no-op when the toggle is off, volume is 0, the OS has
    `prefers-reduced-motion: reduce`, or the AudioContext is
    suspended (iOS pre-gesture).
  • Wired into `DraftRoom.tsx` alongside the existing iter 232f
    haptic triggers — same event, one line each. Zero new state.
  • `AppPreferencesMenu.jsx` gains a "Draft sounds" toggle + inline
    volume slider (with a Test button to preview). The toggle
    fires a preview `playDing()` on enable so users can gauge
    volume against their environment immediately.
"""
from pathlib import Path


LIB = Path("/app/frontend/src/lib/draft-sounds.ts")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
PREFS = Path("/app/frontend/src/components/layout/AppPreferencesMenu.jsx")


def test_draft_sounds_lib_exposes_public_surface():
    src = LIB.read_text()
    # Preference getters/setters + two play helpers + unlock hook.
    for name in [
        "export function ensureAudioUnlocked",
        "export function areDraftSoundsEnabled",
        "export function setDraftSoundsEnabled",
        "export function getDraftSoundsVolume",
        "export function setDraftSoundsVolume",
        "export function playDing",
        "export function playBuzz",
    ]:
        assert name in src, f"missing export: {name}"


def test_draft_sounds_default_off_and_default_volume_60():
    """Audio is more intrusive than haptics — default OFF forces an
    explicit opt-in. Default volume 60 is loud enough to hear in a
    room without startling anyone."""
    src = LIB.read_text()
    # Enabled getter returns false when the key is missing.
    assert 'return raw === "true";' in src
    # Volume getter returns 60 fallback.
    assert "return 60; // sensible default" in src
    # Volume clamped to [0,100].
    assert "Math.min(100, Math.max(0, parsed))" in src


def test_draft_sounds_lib_gates_accessibility_and_context_state():
    src = LIB.read_text()
    # `preparePlayback` is the common gate — must check enabled,
    # non-zero volume, reduced-motion, and non-suspended context.
    assert "if (!areDraftSoundsEnabled()) return null;" in src
    assert "if (rawVol <= 0) return null;" in src
    assert '"(prefers-reduced-motion: reduce)"' in src
    assert 'c.state === "suspended"' in src


def test_ding_and_buzz_use_web_audio_primitives():
    src = LIB.read_text()
    # Ding: sine oscillator with C5 → G5 glide.
    assert 'osc.type = "sine";' in src
    assert "osc.frequency.setValueAtTime(523.25, now);" in src
    assert "osc.frequency.linearRampToValueAtTime(783.99" in src
    # Buzz: three 80ms square-wave pulses on A3.
    assert 'osc.type = "square";' in src
    assert "const pulses = 3;" in src
    assert "const pulseLen = 0.08;" in src
    assert "osc.frequency.setValueAtTime(220, start);" in src


def test_draft_room_pairs_audio_with_haptics():
    src = DRAFT_ROOM.read_text()
    # Import from the audio lib.
    assert 'import { playDing, playBuzz } from "@/lib/draft-sounds";' in src
    # Pick-start pairs playDing with triggerHaptic(30).
    assert "triggerHaptic(30);" in src
    assert "playDing();" in src
    # Final-10s pairs playBuzz with the [80,80,80,80,80] haptic.
    assert "triggerHaptic([80, 80, 80, 80, 80]);" in src
    assert "playBuzz();" in src


def test_prefs_menu_renders_sounds_toggle_and_volume():
    src = PREFS.read_text()
    # Imports.
    assert 'from "@/lib/draft-sounds"' in src
    assert "import { Slider }" in src
    # Toggle row + slider row.
    assert 'data-testid="prefs-sounds-toggle"' in src
    assert 'data-testid="prefs-sounds-volume-slider"' in src
    # Preview button so users can gauge volume without waiting for
    # a live draft event.
    assert 'data-testid="prefs-sounds-preview"' in src
    # Volume slider is hidden when the sounds toggle is OFF so we
    # don't dangle a knob that can't be heard.
    assert "{soundsEnabled && (" in src
    # Human-readable copy.
    assert "Soft ding at pick start, urgent buzz in final 10s" in src

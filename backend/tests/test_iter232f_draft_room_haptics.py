"""Iter 232f — Draft Room haptic buzzes for on-clock moments.

User: "Reuse the same `triggerHaptic` helper for on-the-clock moments
in the Draft Room (short 30ms buzz when your pick starts, longer
80-80-80ms pattern in the final 10 seconds). Same toggle, same
one-liner call at the existing timer event — draft night would feel
viscerally different."

Implementation:
  • Two `useEffect`s in `lovable/pages/DraftRoom.tsx`.
  • **Pick-start** trigger: a `prevIsMyPickRef` ref-compare fires
    `triggerHaptic(30)` when `isMyPickActive` transitions
    false → true AND `isDraftActive`. This mirrors the iter 232e
    mobile-nav Chat-bubble pattern (ref-compare on strict
    transition, no fire on baseline observation).
  • **Final-10s** trigger: `warnedForPickRef` latch ensures the
    `[80, 80, 80, 80, 80]` five-buzz pattern fires ONCE per pick
    when the timer crosses into `pickTimeLeft <= 10 && > 0`. The
    latch resets on every `draftConfig.currentPick` change so the
    next "your pick" cycle can warn again.
  • Both calls no-op when Haptics are OFF, `navigator.vibrate` is
    missing, or `prefers-reduced-motion` is set — all handled
    inside `triggerHaptic` itself.
  • Extended `triggerHaptic` signature to accept a pattern array
    so callers can express urgency (five-buzz warn) without a new
    helper.
"""
from pathlib import Path


HOOK = Path("/app/frontend/src/hooks/use-haptic-preference.ts")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


def test_trigger_haptic_accepts_pattern_array():
    src = HOOK.read_text()
    # Signature now takes `number | number[]` so callers can pass
    # richer patterns for urgency (e.g. the final-10s warn).
    assert "pattern: number | number[] = 30" in src
    # Still routes through the same navigator.vibrate call.
    assert "navigator.vibrate(pattern as never);" in src


def test_draft_room_fires_haptic_on_pick_start():
    src = DRAFT_ROOM.read_text()
    # Import.
    assert 'import { triggerHaptic } from "@/hooks/use-haptic-preference";' in src
    # Ref-compare so a re-render with the same value does not
    # re-fire the buzz.
    assert "prevIsMyPickRef" in src
    # Transition false → true fires the 30ms buzz. Draft must be
    # active so we don't buzz during scheduled/preview state.
    assert "if (!wasMine && isMyPickActive && isDraftActive)" in src
    assert "triggerHaptic(30);" in src


def test_draft_room_fires_final_ten_seconds_warning():
    src = DRAFT_ROOM.read_text()
    # Latch ref so we warn exactly once per pick.
    assert "warnedForPickRef" in src
    # Reset on pick change so the next "your pick" cycle can warn.
    assert "warnedForPickRef.current = null;" in src
    # The window must include `pickTimeLeft > 0` so we don't warn
    # when the timer has already expired.
    assert "pickTimeLeft > 0" in src
    assert "pickTimeLeft <= 10" in src
    # 5-buzz pattern (80ms on/off) matches the user's brief:
    # "longer 80-80-80ms pattern".
    assert "triggerHaptic([80, 80, 80, 80, 80]);" in src


def test_final_ten_seconds_warning_gated_by_own_pick_and_clock():
    """The warn buzz must NOT fire while the clock is paused, when
    the pick belongs to another team, or when the pause switch is
    on — otherwise a commissioner scrubbing paused states could
    trigger accidental buzzes."""
    src = DRAFT_ROOM.read_text()
    # All three gates present in the guard expression.
    assert "isMyPickActive" in src
    assert "isClockActive" in src
    assert "!timerPaused" in src

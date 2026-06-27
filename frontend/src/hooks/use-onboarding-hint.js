// @ts-nocheck
/**
 * Iter 230aw — `useOnboardingHint(key)`
 *
 * Returns `[shouldShow, markShown]` for a one-time onboarding hint
 * tied to a localStorage key. Designed for the `<SwipeableRow
 * showOnboardingHint>` pulse so first-time mobile users discover the
 * swipe gestures exist, but the hint never replays for that user.
 *
 * Behaviour:
 *   - `shouldShow` is `true` only when:
 *       (a) localStorage has no entry for `dd_swipe_hint_${key}`
 *       (b) the current pointer is `coarse` (mobile / touch)
 *       (c) we're in a browser (SSR-safe)
 *   - `markShown()` writes the entry so subsequent loads / surfaces
 *     don't pulse again.
 *   - Also auto-marks shown on the first manual swipe of any row in
 *     the surface (caller wires it up from `onSwipeRight` /
 *     `onSwipeLeft`).
 */
import { useState, useCallback } from "react";

const STORAGE_PREFIX = "dd_swipe_hint_";

export default function useOnboardingHint(key) {
  const [shouldShow, setShouldShow] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      if (localStorage.getItem(STORAGE_PREFIX + key)) return false;
    } catch {
      return false;
    }
    // Only hint on touch devices — desktop users discover via dropdown
    // menu / drag-to-reorder, not via swipes.
    if (!window.matchMedia || !window.matchMedia("(pointer: coarse)").matches) {
      return false;
    }
    return true;
  });

  const markShown = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_PREFIX + key, String(Date.now()));
    } catch {
      /* noop */
    }
    setShouldShow(false);
  }, [key]);

  return [shouldShow, markShown];
}

/**
 * Iter 231at — `usePullToRefresh`
 *
 * A lightweight pull-to-refresh primitive for mobile PWA + browser
 * touch surfaces. Listens to `touchstart` / `touchmove` / `touchend`
 * on `document` and only engages when the page is scrolled to the
 * very top — exactly how iOS Safari + native apps gate the gesture.
 *
 * The caller decides what "refresh" means: pass an async callback
 * (data reload, websocket reconnect, mutation reset) and we'll await
 * it before snapping the indicator back. Threshold (px) + max
 * stretch are tunable so different pages can opt into a tighter or
 * loosier pull.
 *
 * Mouse / desktop users see no behavior change — desktop has its own
 * refresh idioms (Ctrl-R, the omnibox reload button) and we don't
 * want random page-top mouse-drags to fire a network call.
 *
 * Iter 232a — fixed two correctness bugs that made the gesture feel
 * "the icon appears but nothing seems to refresh":
 *   1. The previous implementation kept `state.distance` in the
 *      effect's dep array so listeners re-bound on every pixel. That
 *      created a race where `touchend` could fire on a listener whose
 *      closure still held `distance: 0` (the previous render) and
 *      silently abort the refresh. Replaced with a `distanceRef` that
 *      `onEnd` reads synchronously.
 *   2. The minimum visible-refresh window is now enforced (default
 *      450ms) so a fast cached response can't snap the spinner away
 *      before the user perceives it.
 */
import { useEffect, useRef, useState } from "react";

interface Options {
  /** Async function invoked once the threshold is crossed + released. */
  onRefresh: () => Promise<unknown> | unknown;
  /** Pixels of drag needed before a release fires the refresh. */
  threshold?: number;
  /** Max overstretch before the indicator stops following the finger. */
  maxStretch?: number;
  /** Disable entirely (e.g. when a modal is open). */
  enabled?: boolean;
  /** Minimum visible spinner duration in ms (perception floor). */
  minSpinnerMs?: number;
}

interface State {
  /** Distance the indicator should be translated from y=0. */
  distance: number;
  /** True between threshold-crossed and onRefresh resolution. */
  refreshing: boolean;
  /** True for any touch where pullToRefresh has engaged (distance > 0). */
  engaged: boolean;
}

export function usePullToRefresh({
  onRefresh,
  threshold = 70,
  maxStretch = 110,
  enabled = true,
  minSpinnerMs = 450,
}: Options): State {
  const [state, setState] = useState<State>({ distance: 0, refreshing: false, engaged: false });
  const startY = useRef<number | null>(null);
  const armed = useRef(false);
  // Mirror of `state.distance` updated synchronously in onMove so the
  // touchend handler reads the *real* current drag — `state.distance`
  // through the closure can lag behind by one React commit.
  const distanceRef = useRef(0);
  // Stable handle to the caller's onRefresh so the effect doesn't
  // re-bind listeners every render (every parent re-render passes a
  // new arrow function).
  const onRefreshRef = useRef(onRefresh);
  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);

  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;
    // Touch-only surface — defeats accidental mouse drags on laptops
    // with touchpads that synthesize touch events.
    if (!("ontouchstart" in window)) return;

    const onStart = (e: TouchEvent) => {
      // Only arm when the document is genuinely at top. Reading
      // `scrollY` rather than `documentElement.scrollTop` covers
      // pages that scroll the `body` vs `html` element.
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      if (scrollTop > 0) {
        armed.current = false;
        return;
      }
      const t = e.touches[0];
      if (!t) return;
      startY.current = t.clientY;
      armed.current = true;
      distanceRef.current = 0;
    };

    const onMove = (e: TouchEvent) => {
      if (!armed.current || startY.current == null) return;
      const t = e.touches[0];
      if (!t) return;
      const delta = t.clientY - startY.current;
      if (delta <= 0) {
        // User scrolled back up — release the indicator.
        if (distanceRef.current !== 0) {
          distanceRef.current = 0;
          setState((s) => (s.distance ? { ...s, distance: 0, engaged: false } : s));
        }
        return;
      }
      // Tween past threshold so the user feels resistance.
      const eased = delta < threshold ? delta : threshold + (delta - threshold) * 0.4;
      const clamped = Math.min(maxStretch, eased);
      distanceRef.current = clamped;
      // Prevent the browser's own pull-to-refresh (Android Chrome)
      // from stealing the gesture once we're actively dragging.
      if (e.cancelable && delta > 4) {
        try { e.preventDefault(); } catch { /* iOS Safari sometimes rejects */ }
      }
      setState({ distance: clamped, refreshing: false, engaged: true });
    };

    const onEnd = async () => {
      if (!armed.current) return;
      // Read the live distance from the ref — closure may be stale.
      const dist = distanceRef.current;
      armed.current = false;
      startY.current = null;
      if (dist >= threshold) {
        // Snap the indicator to the threshold position while we run
        // the refresh — looks intentional vs. springing back early.
        distanceRef.current = threshold;
        setState({ distance: threshold, refreshing: true, engaged: true });
        const startedAt = Date.now();
        try {
          await onRefreshRef.current();
        } catch {
          /* swallow — caller should toast on their own */
        } finally {
          // Enforce a minimum spinner window so a fast cached refetch
          // can't dismiss the indicator before the user sees it.
          const elapsed = Date.now() - startedAt;
          if (elapsed < minSpinnerMs) {
            await new Promise((r) => setTimeout(r, minSpinnerMs - elapsed));
          }
          distanceRef.current = 0;
          setState({ distance: 0, refreshing: false, engaged: false });
        }
      } else {
        // Below threshold — spring back without firing.
        distanceRef.current = 0;
        setState({ distance: 0, refreshing: false, engaged: false });
      }
    };

    // `passive: false` lets us call `preventDefault` on touchmove —
    // necessary on Android Chrome to suppress the OS pull-to-refresh
    // while we're actively dragging.
    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", onEnd, { passive: true });

    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove as EventListener);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
    // Stable deps — listeners only rebind when caller toggles
    // enabled/threshold/maxStretch/minSpinnerMs. `onRefresh` is
    // proxied through `onRefreshRef`.
  }, [enabled, threshold, maxStretch, minSpinnerMs]);

  return state;
}

export default usePullToRefresh;

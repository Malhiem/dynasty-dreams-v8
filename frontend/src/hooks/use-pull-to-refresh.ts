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
}: Options): State {
  const [state, setState] = useState<State>({ distance: 0, refreshing: false, engaged: false });
  const startY = useRef<number | null>(null);
  const armed = useRef(false);

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
    };

    const onMove = (e: TouchEvent) => {
      if (!armed.current || startY.current == null) return;
      const t = e.touches[0];
      if (!t) return;
      const delta = t.clientY - startY.current;
      if (delta <= 0) {
        // User scrolled back up — release the indicator.
        setState((s) => (s.distance ? { ...s, distance: 0, engaged: false } : s));
        return;
      }
      // Tween past threshold so the user feels resistance.
      const eased = delta < threshold ? delta : threshold + (delta - threshold) * 0.4;
      const clamped = Math.min(maxStretch, eased);
      // Prevent the browser's own pull-to-refresh (Android Chrome)
      // from stealing the gesture once we're actively dragging.
      if (e.cancelable && delta > 4) {
        try { e.preventDefault(); } catch { /* iOS Safari sometimes rejects */ }
      }
      setState({ distance: clamped, refreshing: false, engaged: true });
    };

    const onEnd = async () => {
      if (!armed.current) return;
      const dist = state.distance;
      armed.current = false;
      startY.current = null;
      if (dist >= threshold) {
        // Snap the indicator to the threshold position while we run
        // the refresh — looks intentional vs. springing back early.
        setState({ distance: threshold, refreshing: true, engaged: true });
        try {
          await onRefresh();
        } catch {
          /* swallow — caller should toast on their own */
        } finally {
          setState({ distance: 0, refreshing: false, engaged: false });
        }
      } else {
        // Below threshold — spring back without firing.
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
      document.removeEventListener("touchmove", onMove as any);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
  }, [enabled, onRefresh, threshold, maxStretch, state.distance]);

  return state;
}

export default usePullToRefresh;

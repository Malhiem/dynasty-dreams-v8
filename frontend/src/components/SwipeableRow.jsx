// @ts-nocheck
/**
 * Iter 230au — Generic swipeable row primitive (extracted from
 * `SwipeableNotificationRow.jsx`).
 *
 * Mobile-first horizontal-drag gesture wrapper. Accepts caller-defined
 * right and left actions:
 *   • Swipe RIGHT past threshold → fires `onSwipeRight()` and
 *     reveals the `rightAction` backdrop mid-drag.
 *   • Swipe LEFT past threshold → fires `onSwipeLeft()` and reveals
 *     the `leftAction` backdrop mid-drag.
 *
 * Either side can be disabled by passing `disabled` on its action
 * (the row still moves slightly resistively so the gesture stays
 * tactile, but the commit no-ops).
 *
 * Tap (Δ < 8px) falls through to the wrapped child's onClick so
 * existing row-click behaviour is preserved.
 *
 * Props:
 *   - rightAction:   { label, icon, bg, color, disabled?, testId? }
 *   - leftAction:    same shape, used for the left-swipe reveal
 *   - onSwipeRight:  fired when right gesture commits (after animation)
 *   - onSwipeLeft:   fired when left gesture commits (after animation)
 *   - children:      the row content (handles its own onClick for taps)
 *   - keepOnRight:   when true, row stays after right-commit (e.g.
 *                    mark-read), otherwise the parent is expected to
 *                    optimistically remove it (e.g. delete).
 *   - keepOnLeft:    same flag for the left side.
 *   - testId:        forwarded to the outer wrapper
 */
import { useEffect, useRef, useState, useCallback } from "react";

const COMMIT_THRESHOLD_PX = 80;
const TAP_TOLERANCE_PX = 8;
// Iter 230aw — How far the row drifts in each direction during the
// onboarding hint pulse. Just enough to reveal the backdrop colour +
// label, never enough to trip the commit threshold.
const HINT_PEEK_PX = 56;

export default function SwipeableRow({
  rightAction = null,
  leftAction = null,
  onSwipeRight,
  onSwipeLeft,
  keepOnRight = true,
  keepOnLeft = false,
  testId,
  // Iter 230aw — When true (and the row is enabled for at least one
  // direction), the row animates a quick right-peek → centre →
  // left-peek → centre pulse on mount so first-time mobile users see
  // both action backdrops and learn the gesture exists. Set by the
  // parent only for the FIRST row in a list, and only when the user
  // hasn't dismissed the hint for that surface yet (see
  // `useOnboardingHint` helper).
  showOnboardingHint = false,
  onHintShown,
  children,
}) {
  const wrapperRef = useRef(null);
  const startXRef = useRef(0);
  const startYRef = useRef(0);
  const dragLockedRef = useRef(false);
  const pointerIdRef = useRef(null);

  const [translateX, setTranslateX] = useState(0);
  const [animating, setAnimating] = useState(false);

  const reset = useCallback((animate = true) => {
    if (animate) {
      setAnimating(true);
      requestAnimationFrame(() => setTranslateX(0));
      setTimeout(() => setAnimating(false), 220);
    } else {
      setAnimating(false);
      setTranslateX(0);
    }
    dragLockedRef.current = false;
    pointerIdRef.current = null;
  }, []);

  const commit = useCallback(
    (dir) => {
      const target = dir === "right" ? 320 : -320;
      setAnimating(true);
      setTranslateX(target);
      setTimeout(() => {
        if (dir === "right") onSwipeRight?.();
        if (dir === "left") onSwipeLeft?.();
        // Snap back instantly so the row is ready for a follow-up
        // gesture if it stays in the list.
        reset(false);
      }, 200);
    },
    [onSwipeRight, onSwipeLeft, reset],
  );

  const rightDisabled = !rightAction || rightAction.disabled;
  const leftDisabled = !leftAction || leftAction.disabled;

  // Iter 230aw — Onboarding hint pulse. Runs ONCE per mount when
  // `showOnboardingHint` is true and at least one direction is
  // enabled. The animation chain (right peek → centre → left peek →
  // centre) takes ~1500ms total and is gated behind a guard so
  // remounts inside the same tab don't repeat. The parent's
  // `useOnboardingHint` helper handles cross-tab + cross-session
  // dedupe via localStorage.
  const hintFiredRef = useRef(false);
  useEffect(() => {
    if (!showOnboardingHint) return;
    if (hintFiredRef.current) return;
    if (rightDisabled && leftDisabled) return;
    hintFiredRef.current = true;
    // Defer slightly so the first paint (with row at translateX:0) is
    // visible before we start sliding — keeps the hint readable.
    const t0 = setTimeout(() => {
      setAnimating(true);
      setTranslateX(rightDisabled ? -HINT_PEEK_PX : HINT_PEEK_PX);
    }, 350);
    const t1 = setTimeout(() => setTranslateX(0), 850);
    const t2 = setTimeout(
      () => setTranslateX(leftDisabled ? HINT_PEEK_PX : -HINT_PEEK_PX),
      1100,
    );
    const t3 = setTimeout(() => {
      setTranslateX(0);
      setTimeout(() => setAnimating(false), 220);
      onHintShown?.();
    }, 1600);
    return () => {
      clearTimeout(t0);
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
    // Run once on mount; subsequent flag changes shouldn't re-pulse.
  }, []);

  const onPointerDown = (e) => {
    if (pointerIdRef.current !== null) return;
    pointerIdRef.current = e.pointerId;
    startXRef.current = e.clientX;
    startYRef.current = e.clientY;
    dragLockedRef.current = false;
    setAnimating(false);
  };

  const onPointerMove = (e) => {
    if (pointerIdRef.current !== e.pointerId) return;
    const dx = e.clientX - startXRef.current;
    const dy = e.clientY - startYRef.current;
    if (!dragLockedRef.current) {
      if (Math.abs(dy) > Math.abs(dx) * 1.2 && Math.abs(dy) > 12) {
        pointerIdRef.current = null;
        return;
      }
      if (Math.abs(dx) < 6) return;
      dragLockedRef.current = true;
      try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch { /* noop */ }
    }
    let next = dx;
    if (rightDisabled && dx > 0) next = Math.min(40, dx / 3);
    if (leftDisabled && dx < 0) next = Math.max(-40, dx / 3);
    setTranslateX(next);
  };

  const onPointerUp = (e) => {
    if (pointerIdRef.current !== e.pointerId) return;
    const dx = e.clientX - startXRef.current;
    pointerIdRef.current = null;
    try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch { /* noop */ }

    if (!dragLockedRef.current && Math.abs(dx) < TAP_TOLERANCE_PX) {
      reset(false);
      return;
    }
    if (dx > COMMIT_THRESHOLD_PX && !rightDisabled) {
      commit("right");
    } else if (dx < -COMMIT_THRESHOLD_PX && !leftDisabled) {
      commit("left");
    } else {
      reset(true);
    }
  };

  const showingRight = translateX > 8 && !rightDisabled && rightAction;
  const showingLeft = translateX < -8 && !leftDisabled && leftAction;

  return (
    <div ref={wrapperRef} className="relative overflow-hidden" data-testid={testId}>
      {showingRight && (
        <div
          className={`absolute inset-0 flex items-center justify-start pl-4 text-xs font-semibold pointer-events-none ${rightAction.bg || "bg-emerald-600/25"} ${rightAction.color || "text-emerald-200"}`}
          data-testid={rightAction.testId}
        >
          {rightAction.icon}
          {rightAction.label && <span className="ml-1.5">{rightAction.label}</span>}
        </div>
      )}
      {showingLeft && (
        <div
          className={`absolute inset-0 flex items-center justify-end pr-4 text-xs font-semibold pointer-events-none ${leftAction.bg || "bg-rose-600/25"} ${leftAction.color || "text-rose-200"}`}
          data-testid={leftAction.testId}
        >
          {leftAction.icon}
          {leftAction.label && <span className="ml-1.5">{leftAction.label}</span>}
        </div>
      )}

      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => reset(true)}
        style={{
          transform: `translateX(${translateX}px)`,
          transition: animating ? "transform 200ms ease-out" : "none",
          touchAction: "pan-y",
        }}
      >
        {children}
      </div>
    </div>
  );
}

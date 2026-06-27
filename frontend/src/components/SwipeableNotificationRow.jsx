// @ts-nocheck
/**
 * Iter 230at — Swipeable notification row.
 *
 * Mobile-first swipe gestures over the existing notification card:
 *   • Swipe RIGHT  → mark as read   (revealing the green "Read" bg)
 *   • Swipe LEFT   → delete         (revealing the red  "Delete" bg)
 *
 * Implementation notes:
 *   - Uses pointer events so it works for both touch and mouse, but
 *     defaults to touch-action: pan-y so vertical scrolling in the
 *     parent panel still works naturally.
 *   - Threshold is 33% of the card's measured width (or 80px,
 *     whichever is smaller) so short swipes snap back; long swipes
 *     commit the action.
 *   - Tap (delta < 8px) falls through to the regular onClick so the
 *     existing "click row to mark read + follow link" behaviour is
 *     preserved.
 *   - Rows that are already read disable the right-swipe gesture
 *     (no-op) but keep the left-swipe-to-delete affordance.
 *   - Reduced-motion users get the actions exposed via small
 *     keyboard / aria buttons rendered after the row (see parent).
 */
import { useRef, useState, useCallback } from "react";
import { Check, Trash2 } from "lucide-react";

const COMMIT_THRESHOLD_PX = 80;
const TAP_TOLERANCE_PX = 8;

export default function SwipeableNotificationRow({
  notification,
  onMarkRead,
  onDelete,
  children,
}) {
  const wrapperRef = useRef(null);
  const startXRef = useRef(0);
  const startYRef = useRef(0);
  const dragLockedRef = useRef(false);
  const pointerIdRef = useRef(null);
  const isRead = !!notification.read;

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
        if (dir === "right" && !isRead) onMarkRead?.(notification._id);
        if (dir === "left") onDelete?.(notification._id);
        // Reset for the brief moment between commit + parent unmount
        // (delete) or row update (read).
        reset(false);
      }, 200);
    },
    [isRead, notification._id, onDelete, onMarkRead, reset],
  );

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
        // Vertical scroll wins — bail.
        pointerIdRef.current = null;
        return;
      }
      if (Math.abs(dx) < 6) return;
      dragLockedRef.current = true;
      try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch { /* noop */ }
    }
    // Read rows don't move right (you can't mark-read what's already
    // read), but left-to-delete is still allowed.
    let next = dx;
    if (isRead && dx > 0) next = Math.min(40, dx / 3);
    setTranslateX(next);
  };

  const onPointerUp = (e) => {
    if (pointerIdRef.current !== e.pointerId) return;
    const dx = e.clientX - startXRef.current;
    pointerIdRef.current = null;
    try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch { /* noop */ }

    if (!dragLockedRef.current && Math.abs(dx) < TAP_TOLERANCE_PX) {
      // It was a tap — let the inner row's onClick run as usual.
      reset(false);
      return;
    }

    if (dx > COMMIT_THRESHOLD_PX && !isRead) {
      commit("right");
    } else if (dx < -COMMIT_THRESHOLD_PX) {
      commit("left");
    } else {
      reset(true);
    }
  };

  // Visual cue for the action being revealed under the row.
  const showingRight = translateX > 8 && !isRead;
  const showingLeft = translateX < -8;

  return (
    <div ref={wrapperRef} className="relative overflow-hidden">
      {/* Action backdrops */}
      {showingRight && (
        <div
          className="absolute inset-0 flex items-center justify-start pl-4 bg-emerald-600/25 text-emerald-200 text-xs font-semibold pointer-events-none"
          data-testid={`notif-swipe-read-hint-${notification._id}`}
        >
          <Check className="h-4 w-4 mr-1.5" />
          Mark read
        </div>
      )}
      {showingLeft && (
        <div
          className="absolute inset-0 flex items-center justify-end pr-4 bg-rose-600/25 text-rose-200 text-xs font-semibold pointer-events-none"
          data-testid={`notif-swipe-delete-hint-${notification._id}`}
        >
          <Trash2 className="h-4 w-4 mr-1.5" />
          Delete
        </div>
      )}

      <div
        data-testid={`notif-swipe-row-${notification._id}`}
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

/**
 * Iter 232l — Browser Notification helper.
 *
 * Thin wrapper around the browser's `Notification` API with the
 * accessibility + preference gates our other alert layers use
 * (haptics iter 232e, sounds iter 232g, presence pulse iter 232d).
 *
 * Design:
 *   • `requestNotificationPermission()` — call from a user gesture
 *     (button click, toggle) to prompt the OS-level allow dialog.
 *     No-op when the browser doesn't expose `Notification`.
 *   • `notificationsAllowed()` — pure predicate; returns true iff
 *     the browser API exists AND `Notification.permission === "granted"`.
 *   • `showBrowserNotification({ title, body, tag })` — fires a
 *     notification. `tag` de-dupes repeats (a second call with the
 *     same tag replaces the previous notification instead of
 *     stacking) so a countdown that re-renders every minute doesn't
 *     turn into a rave.
 *
 * All entry points silently no-op when the browser doesn't support
 * the API, when permission isn't granted, or when the user has the
 * OS-level `prefers-reduced-motion: reduce` toggle on (users who
 * opt out of motion generally also want quieter alerts).
 */

function hasApi(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return typeof Notification !== "undefined";
  } catch {
    return false;
  }
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function notificationsSupported(): boolean {
  return hasApi();
}

export function notificationsAllowed(): boolean {
  if (!hasApi()) return false;
  try {
    return Notification.permission === "granted";
  } catch {
    return false;
  }
}

export function notificationsBlocked(): boolean {
  if (!hasApi()) return false;
  try {
    return Notification.permission === "denied";
  } catch {
    return false;
  }
}

/**
 * Prompt the OS-level permission dialog. Must be called from a user
 * gesture (button click). Returns a promise resolving to the final
 * permission state — 'granted' | 'denied' | 'default'.
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!hasApi()) return "denied";
  try {
    const result = await Notification.requestPermission();
    return result;
  } catch {
    return "denied";
  }
}

interface ShowArgs {
  title: string;
  body?: string;
  /** Stable identifier that de-dupes repeats so the same event
   * doesn't spawn multiple notifications on re-renders. */
  tag?: string;
  /** Prevents the OS from auto-hiding the notification. Useful for
   * high-stakes reminders like "you are on the clock". */
  requireInteraction?: boolean;
}

/**
 * Show a browser notification. Returns `true` when a notification
 * was actually fired.
 */
export function showBrowserNotification({
  title, body, tag, requireInteraction,
}: ShowArgs): boolean {
  if (!notificationsAllowed()) return false;
  if (prefersReducedMotion()) return false;
  try {
    new Notification(title, {
      body,
      tag,
      requireInteraction: !!requireInteraction,
      // Manifest icon so the notification carries the app brand.
      icon: "/icon-192.png",
      badge: "/icon-192.png",
    });
    return true;
  } catch {
    return false;
  }
}

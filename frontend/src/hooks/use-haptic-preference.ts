/**
 * Iter 232e — `useHapticPreference` + `triggerHaptic`
 *
 * Tiny primitive for the "haptic buzz on live events" preference.
 * Stored per-user in `localStorage['dd-haptics']` so it survives
 * across sessions.
 *
 * Design notes:
 *   • Defaults to ON when the device actually supports vibration
 *     (`navigator.vibrate` present + user hasn't opted out) —
 *     supporting devices tend to be phones where the affordance
 *     genuinely helps, and desktop browsers where `vibrate` is a
 *     no-op won't buzz anyway.
 *   • Defaults to OFF when the browser doesn't expose the API so
 *     the toggle doesn't render a UI knob that does nothing.
 *   • `triggerHaptic(ms)` is a safe no-op if the preference is
 *     off, the API is missing, or the user has
 *     `prefers-reduced-motion: reduce` on their OS.
 */
import { useCallback, useEffect, useState } from "react";

const LS_KEY = "dd-haptics";

function hasVibrateApi(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return typeof navigator !== "undefined" && typeof navigator.vibrate === "function";
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

function readStored(): boolean | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (raw === null) return null;
    return raw === "true";
  } catch {
    return null;
  }
}

function writeStored(v: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, v ? "true" : "false");
  } catch {
    /* localStorage blocked (privacy mode, quota, etc.) — silently no-op */
  }
}

interface HapticState {
  /** True when the browser exposes `navigator.vibrate`. */
  supported: boolean;
  /** True when the user has enabled haptics AND the browser supports it. */
  enabled: boolean;
  /** Toggle handle for the Preferences menu. */
  setEnabled: (v: boolean) => void;
}

export function useHapticPreference(): HapticState {
  const supported = hasVibrateApi();

  // Default: enabled iff supported AND the user hasn't explicitly
  // opted out. Users on non-vibrating browsers see the toggle as
  // "off + disabled" so we don't dangle a promise the OS can't keep.
  const [enabled, setEnabledState] = useState<boolean>(() => {
    if (!supported) return false;
    const stored = readStored();
    return stored === null ? true : stored;
  });

  // Sync when another tab flips the preference (rare but cheap).
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== LS_KEY) return;
      const next = readStored();
      if (next !== null) setEnabledState(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setEnabled = useCallback((v: boolean) => {
    setEnabledState(v);
    writeStored(v);
    // A short confirmation buzz when the user turns it on gives
    // instant feedback that the hardware works + the toggle took.
    if (v && supported && !prefersReducedMotion()) {
      try { navigator.vibrate(30); } catch { /* noop */ }
    }
  }, [supported]);

  return { supported, enabled, setEnabled };
}

/**
 * Standalone helper for callers that just need to fire a buzz
 * without wiring the full hook (e.g. one-shot event handlers).
 * Reads the same localStorage key. Returns whether the buzz was
 * actually attempted.
 */
export function triggerHaptic(ms: number = 30): boolean {
  if (!hasVibrateApi()) return false;
  if (prefersReducedMotion()) return false;
  // Explicit opt-out honoured; missing key = default-on.
  const stored = readStored();
  if (stored === false) return false;
  try {
    navigator.vibrate(ms);
    return true;
  } catch {
    return false;
  }
}

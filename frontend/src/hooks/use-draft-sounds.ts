// @ts-nocheck
/**
 * Iter 172 — Draft Room audio alerts.
 *
 * Two distinct synthesized tones so a manager who's tabbed away from the
 * Draft Room still gets an audible heads-up:
 *
 *   • "Next Up"        — soft 2-note ascending chime (E5 → G5). Fires when
 *                        picksUntilMyTurn transitions to 1.
 *   • "On the Clock"   — urgent 3-note arpeggio (A5 → C6 → E6) played twice.
 *                        Fires when picksUntilMyTurn transitions to 0.
 *
 * Implemented via Web Audio API so we don't ship any audio assets and the
 * tones render identically on every platform.
 *
 * Browser autoplay policies require a user gesture before an AudioContext
 * can start producing sound. We lazily create the context on the first
 * `play*` call inside an event handler (the toggle click, simulate-pick,
 * etc.) and gracefully no-op if the context is still in `suspended` state.
 *
 * The enabled flag persists across reloads via localStorage so a manager
 * who muted last night doesn't get jump-scared at 9 AM.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const LS_KEY = "draftroom.sounds.enabled.v1";

type Tone = { freq: number; start: number; dur: number; gain?: number };

const NEXT_UP_TONES: Tone[] = [
  { freq: 659.25, start: 0.00, dur: 0.18, gain: 0.18 }, // E5
  { freq: 783.99, start: 0.16, dur: 0.28, gain: 0.18 }, // G5
];

const ON_CLOCK_TONES: Tone[] = [
  { freq: 880.00, start: 0.00, dur: 0.14, gain: 0.28 }, // A5
  { freq: 1046.5, start: 0.13, dur: 0.14, gain: 0.28 }, // C6
  { freq: 1318.5, start: 0.26, dur: 0.22, gain: 0.30 }, // E6
  // brief pause then repeat for urgency
  { freq: 880.00, start: 0.55, dur: 0.14, gain: 0.28 }, // A5
  { freq: 1046.5, start: 0.68, dur: 0.14, gain: 0.28 }, // C6
  { freq: 1318.5, start: 0.81, dur: 0.30, gain: 0.30 }, // E6
];

function readPersistedEnabled(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const v = window.localStorage.getItem(LS_KEY);
    // Default on — managers explicitly opted in by scheduling a draft.
    return v === null ? true : v === "1";
  } catch {
    return true;
  }
}

export default function useDraftSounds() {
  const ctxRef = useRef<AudioContext | null>(null);
  const [enabled, setEnabledState] = useState<boolean>(readPersistedEnabled());

  const ensureContext = useCallback((): AudioContext | null => {
    if (typeof window === "undefined") return null;
    if (!ctxRef.current) {
      const Ctor = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!Ctor) return null;
      try {
        ctxRef.current = new Ctor();
      } catch {
        return null;
      }
    }
    // Browsers suspend the context until a user gesture. Best-effort resume.
    if (ctxRef.current && ctxRef.current.state === "suspended") {
      ctxRef.current.resume().catch(() => {});
    }
    return ctxRef.current;
  }, []);

  const playPattern = useCallback(
    (tones: Tone[]) => {
      if (!enabled) return;
      const ctx = ensureContext();
      if (!ctx) return;
      const now = ctx.currentTime;
      tones.forEach((t) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(t.freq, now + t.start);
        // Quick attack / release envelope so the tone doesn't click.
        const peak = t.gain ?? 0.2;
        gain.gain.setValueAtTime(0.0001, now + t.start);
        gain.gain.exponentialRampToValueAtTime(peak, now + t.start + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + t.start + t.dur);
        osc.connect(gain).connect(ctx.destination);
        osc.start(now + t.start);
        osc.stop(now + t.start + t.dur + 0.02);
      });
    },
    [enabled, ensureContext],
  );

  const playNextUp = useCallback(() => playPattern(NEXT_UP_TONES), [playPattern]);
  const playOnTheClock = useCallback(() => playPattern(ON_CLOCK_TONES), [playPattern]);

  const setEnabled = useCallback((next: boolean) => {
    setEnabledState(next);
    try {
      window.localStorage.setItem(LS_KEY, next ? "1" : "0");
    } catch {}
    // If the user just enabled sounds, prime the audio context inside the
    // click handler that called us — this satisfies autoplay policy so the
    // next on-clock alert can actually play even when the tab is hidden.
    if (next) ensureContext();
  }, [ensureContext]);

  // Stop dangling contexts on unmount.
  useEffect(
    () => () => {
      const ctx = ctxRef.current;
      if (ctx && ctx.state !== "closed") {
        try { ctx.close(); } catch {}
      }
    },
    [],
  );

  return useMemo(
    () => ({ enabled, setEnabled, playNextUp, playOnTheClock }),
    [enabled, setEnabled, playNextUp, playOnTheClock],
  );
}

/**
 * useTabTitleAlert — flash a prefix on document.title whenever the tab is
 * hidden and `alertActive` is true. Restores the original title when the
 * tab regains focus or alertActive flips back to false.
 */
export function useTabTitleAlert(alertActive: boolean, prefix = "🔔 YOUR PICK — ") {
  useEffect(() => {
    if (typeof document === "undefined") return;
    const original = document.title;
    if (!alertActive) {
      // Make sure we strip any lingering prefix.
      if (document.title.startsWith(prefix)) {
        document.title = document.title.slice(prefix.length);
      }
      return;
    }
    let toggled = false;
    let timer: any = null;
    const tick = () => {
      if (document.hidden) {
        document.title = toggled ? original : prefix + original;
        toggled = !toggled;
      } else {
        document.title = original;
        toggled = false;
      }
      timer = setTimeout(tick, 1100);
    };
    tick();
    return () => {
      if (timer) clearTimeout(timer);
      document.title = original;
    };
  }, [alertActive, prefix]);
}

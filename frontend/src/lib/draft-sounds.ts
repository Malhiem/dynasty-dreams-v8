/**
 * Iter 232g — Web Audio synthesized draft-clock tones.
 *
 * Two short, entirely code-generated tones for cross-modal draft
 * cues (paired with the iter 232f haptics):
 *
 *   • `playDing()` — a soft two-note glide (C5 → G5) with an
 *     envelope tuned so it reads as a friendly "your turn" chime.
 *     ~250ms total.
 *   • `playBuzz()` — a stubby low-square burst on A3, three quick
 *     pulses to match the [80,80,80,80,80] haptic urgency pattern
 *     from the final-10s warning.
 *
 * Design goals:
 *   • No audio files → no bundle bloat, no CORS/service-worker
 *     asset caching concerns.
 *   • Reused `AudioContext` (browsers cap the count) with an
 *     `ensureUserGestureUnlock` step so iOS Safari doesn't reject
 *     the first playback attempt.
 *   • Volume is a plain 0-100 int stored in localStorage. A `0`
 *     volume mutes the caller entirely (short-circuit before the
 *     oscillator ever spins up).
 */

const LS_ENABLED = "dd-sounds-enabled";
const LS_VOLUME = "dd-sounds-volume";

// Singleton `AudioContext`. Browsers cap concurrent contexts at 6ish
// on desktop and 4 on mobile, so we absolutely want one shared
// instance for the entire app.
let ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (ctx) return ctx;
  try {
    const AudioCtor =
      (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
        .AudioContext ||
      (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioCtor) return null;
    ctx = new AudioCtor();
    return ctx;
  } catch {
    return null;
  }
}

/**
 * Resume the shared AudioContext if it's in the "suspended" state
 * (this is iOS Safari's default until the first user gesture).
 * Should be called from a user-initiated event handler at least
 * once per session — e.g. the Preferences toggle's onClick.
 */
export function ensureAudioUnlocked(): void {
  const c = getCtx();
  if (!c) return;
  if (c.state === "suspended") {
    // Return promise is intentionally not awaited — this is fire &
    // forget from a click handler.
    void c.resume().catch(() => undefined);
  }
}

export function areDraftSoundsEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(LS_ENABLED);
    // Default OFF — audio is more intrusive than haptics, requires
    // an explicit opt-in.
    return raw === "true";
  } catch {
    return false;
  }
}

export function setDraftSoundsEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_ENABLED, enabled ? "true" : "false");
  } catch {
    /* localStorage blocked (privacy mode, quota) — silently no-op */
  }
  if (enabled) ensureAudioUnlocked();
}

export function getDraftSoundsVolume(): number {
  if (typeof window === "undefined") return 60;
  try {
    const raw = window.localStorage.getItem(LS_VOLUME);
    if (raw === null) return 60; // sensible default
    const parsed = parseInt(raw, 10);
    if (Number.isNaN(parsed)) return 60;
    return Math.min(100, Math.max(0, parsed));
  } catch {
    return 60;
  }
}

export function setDraftSoundsVolume(volume: number): void {
  if (typeof window === "undefined") return;
  const clamped = Math.min(100, Math.max(0, Math.round(volume)));
  try {
    window.localStorage.setItem(LS_VOLUME, String(clamped));
  } catch {
    /* noop */
  }
}

/**
 * Common entry-point guard for the two playback helpers so both
 * pick-start and final-10s share the same accessibility contract.
 * Returns the shared context (with linear-normalized `gain` [0..1])
 * or `null` when we should stay silent.
 */
function preparePlayback(): { c: AudioContext; gain: number } | null {
  if (!areDraftSoundsEnabled()) return null;
  const rawVol = getDraftSoundsVolume();
  if (rawVol <= 0) return null;
  // Users on the OS "reduce motion + effects" toggle usually also
  // want quieter UI feedback — respect that as an accessibility
  // signal without a separate audio setting.
  try {
    if (
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return null;
    }
  } catch {
    /* ignore */
  }
  const c = getCtx();
  if (!c) return null;
  if (c.state === "suspended") {
    // We tried — if it's still suspended (no user gesture yet), the
    // playback would be silent anyway. Bail cleanly.
    void c.resume().catch(() => undefined);
    if (c.state === "suspended") return null;
  }
  // Volumes >65 add unpleasant peak clip in mobile speakers; cap the
  // top-end amplitude so "loud" never means "harsh".
  const gain = Math.min(1, rawVol / 100) * 0.35;
  return { c, gain };
}

/**
 * Soft two-note "your turn" glide. Sine wave + gentle ADSR
 * envelope so it reads more like a doorbell than a game notification.
 */
export function playDing(): boolean {
  const prep = preparePlayback();
  if (!prep) return false;
  const { c, gain } = prep;
  try {
    const now = c.currentTime;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = "sine";
    // C5 → G5 upward glide feels like a friendly "hey, you're up".
    osc.frequency.setValueAtTime(523.25, now);
    osc.frequency.linearRampToValueAtTime(783.99, now + 0.18);
    // ADSR: quick attack, hold briefly, exponential release. Using
    // exponential ramp avoids the click-artefact you get from a
    // sharp linearRampToValueAtTime → 0.
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(gain, now + 0.015);
    g.gain.setValueAtTime(gain, now + 0.14);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);
    osc.connect(g).connect(c.destination);
    osc.start(now);
    osc.stop(now + 0.36);
    return true;
  } catch {
    return false;
  }
}

/**
 * Urgent buzz pattern for the "final 10 seconds" warning. Three
 * short square-wave bursts on A3 (220 Hz) so it cuts through
 * background noise without being ear-splitting.
 */
export function playBuzz(): boolean {
  const prep = preparePlayback();
  if (!prep) return false;
  const { c, gain } = prep;
  try {
    const now = c.currentTime;
    const pulses = 3;
    const pulseLen = 0.08; // 80ms — matches the [80,80,...] haptic
    const gap = 0.06;
    for (let i = 0; i < pulses; i++) {
      const start = now + i * (pulseLen + gap);
      const osc = c.createOscillator();
      const g = c.createGain();
      osc.type = "square";
      osc.frequency.setValueAtTime(220, start);
      // Slightly quieter than the ding so back-to-back pulses don't
      // fatigue the listener.
      const pulseGain = gain * 0.7;
      g.gain.setValueAtTime(0, start);
      g.gain.linearRampToValueAtTime(pulseGain, start + 0.008);
      g.gain.setValueAtTime(pulseGain, start + pulseLen - 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, start + pulseLen);
      osc.connect(g).connect(c.destination);
      osc.start(start);
      osc.stop(start + pulseLen + 0.02);
    }
    return true;
  } catch {
    return false;
  }
}

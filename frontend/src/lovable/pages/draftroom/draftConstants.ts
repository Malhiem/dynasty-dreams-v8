// @ts-nocheck
/**
 * Iter 171 — Shared draft-room constants & helpers.
 *
 * Position color/tint maps + countdown / pick-timer formatters were
 * duplicated across DraftRoom.tsx and the newly-extracted DraftLiveTile
 * + DraftBoard subcomponents. Centralised here so both presentation
 * components stay in lockstep without prop-drilling them around.
 */

export const positionColors: Record<string, string> = {
  C:  "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D:  "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G:  "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

export const positionTints: Record<string, string> = {
  C:  "bg-blue-500/15 border-blue-500/40",
  LW: "bg-emerald-500/15 border-emerald-500/40",
  RW: "bg-teal-500/15 border-teal-500/40",
  D:  "bg-amber-500/15 border-amber-500/40",
  G:  "bg-purple-500/15 border-purple-500/40",
};

export function formatCountdown(ms: number) {
  if (ms <= 0) return "00:00:00";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatPickTimer(seconds: number) {
  // Iter 230ao — Always display HH:MM:SS so multi-hour per-pick clocks
  // (TFHL uses 4h windows) read correctly. Short timers also benefit
  // from the consistent zero-padded format (e.g. 00:01:30).
  const safe = Math.max(0, Math.floor(seconds));
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

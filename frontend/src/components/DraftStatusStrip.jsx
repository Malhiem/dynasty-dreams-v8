/**
 * Iter 232k — `<DraftStatusStrip />`
 *
 * Compact live-status pill row rendered inside the `/commissioner`
 * Draft tab card. Turns the tab from a passive launchpad into a
 * genuine game-day dashboard so commissioners glance at
 * `/commissioner` and immediately see the whole picture:
 *
 *   • Countdown to the next scheduled draft ("Draft in 3 days",
 *     "Draft starting soon", "Draft is live").
 *   • Number of bonus picks configured (compensation / expansion —
 *     iter 232i feature).
 *   • Team fill status (12 / 12 ready).
 *
 * The strip re-ticks itself once per minute so "in 12 minutes" ages
 * into "in 11 minutes" without the parent re-fetching. When there is
 * no upcoming draft on the books the whole strip returns null so the
 * card layout doesn't jump.
 */
import { useEffect, useState } from "react";
import { Clock, Gift, Users, Zap } from "lucide-react";

function formatCountdown(diffMs) {
  // Diff is signed — positive means in the future.
  const absMs = Math.abs(diffMs);
  const minutes = Math.floor(absMs / (60 * 1000));
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (diffMs <= 0) return "live now";
  if (minutes < 1) return "starting seconds";
  if (minutes < 60) return `in ${minutes} min${minutes === 1 ? "" : "s"}`;
  if (hours < 24) {
    const remMin = minutes - hours * 60;
    if (remMin === 0) return `in ${hours} hr${hours === 1 ? "" : "s"}`;
    return `in ${hours}h ${remMin}m`;
  }
  if (days < 7) {
    const remHr = hours - days * 24;
    if (remHr === 0) return `in ${days} day${days === 1 ? "" : "s"}`;
    return `in ${days}d ${remHr}h`;
  }
  return `in ${days} days`;
}

export default function DraftStatusStrip({
  nextDraft, bonusCount = 0, teamCount = 0, maxTeams,
}) {
  // Re-tick once per minute so the countdown ages without the
  // parent having to refetch.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60 * 1000);
    return () => clearInterval(id);
  }, []);

  if (!nextDraft) return null;

  const scheduledAt = nextDraft.scheduled_at
    ? Date.parse(nextDraft.scheduled_at)
    : null;
  if (!scheduledAt) return null;

  const diffMs = scheduledAt - now;
  const status = String(nextDraft.status || "").toLowerCase();
  const isLive = status === "active" || (diffMs <= 0 && status !== "completed");
  const countdown = isLive ? "live now" : formatCountdown(diffMs);

  // Colour cue: live = green, imminent (<24h) = amber, else neutral.
  const countdownTone = isLive
    ? "bg-[#34C759]/15 border-[#34C759]/40 text-[#34C759]"
    : diffMs < 24 * 60 * 60 * 1000
      ? "bg-amber-500/15 border-amber-500/40 text-amber-400"
      : "bg-[#00D2FF]/10 border-[#00D2FF]/30 text-[#00D2FF]";

  const teamsReady = maxTeams && teamCount >= maxTeams;

  return (
    <div
      className="flex flex-wrap items-center gap-2 mt-3"
      data-testid="commissioner-draft-status-strip"
    >
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${countdownTone}`}
        data-testid="commissioner-draft-status-countdown"
        data-status={isLive ? "live" : "scheduled"}
        title={new Date(scheduledAt).toLocaleString()}
      >
        {isLive ? <Zap className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
        <span>Draft {countdown}</span>
      </span>
      <span
        className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs font-medium text-[#A1A1AA]"
        data-testid="commissioner-draft-status-bonus-count"
      >
        <Gift className="h-3 w-3 text-amber-500" />
        <span>
          {bonusCount} bonus pick{bonusCount === 1 ? "" : "s"} configured
        </span>
      </span>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
          teamsReady
            ? "border-[#34C759]/30 bg-[#34C759]/10 text-[#34C759]"
            : "border-white/10 bg-white/[0.04] text-[#A1A1AA]"
        }`}
        data-testid="commissioner-draft-status-teams"
      >
        <Users className="h-3 w-3" />
        <span>
          {teamCount}
          {maxTeams ? ` / ${maxTeams}` : ""} team{teamCount === 1 ? "" : "s"}
          {teamsReady ? " ready" : ""}
        </span>
      </span>
    </div>
  );
}

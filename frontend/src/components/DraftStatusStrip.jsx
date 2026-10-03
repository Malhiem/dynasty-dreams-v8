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
import { useEffect, useRef, useState } from "react";
import { Clock, Gift, Users, Zap } from "lucide-react";
import { showBrowserNotification } from "@/lib/browser-notify";

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
  nextDraft, bonusCount = 0, teamCount = 0, maxTeams, unclaimedSeats = 0,
}) {
  // Re-tick once per minute so the countdown ages without the
  // parent having to refetch.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60 * 1000);
    return () => clearInterval(id);
  }, []);
  // Iter 232l — Latch so the "10-minute warning" browser
  // Notification fires exactly once per draft (not on every
  // 60-second re-tick). Reset when the draft id changes.
  const notified10minRef = useRef(null);
  const notifiedLiveRef = useRef(null);
  useEffect(() => {
    notified10minRef.current = null;
    notifiedLiveRef.current = null;
  }, [nextDraft?._id, nextDraft?.id]);

  // Compute derived values BEFORE any early returns so downstream
  // hooks (the notification effect) run unconditionally per React
  // Hook rules. `scheduledAt` and `diffMs` are safe to derive with
  // possibly-null `nextDraft` because we guard inside the effect.
  const scheduledAt = nextDraft?.scheduled_at
    ? Date.parse(nextDraft.scheduled_at)
    : null;
  const diffMs = scheduledAt ? scheduledAt - now : 0;
  const status = String(nextDraft?.status || "").toLowerCase();
  const isLive =
    !!nextDraft &&
    (status === "active" || (scheduledAt && diffMs <= 0 && status !== "completed"));
  const countdown = isLive ? "live now" : formatCountdown(diffMs);
  const underOneHour = !isLive && diffMs > 0 && diffMs < 60 * 60 * 1000;

  // Iter 232l — Fire OS-level browser notifications on two triggers:
  //   • 10 minutes before scheduled start ("Draft starts in 10 minutes —
  //     N seats still unclaimed")
  //   • The moment the draft goes live
  // Both are idempotent via refs so a re-tick can't spawn duplicates.
  // The Notification API itself gates on `Notification.permission` +
  // `prefers-reduced-motion` inside `showBrowserNotification`.
  useEffect(() => {
    const draftId = nextDraft?._id || nextDraft?.id;
    if (!draftId || !scheduledAt) return;
    const rem = scheduledAt - now;
    // 10-minute warning window: fires once when the countdown is
    // between 10min and 9min remaining. The 60s bucket the parent
    // re-ticks on means at most one landing inside this window.
    if (
      rem > 9 * 60 * 1000 &&
      rem <= 10 * 60 * 1000 &&
      notified10minRef.current !== draftId
    ) {
      notified10minRef.current = draftId;
      const seatsCopy =
        unclaimedSeats > 0
          ? ` — ${unclaimedSeats} seat${unclaimedSeats === 1 ? "" : "s"} still unclaimed`
          : "";
      showBrowserNotification({
        title: "Draft starts in 10 minutes",
        body: `${nextDraft.name || nextDraft.league_name || "Your draft"}${seatsCopy}`,
        tag: `draft-10min-${draftId}`,
        requireInteraction: false,
      });
    }
    // "Draft is live" trigger — fires exactly once at the transition.
    if (
      status === "active" &&
      notifiedLiveRef.current !== draftId
    ) {
      notifiedLiveRef.current = draftId;
      showBrowserNotification({
        title: "Draft is live",
        body: nextDraft.name || nextDraft.league_name || "The draft has started",
        tag: `draft-live-${draftId}`,
        requireInteraction: true,
      });
    }
  }, [
    now, scheduledAt, status, unclaimedSeats,
    nextDraft?._id, nextDraft?.id, nextDraft?.name, nextDraft?.league_name,
  ]);

  if (!nextDraft) return null;
  if (!scheduledAt) return null;

  // Colour cue: live = green, imminent (<24h) = amber, else neutral.
  // Iter 232l — when <1h out, layer an animated pulse ring on top of
  // the amber tone so the pill visibly breathes as the draft nears.
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
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${countdownTone} ${
          underOneHour || isLive ? "draft-countdown-pulse" : ""
        }`}
        data-testid="commissioner-draft-status-countdown"
        data-status={isLive ? "live" : underOneHour ? "imminent" : "scheduled"}
        data-pulsing={underOneHour || isLive ? "true" : "false"}
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

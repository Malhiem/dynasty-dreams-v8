// @ts-nocheck
/**
 * Iter 129 — Trade Deadline Countdown Ribbon
 *
 * Renders a slim dismissible banner across the top of the app once the
 * league has a `trade_deadline_at` set and the deadline is in the future.
 * Refreshes the countdown every minute. Vanishes when the deadline has
 * passed (deadline-enforcement on the backend takes over).
 *
 * Dismissal is per-deadline-ISO so a fresh deadline always re-shows.
 */
import { useEffect, useMemo, useState } from "react";
import { Clock, X } from "lucide-react";
import { Link } from "react-router-dom";
import { useActiveLeague } from "@/hooks/use-active-league";

function fmtRemaining(target) {
  const now = Date.now();
  const diff = target - now;
  if (diff <= 0) return null;
  const totalMinutes = Math.floor(diff / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days} day${days === 1 ? "" : "s"}, ${hours} hr`;
  if (hours > 0) return `${hours} hr, ${minutes} min`;
  return `${minutes} min`;
}

export default function TradeDeadlineRibbon() {
  const { league } = useActiveLeague();
  const deadlineAt = league?.trade_deadline_at;

  // Re-render every 60s so the countdown ticks
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!deadlineAt) return;
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(id);
  }, [deadlineAt]);

  const target = useMemo(() => {
    if (!deadlineAt) return null;
    const d = new Date(deadlineAt);
    return Number.isNaN(d.getTime()) ? null : d.getTime();
  }, [deadlineAt]);

  const dismissKey = `trade-deadline-ribbon-dismissed:${deadlineAt || ""}`;
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return window.sessionStorage.getItem(dismissKey) === "1";
    } catch { return false; }
  });

  if (!target || dismissed) return null;
  const remaining = fmtRemaining(target);
  if (!remaining) return null;

  // Tone: rose (under 24h), amber (under 3d), cyan otherwise
  const msLeft = target - Date.now();
  const tone =
    msLeft < 24 * 3600_000
      ? "bg-rose-500/15 border-rose-500/40 text-rose-200"
      : msLeft < 3 * 24 * 3600_000
        ? "bg-amber-500/15 border-amber-500/40 text-amber-200"
        : "bg-cyan-500/15 border-cyan-500/40 text-cyan-200";

  return (
    <div
      className={`w-full border-b ${tone} flex items-center gap-2 px-4 py-1.5 text-xs font-medium`}
      role="status"
      data-testid="trade-deadline-ribbon"
    >
      <Clock className="h-3.5 w-3.5 flex-shrink-0" />
      <span data-testid="trade-deadline-ribbon-text">
        Trade deadline in <span className="font-bold">{remaining}</span>
        <span className="ml-2 opacity-70 hidden sm:inline">
          ({new Date(target).toLocaleString(undefined, {
            month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
          })})
        </span>
      </span>
      <Link
        to="/trade-block"
        className="ml-auto underline-offset-2 hover:underline"
        data-testid="trade-deadline-ribbon-cta"
      >
        Open Trade Block →
      </Link>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => {
          try { window.sessionStorage.setItem(dismissKey, "1"); } catch {}
          setDismissed(true);
        }}
        className="ml-1 opacity-60 hover:opacity-100"
        data-testid="trade-deadline-ribbon-dismiss"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

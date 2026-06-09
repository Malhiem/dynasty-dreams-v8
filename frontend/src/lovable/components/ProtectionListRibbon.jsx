// @ts-nocheck
/**
 * Iter 143 — Protection List Submission Ribbon
 *
 * Surfaces a slim dismissible banner whenever the active league has a
 * keeper or expansion draft scheduled AND the protection list deadline
 * is in the future. Hides itself when:
 *   - no relevant draft is scheduled
 *   - the deadline has passed (server-side enforcement takes over)
 *   - the user already submitted their protection list for this season
 *
 * Backend payload (`GET /api/leagues/{id}/protection-list/status`):
 *   {
 *     applicable: bool, draft_type: "keeper" | "expansion",
 *     deadline_at: ISO string | null,
 *     submitted: bool, my_team_id: str | null,
 *   }
 */
import { useEffect, useMemo, useState } from "react";
import { ShieldCheck, X } from "lucide-react";
import { Link } from "react-router-dom";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";

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

export default function ProtectionListRibbon() {
  const { league } = useActiveLeague();
  const [status, setStatus] = useState(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!league?.id) {
      setStatus(null);
      return;
    }
    let cancelled = false;
    api
      .get(`/leagues/${league.id}/protection-list/status`)
      .then(({ data }) => {
        if (!cancelled) setStatus(data || null);
      })
      .catch(() => setStatus(null));
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [league?.id]);

  const target = useMemo(() => {
    if (!status?.deadline_at) return null;
    const d = new Date(status.deadline_at);
    return Number.isNaN(d.getTime()) ? null : d.getTime();
  }, [status?.deadline_at]);

  const dismissKey = `protection-ribbon-dismissed:${status?.deadline_at || ""}:${status?.draft_type || ""}`;
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    return !!window.localStorage.getItem(dismissKey);
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    setDismissed(!!window.localStorage.getItem(dismissKey));
  }, [dismissKey]);

  if (!status?.applicable || !target || status.submitted || dismissed) return null;
  const remaining = fmtRemaining(target);
  if (!remaining) return null;

  const dismiss = () => {
    if (typeof window !== "undefined") window.localStorage.setItem(dismissKey, "1");
    setDismissed(true);
  };

  const label =
    status.draft_type === "keeper"
      ? "Keeper Declaration"
      : "Expansion Protection List";

  return (
    <div
      data-testid="protection-list-ribbon"
      className="bg-emerald-500/10 border-b border-emerald-500/30 px-4 py-2 flex items-center gap-3 text-xs text-emerald-200"
      role="status"
    >
      <ShieldCheck className="h-4 w-4 shrink-0" />
      <div className="flex-1">
        <span className="font-semibold mr-2" data-testid="protection-list-ribbon-label">
          {label}
        </span>
        Submit by:{" "}
        <span className="font-mono" data-testid="protection-list-ribbon-countdown">
          {remaining}
        </span>{" "}
        remaining
      </div>
      <Link
        to="/protection-list"
        className="px-2 py-1 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-100 font-medium"
        data-testid="protection-list-ribbon-submit"
      >
        Submit Protection List
      </Link>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        className="text-emerald-300 hover:text-white"
        data-testid="protection-list-ribbon-dismiss"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

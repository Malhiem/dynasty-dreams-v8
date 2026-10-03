// @ts-nocheck
/**
 * Iter 230aa — Draft stats strip.
 *
 * Compact metrics rendered below the live "On the Clock" / last-pick
 * area in `DraftLiveTile`. Pulls data from
 * `GET /api/drafts/{draft_id}/stats` and re-polls whenever the parent
 * advances `currentPick` (so the strip stays roughly in sync with the
 * board without subscribing to a separate Socket.IO channel).
 *
 * Fields rendered:
 *   • `Pick N / total` — current overall pick over total picks
 *   • `Avg X / pick`   — average elapsed time between picks
 *   • `Fastest: TEAM (Xs)` — team with the lowest avg pick time
 *   • `Slowest: TEAM (Xs)` — team with the highest avg pick time
 *   • `Floor trades: N`    — completed in-draft pick trades
 *
 * All fields gracefully no-op when their value isn't computable yet
 * (e.g. 0 picks made → no deltas → no avg/fastest/slowest).
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Zap, ArrowRightLeft, Clock, Hash } from "lucide-react";

interface Stats {
  current_pick: number;
  total_picks: number;
  picks_made: number;
  avg_seconds_per_pick: number | null;
  fastest: { team: string; avg_seconds: number; picks: number } | null;
  slowest: { team: string; avg_seconds: number; picks: number } | null;
  floor_trades: number;
  latest_floor_trade?: {
    team_a_abbr: string | null;
    team_b_abbr: string | null;
    team_a_picks: string[];
    team_b_picks: string[];
    seconds_ago: number | null;
  } | null;
}

function _fmtSeconds(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function _fmtAgo(s: number | null | undefined): string {
  if (s == null) return "";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function _summariseFloorTrade(t: Stats["latest_floor_trade"]): string {
  if (!t) return "";
  const a = t.team_a_abbr || "?";
  const b = t.team_b_abbr || "?";
  const aPicks = t.team_a_picks?.length ? t.team_a_picks.join(", ") : "—";
  const bPicks = t.team_b_picks?.length ? t.team_b_picks.join(", ") : "—";
  const ago = t.seconds_ago != null ? ` · ${_fmtAgo(t.seconds_ago)}` : "";
  return `Latest: ${a}/${b} swap ${aPicks} ↔ ${bPicks}${ago}`;
}

export default function DraftStatsStrip({
  draftId,
  currentPick,
}: {
  draftId: string | null | undefined;
  currentPick: number;
}) {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    if (!draftId) { setStats(null); return; }
    let cancelled = false;
    api.get(`/drafts/${draftId}/stats`)
      .then((r) => { if (!cancelled) setStats(r.data); })
      .catch(() => { if (!cancelled) setStats(null); });
    return () => { cancelled = true; };
  }, [draftId, currentPick]);

  if (!stats) return null;

  return (
    <div
      className="mt-3 rounded-md border border-border/40 bg-secondary/30 px-2 py-1.5 text-[11px] space-y-1"
      data-testid="draft-stats-strip"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <Hash className="h-3 w-3" />
          <span data-testid="draft-stats-current-pick">
            <span className="text-white font-semibold tabular-nums">{stats.current_pick}</span>
            <span className="opacity-60"> of </span>
            <span className="text-white font-semibold tabular-nums">{stats.total_picks}</span>
          </span>
        </span>
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span data-testid="draft-stats-avg">
            Avg <span className="text-white font-semibold">{_fmtSeconds(stats.avg_seconds_per_pick)}</span>
          </span>
        </span>
      </div>
      {(stats.fastest || stats.slowest) && (
        <div className="flex items-center justify-between gap-2">
          {stats.fastest ? (
            <span
              className="inline-flex items-center gap-1 text-emerald-300"
              data-testid="draft-stats-fastest"
              title={`${stats.fastest.team} averaged ${_fmtSeconds(stats.fastest.avg_seconds)} across ${stats.fastest.picks} pick${stats.fastest.picks === 1 ? "" : "s"}`}
            >
              <Zap className="h-3 w-3" />
              {stats.fastest.team}
              <span className="text-emerald-200/70">({_fmtSeconds(stats.fastest.avg_seconds)})</span>
            </span>
          ) : <span />}
          {stats.slowest ? (
            <span
              className="inline-flex items-center gap-1 text-amber-300"
              data-testid="draft-stats-slowest"
              title={`${stats.slowest.team} averaged ${_fmtSeconds(stats.slowest.avg_seconds)} across ${stats.slowest.picks} pick${stats.slowest.picks === 1 ? "" : "s"}`}
            >
              <Clock className="h-3 w-3" />
              {stats.slowest.team}
              <span className="text-amber-200/70">({_fmtSeconds(stats.slowest.avg_seconds)})</span>
            </span>
          ) : <span />}
        </div>
      )}
      <div className="flex items-center justify-between gap-2">
        <span
          className="inline-flex items-center gap-1 text-muted-foreground"
          data-testid="draft-stats-floor-trades"
          // Iter 230ag — Tooltip shows the most recent floor-trade
          // summary so the count isn't just a number — managers can
          // see WHAT just happened on the draft floor at a glance.
          title={
            stats.latest_floor_trade
              ? _summariseFloorTrade(stats.latest_floor_trade)
              : (stats.floor_trades > 0 ? `${stats.floor_trades} pick trade(s) so far` : "No in-draft pick trades yet")
          }
        >
          <ArrowRightLeft className="h-3 w-3" />
          Floor trades <span className="text-white font-semibold tabular-nums">{stats.floor_trades}</span>
        </span>
      </div>
    </div>
  );
}

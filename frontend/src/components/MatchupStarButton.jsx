// @ts-nocheck
/**
 * Iter 132 — Reusable star toggle + H2H tooltip for any matchup card.
 *
 * Drop this next to a matchup's team names on League Home / Live
 * Scoring / Matchup grids. Internally caches the league's
 * `/matchup-stars` payload on a module-level Map so multiple buttons
 * for the same league share one fetch.
 *
 * Props:
 *   leagueId       — required, scopes the cache + API call.
 *   matchupId      — required, the matchup's `_id`.
 *   homeTeamId/Name + awayTeamId/Name — used to label the streak
 *                    sentence ("Team A has won 3 in a row").
 *   size           — icon px (default 16).
 */
import { useEffect, useMemo, useState } from "react";
import { Star, StarOff, Info } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// Cache: leagueId → { starredIds: Set<string>, h2h: Record<id,obj>, ts: number }
const _cache = new Map();
const _listeners = new Map(); // leagueId → Set<setStateCallback>

const fetchLeagueStars = async (leagueId, force = false) => {
  const now = Date.now();
  const entry = _cache.get(leagueId);
  if (!force && entry && now - entry.ts < 30_000) return entry;
  try {
    const { data } = await api.get(`/matchup-stars?league_id=${leagueId}`);
    const next = {
      starredIds: new Set(data?.starred_ids || []),
      h2h: data?.h2h || {},
      ts: now,
    };
    _cache.set(leagueId, next);
    (_listeners.get(leagueId) || new Set()).forEach((cb) => cb(next));
    return next;
  } catch {
    return entry || { starredIds: new Set(), h2h: {}, ts: now };
  }
};

const subscribe = (leagueId, cb) => {
  if (!_listeners.has(leagueId)) _listeners.set(leagueId, new Set());
  _listeners.get(leagueId).add(cb);
  return () => _listeners.get(leagueId)?.delete(cb);
};

export default function MatchupStarButton({
  leagueId,
  matchupId,
  homeTeamId,
  homeTeamName,
  awayTeamId,
  awayTeamName,
  size = 16,
}) {
  const [state, setState] = useState(() => _cache.get(leagueId) || null);

  useEffect(() => {
    if (!leagueId) return;
    fetchLeagueStars(leagueId).then(setState);
    return subscribe(leagueId, setState);
  }, [leagueId]);

  const isStarred = !!state?.starredIds.has(String(matchupId));
  const h = state?.h2h?.[String(matchupId)] || null;

  const toggle = async (e) => {
    e?.preventDefault?.();
    e?.stopPropagation?.();
    try {
      const { data } = await api.post(`/matchup-stars/${matchupId}`);
      // Update cache + notify all listeners for this league
      const entry = _cache.get(leagueId) || { starredIds: new Set(), h2h: {}, ts: Date.now() };
      const nextSet = new Set(entry.starredIds);
      if (data?.starred) nextSet.add(String(matchupId));
      else nextSet.delete(String(matchupId));
      const next = { ...entry, starredIds: nextSet };
      _cache.set(leagueId, next);
      (_listeners.get(leagueId) || new Set()).forEach((cb) => cb(next));
      toast.success(data?.starred ? "Added to watchlist" : "Removed from watchlist");
    } catch {
      toast.error("Failed to update star — try again.");
    }
  };

  // Build the streak sentence using REAL team names from props
  const streakSentence = useMemo(() => {
    if (!h || !h.streak_wins || h.streak_wins < 1) return null;
    const sid = String(h.streak_team_id || "");
    const teamName =
      sid === String(homeTeamId)
        ? homeTeamName
        : sid === String(awayTeamId)
          ? awayTeamName
          : "—";
    return `${teamName} has won ${h.streak_wins} in a row`;
  }, [h, homeTeamId, awayTeamId, homeTeamName, awayTeamName]);

  // Render the all-time record from HOME team's perspective so the
  // user can read it as `home  away`. Re-orient if backend gave us a
  // different perspective_team_id.
  const allTimeLine = useMemo(() => {
    if (!h?.all_time) return "0-0";
    if (h.perspective_team_id && String(h.perspective_team_id) !== String(homeTeamId)) {
      const [a, b] = String(h.all_time).split("-");
      return `${b}-${a}`;
    }
    return h.all_time;
  }, [h, homeTeamId]);

  const lastSeasonLine = useMemo(() => {
    if (!h?.last_season) return "0-0";
    if (h.perspective_team_id && String(h.perspective_team_id) !== String(homeTeamId)) {
      const [a, b] = String(h.last_season).split("-");
      return `${b}-${a}`;
    }
    return h.last_season;
  }, [h, homeTeamId]);

  return (
    <div className="inline-flex items-center gap-1" data-testid={`matchup-star-row-${matchupId}`}>
      <button
        type="button"
        onClick={toggle}
        aria-label={isStarred ? "Unstar matchup" : "Star matchup"}
        title={isStarred ? "Remove from watchlist" : "Add to watchlist"}
        data-testid={`matchup-star-${matchupId}`}
        className={`transition ${
          isStarred
            ? "text-amber-400 hover:text-amber-300"
            : "text-muted-foreground hover:text-amber-400"
        }`}
      >
        {isStarred ? <Star size={size} fill="currentColor" /> : <StarOff size={size} />}
      </button>

      {h && (
        <TooltipProvider delayDuration={120}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={(e) => e.preventDefault()}
                aria-label="Head-to-head record"
                data-testid={`matchup-h2h-info-${matchupId}`}
                className="text-cyan-300/70 hover:text-cyan-200 cursor-help focus:outline-none"
              >
                <Info size={size - 2} />
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="top"
              className="bg-popover border border-border text-xs"
              data-testid={`matchup-h2h-tooltip-${matchupId}`}
            >
              <div className="space-y-1 min-w-[200px]">
                <div className="font-semibold text-white">Head-to-head</div>
                <div>
                  Lifetime:{" "}
                  <span className="font-mono">{allTimeLine}</span>
                  <span className="text-muted-foreground"> ({homeTeamName || "Home"} – {awayTeamName || "Away"})</span>
                </div>
                <div>
                  Last season:{" "}
                  <span className="font-mono">{lastSeasonLine}</span>
                </div>
                {streakSentence && (
                  <div className="text-rose-300 pt-1 border-t border-border/50 mt-1">
                    🔥 {streakSentence}
                  </div>
                )}
              </div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

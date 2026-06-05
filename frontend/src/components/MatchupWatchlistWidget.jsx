// @ts-nocheck
/**
 * Iter 130 — Matchup Watchlist Widget
 *
 * Renders the current-week matchups with a star toggle + auto-watch reason
 * badges. Starred matchups sort to the top.
 *
 * Reasons surfaced by the backend (`/api/matchup-stars`):
 *   • rivalry           — division opponents
 *   • standings_battle  — within 1 win of each other
 *   • playoff_implications — late season, bubble teams
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Star, StarOff, Swords, BarChart3, Flame } from "lucide-react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const REASON_META = {
  rivalry: {
    label: "Rivalry",
    cls: "bg-violet-500/15 text-violet-300 border-violet-500/40",
    Icon: Swords,
  },
  standings_battle: {
    label: "Standings battle",
    cls: "bg-cyan-500/15 text-cyan-300 border-cyan-500/40",
    Icon: BarChart3,
  },
  playoff_implications: {
    label: "Playoff implications",
    cls: "bg-amber-500/15 text-amber-300 border-amber-500/40",
    Icon: Flame,
  },
};

export default function MatchupWatchlistWidget({ leagueId, week }) {
  const [matchups, setMatchups] = useState([]);
  const [starredIds, setStarredIds] = useState(new Set());
  const [autoWatch, setAutoWatch] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get(`/matchups/${leagueId}/current-week`).catch(() => ({ data: { matchups: [] } })),
      api.get(`/matchup-stars?league_id=${leagueId}${week ? `&week=${week}` : ""}`).catch(() => ({ data: { starred_ids: [], auto_watch: {} } })),
    ]).then(([wkRes, starRes]) => {
      if (cancelled) return;
      setMatchups(wkRes.data?.matchups || []);
      setStarredIds(new Set(starRes.data?.starred_ids || []));
      setAutoWatch(starRes.data?.auto_watch || {});
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId, week]);

  const toggleStar = async (matchupId) => {
    // Optimistic update
    setStarredIds((prev) => {
      const next = new Set(prev);
      if (next.has(matchupId)) next.delete(matchupId);
      else next.add(matchupId);
      return next;
    });
    try {
      const { data } = await api.post(`/matchup-stars/${matchupId}`);
      // Confirm from server
      setStarredIds((prev) => {
        const next = new Set(prev);
        if (data?.starred) next.add(matchupId);
        else next.delete(matchupId);
        return next;
      });
    } catch {
      toast.error("Failed to update star — try again.");
      // Rollback
      setStarredIds((prev) => {
        const next = new Set(prev);
        if (next.has(matchupId)) next.delete(matchupId);
        else next.add(matchupId);
        return next;
      });
    }
  };

  if (!leagueId || (!loading && matchups.length === 0)) return null;

  // Sort: starred first, then auto-watch-with-reasons, then the rest
  const sorted = [...matchups].sort((a, b) => {
    const aS = starredIds.has(String(a._id || a.id));
    const bS = starredIds.has(String(b._id || b.id));
    if (aS !== bS) return aS ? -1 : 1;
    const aR = (autoWatch[String(a._id || a.id)] || []).length;
    const bR = (autoWatch[String(b._id || b.id)] || []).length;
    return bR - aR;
  });

  return (
    <div
      className="surface p-5 mb-6 border border-white/5"
      data-testid="matchup-watchlist-widget"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-heading text-sm font-bold text-white tracking-wider flex items-center gap-2">
          <Star size={14} className="text-amber-400" /> MATCHUP WATCHLIST
        </h3>
        <span className="text-xs text-muted-foreground">
          {starredIds.size} starred · {Object.keys(autoWatch).length} auto-watched
        </span>
      </div>
      <div className="space-y-2">
        {sorted.map((m) => {
          const id = String(m._id || m.id);
          const isStarred = starredIds.has(id);
          const reasons = autoWatch[id] || [];
          return (
            <div
              key={id}
              className={`flex items-center gap-3 px-3 py-2 rounded-md border transition ${
                isStarred
                  ? "bg-amber-500/10 border-amber-500/40"
                  : reasons.length > 0
                    ? "bg-cyan-500/5 border-cyan-500/20"
                    : "bg-white/5 border-white/10"
              }`}
              data-testid={`watchlist-row-${id}`}
            >
              <button
                type="button"
                onClick={() => toggleStar(id)}
                data-testid={`watchlist-star-${id}`}
                aria-label={isStarred ? "Unstar matchup" : "Star matchup"}
                className={`flex-shrink-0 transition ${
                  isStarred ? "text-amber-400 hover:text-amber-300" : "text-muted-foreground hover:text-amber-400"
                }`}
              >
                {isStarred ? <Star size={16} fill="currentColor" /> : <StarOff size={16} />}
              </button>
              <Link
                to="/matchup"
                className="flex-1 flex items-center justify-between gap-3 min-w-0"
                data-testid={`watchlist-link-${id}`}
              >
                <span className="text-sm text-white truncate">
                  {m.away_team_name || "—"}
                  <span className="text-muted-foreground mx-1">vs</span>
                  {m.home_team_name || "—"}
                </span>
                <div className="flex flex-wrap gap-1">
                  {reasons.map((r) => {
                    const meta = REASON_META[r];
                    if (!meta) return null;
                    const Icon = meta.Icon;
                    return (
                      <Badge
                        key={r}
                        variant="outline"
                        className={`${meta.cls} border text-[10px] py-0 px-1.5 gap-1`}
                        data-testid={`watchlist-reason-${r}-${id}`}
                      >
                        <Icon size={10} />
                        {meta.label}
                      </Badge>
                    );
                  })}
                </div>
              </Link>
            </div>
          );
        })}
      </div>
    </div>
  );
}

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
import { Star, StarOff, Swords, BarChart3, Flame, Trophy, Crown, Shield, ArrowUpDown, AlertOctagon, Eye, EyeOff } from "lucide-react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
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
  playoff_clinch: {
    label: "Playoff clinch",
    cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
    Icon: Trophy,
  },
  division_lead: {
    label: "Division lead",
    cls: "bg-blue-500/15 text-blue-300 border-blue-500/40",
    Icon: Shield,
  },
  conference_lead: {
    label: "Conference lead",
    cls: "bg-indigo-500/15 text-indigo-300 border-indigo-500/40",
    Icon: Crown,
  },
  last_place_battle: {
    label: "Last place battle",
    cls: "bg-rose-500/15 text-rose-300 border-rose-500/40",
    Icon: AlertOctagon,
  },
  rank_jump: {
    label: "Rank jump",
    cls: "bg-pink-500/15 text-pink-300 border-pink-500/40",
    Icon: ArrowUpDown,
  },
};

export default function MatchupWatchlistWidget({ leagueId, week }) {
  const [matchups, setMatchups] = useState([]);
  const [starredIds, setStarredIds] = useState(new Set());
  const [autoWatch, setAutoWatch] = useState({});
  const [h2h, setH2h] = useState({});
  const [loading, setLoading] = useState(false);
  // Iter 131 — user-controlled toggle to show/hide the auto-watch
  // matchups. Persisted in localStorage per league so each user keeps
  // their preference.
  const [showAuto, setShowAuto] = useState(() => {
    try {
      const v = localStorage.getItem(`watchlist-show-auto:${leagueId}`);
      return v === null ? true : v === "1";
    } catch { return true; }
  });
  useEffect(() => {
    try { localStorage.setItem(`watchlist-show-auto:${leagueId}`, showAuto ? "1" : "0"); } catch {}
  }, [leagueId, showAuto]);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get(`/matchups/${leagueId}/current-week`).catch(() => ({ data: { matchups: [] } })),
      api.get(`/matchup-stars?league_id=${leagueId}${week ? `&week=${week}` : ""}`).catch(() => ({ data: { starred_ids: [], auto_watch: {}, h2h: {} } })),
    ]).then(([wkRes, starRes]) => {
      if (cancelled) return;
      setMatchups(wkRes.data?.matchups || []);
      setStarredIds(new Set(starRes.data?.starred_ids || []));
      setAutoWatch(starRes.data?.auto_watch || {});
      setH2h(starRes.data?.h2h || {});
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

  // Build visible list:
  //  - Starred matchups are ALWAYS shown.
  //  - Auto-watched matchups (have at least one reason) are shown only when
  //    `showAuto` is true.
  //  - Non-auto-watched, non-starred matchups are always shown for context.
  // Sort: starred → auto-watched (more reasons first) → rest.
  const filtered = matchups.filter((m) => {
    const id = String(m._id || m.id);
    if (starredIds.has(id)) return true;
    const reasons = autoWatch[id] || [];
    if (reasons.length > 0 && !showAuto) return false;
    return true;
  });
  const sorted = [...filtered].sort((a, b) => {
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
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h3 className="font-heading text-sm font-bold text-white tracking-wider flex items-center gap-2">
          <Star size={14} className="text-amber-400" /> MATCHUP WATCHLIST
        </h3>
        <div className="flex items-center gap-3">
          <label
            className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none"
            data-testid="watchlist-show-auto-toggle"
          >
            <input
              type="checkbox"
              checked={showAuto}
              onChange={(e) => setShowAuto(e.target.checked)}
              className="rounded border-border bg-secondary text-amber-400 focus:ring-amber-400/30"
              data-testid="watchlist-show-auto-checkbox"
            />
            {showAuto ? <Eye size={12} /> : <EyeOff size={12} />}
            <span>Auto-watch</span>
          </label>
          <span className="text-xs text-muted-foreground">
            {starredIds.size} starred · {Object.keys(autoWatch).length} auto
          </span>
        </div>
      </div>
      <div className="space-y-2">
        {sorted.map((m) => {
          const id = String(m._id || m.id);
          const isStarred = starredIds.has(id);
          const reasons = autoWatch[id] || [];
          const h = h2h[id];
          // Resolve the streak team name from the matchup's actual team ids
          const streakTeamName = h && h.streak_team_id
            ? (String(h.streak_team_id) === String(m.home_team_id)
                ? m.home_team_name
                : String(h.streak_team_id) === String(m.away_team_id)
                  ? m.away_team_name
                  : null)
            : null;
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
                <div className="flex flex-wrap gap-1 items-center">
                  {reasons.map((r) => {
                    const meta = REASON_META[r];
                    if (!meta) return null;
                    const Icon = meta.Icon;
                    // Iter 131 — Rivalry tag carries the H2H tooltip
                    if (r === "rivalry" && h) {
                      return (
                        <TooltipProvider key={r} delayDuration={120}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge
                                variant="outline"
                                className={`${meta.cls} border text-[10px] py-0 px-1.5 gap-1 cursor-help`}
                                data-testid={`watchlist-reason-${r}-${id}`}
                              >
                                <Icon size={10} />
                                {meta.label}
                                {h.streak_wins >= 3 && (
                                  <span className="ml-1 px-1 rounded bg-rose-500/30 text-rose-100 font-semibold">
                                    🔥{h.streak_wins}
                                  </span>
                                )}
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="bg-popover border border-border text-xs">
                              <div className="space-y-1">
                                <div className="font-semibold">Head-to-head</div>
                                <div>
                                  Lifetime:{" "}
                                  <span className="font-mono">{h.all_time}</span>
                                </div>
                                <div>
                                  Last season:{" "}
                                  <span className="font-mono">{h.last_season}</span>
                                </div>
                                {h.streak_wins >= 1 && streakTeamName && (
                                  <div className="text-rose-300">
                                    🔥 {streakTeamName} has won {h.streak_wins} in a row
                                  </div>
                                )}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      );
                    }
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

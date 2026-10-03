// @ts-nocheck
import { useEffect, useState, useMemo } from "react";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Radio, ChevronRight, Clock, TrendingUp, LayoutList, Rows2 } from "lucide-react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import MatchupStarButton from "@/components/MatchupStarButton";

/**
 * League Live side-rail. Pulls enriched matchup data from
 * `/api/leagues/{id}/matchup-side-rail` (top-3 contributors per side, projected
 * delta, games-remaining-this-week). Refreshes every 30s.
 */

const POLL_MS = 30_000;
const SMOOTH = 25;

function winProb(a, b) {
  const denom = a + b + SMOOTH * 2;
  if (denom <= 0) return 0.5;
  return Math.max(0.01, Math.min(0.99, (a + SMOOTH) / denom));
}

function teamInitials(name = "") {
  return name.split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");
}

function ContributorRow({ c }) {
  return (
    <div className="flex items-center justify-between text-[10px] text-muted-foreground"
      data-testid={`side-rail-contrib-${c.player_id}`}>
      <span className="truncate">
        <span className="text-foreground font-medium">{c.name}</span>
        <span className="ml-1">{c.position}</span>
      </span>
      <span className="tabular-nums text-foreground">{c.fpts.toFixed(1)}</span>
    </div>
  );
}

export function MatchupSideRail({ leagueId, myMatchupId, currentWeek, onSelectMatchup, viewingMatchupId }) {
  const [view, setView] = useState<"compact" | "detailed">(() => {
    try {
      return (localStorage.getItem("dynasty-matchup-sidebar-view") as "compact" | "detailed") || "detailed";
    } catch { return "detailed"; }
  });
  const toggleView = () => {
    setView((v) => {
      const next = v === "compact" ? "detailed" : "compact";
      try { localStorage.setItem("dynasty-matchup-sidebar-view", next); } catch { /* noop */ }
      return next;
    });
  };
  const [matchups, setMatchups] = useState([]);
  // Iter 133 — fetch starred + auto-watch metadata so we can sort + render stars
  const [stars, setStars] = useState({ starredIds: new Set(), autoWatch: {} });

  useEffect(() => {
    if (!leagueId) return undefined;
    let cancelled = false;
    const load = () => api.get(`/matchup-stars?league_id=${leagueId}`)
      .then(({ data }) => {
        if (cancelled) return;
        setStars({
          starredIds: new Set(data?.starred_ids || []),
          autoWatch: data?.auto_watch || {},
        });
      })
      .catch(() => {});
    load();
    const onChange = () => load();
    window.addEventListener("matchup-star-changed", onChange);
    return () => { cancelled = true; window.removeEventListener("matchup-star-changed", onChange); };
  }, [leagueId]);

  useEffect(() => {
    if (!leagueId) return undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/matchup-side-rail`);
        if (cancelled) return;
        setMatchups(data?.matchups || []);
      } catch {
        // best-effort
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [leagueId]);

  // Iter 134 — keep MY matchup pinned at the very top, then starred,
  // then auto-watched (most reasons first), then the rest.
  const otherMatchups = matchups;

  const sortedMatchups = useMemo(() => {
    const arr = [...otherMatchups];
    arr.sort((a, b) => {
      const aMine = myMatchupId && a.matchup_id === myMatchupId;
      const bMine = myMatchupId && b.matchup_id === myMatchupId;
      if (aMine !== bMine) return aMine ? -1 : 1;
      const aId = String(a.matchup_id);
      const bId = String(b.matchup_id);
      const aStar = stars.starredIds.has(aId);
      const bStar = stars.starredIds.has(bId);
      if (aStar !== bStar) return aStar ? -1 : 1;
      const aR = (stars.autoWatch[aId] || []).length;
      const bR = (stars.autoWatch[bId] || []).length;
      return bR - aR;
    });
    return arr;
  }, [otherMatchups, stars, myMatchupId]);

  return (
    <aside className="w-full lg:w-[320px] shrink-0 space-y-3" data-testid="matchup-side-rail">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-1.5">
          <Radio className="h-3.5 w-3.5 text-primary" />
          League Live
          {currentWeek != null && (
            <span className="text-[10px] text-muted-foreground font-normal ml-1">
              · Week {currentWeek}
            </span>
          )}
        </h3>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={toggleView}
            data-testid="side-rail-view-toggle"
            data-view={view}
            title={view === "compact" ? "Switch to detailed view" : "Switch to compact view"}
            className="text-[10px] text-muted-foreground hover:text-primary flex items-center gap-1 px-1.5 py-0.5 rounded border border-border/60 hover:border-primary/60 transition-colors"
          >
            {view === "compact" ? (
              <><LayoutList className="h-3 w-3" /> Detailed</>
            ) : (
              <><Rows2 className="h-3 w-3" /> Compact</>
            )}
          </button>
          <Link
            to="/live"
            data-testid="matchup-live-link"
            className="text-[11px] text-primary hover:underline flex items-center gap-0.5"
          >
            Full View <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
      </div>

      {sortedMatchups.length === 0 && (
        <p className="text-[11px] text-muted-foreground italic" data-testid="matchup-side-rail-empty">
          No live matchups this week.
        </p>
      )}

      {sortedMatchups.map((m) => {
        const a = m.away.current_fpts ?? 0;
        const h = m.home.current_fpts ?? 0;
        const probAway = winProb(a, h);
        const probHome = 1 - probAway;
        const totalGamesLeft = (m.away.games_remaining || 0) + (m.home.games_remaining || 0);
        const isViewing = viewingMatchupId === m.matchup_id;
        const isMine = myMatchupId && m.matchup_id === myMatchupId;
        const isStarred = stars.starredIds.has(String(m.matchup_id));
        const reasonCount = (stars.autoWatch[String(m.matchup_id)] || []).length;

        const sides = [
          { ...m.away, prob: probAway, side: "away" },
          { ...m.home, prob: probHome, side: "home" },
        ];

        return (
          <Card
            key={m.matchup_id}
            data-testid={`matchup-side-rail-card-${m.matchup_id}`}
            onClick={() => onSelectMatchup?.(m)}
            className={`p-3 transition-colors space-y-2 ${
              onSelectMatchup ? "cursor-pointer hover:bg-card hover:border-primary/40" : ""
            } ${isViewing ? "bg-primary/10 border-primary/50 ring-1 ring-primary/30" : isMine ? "bg-primary/5 border-primary/40" : isStarred ? "bg-amber-500/5 border-amber-500/30" : reasonCount > 0 ? "bg-cyan-500/5 border-cyan-500/20" : "bg-card/80"}`}
            data-viewing={isViewing ? "true" : "false"}
          >
            {/* Iter 133 — star + H2H info icon */}
            <div
              className="flex items-center justify-between -mt-1 -mr-1"
              onClick={(e) => e.stopPropagation()}
              data-testid={`matchup-side-rail-star-row-${m.matchup_id}`}
            >
              {isMine ? (
                <Badge
                  variant="outline"
                  className="h-4 text-[9px] px-1.5 border-primary/40 text-primary bg-primary/10"
                  data-testid={`matchup-side-rail-mine-${m.matchup_id}`}
                >
                  MY MATCHUP
                </Badge>
              ) : (
                <span />
              )}
              <MatchupStarButton
                leagueId={leagueId}
                matchupId={m.matchup_id}
                homeTeamId={m.home?.team_id}
                homeTeamName={m.home?.team_name}
                awayTeamId={m.away?.team_id}
                awayTeamName={m.away?.team_name}
                size={14}
              />
            </div>
            {sides.map((row, idx) => (
              <div key={row.team_id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <Avatar className="h-6 w-6 shrink-0">
                    {row.team_logo ? <AvatarImage src={row.team_logo} alt={row.team_name} /> : null}
                    <AvatarFallback className="text-[10px] bg-secondary">
                      {teamInitials(row.team_name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[12px] font-medium truncate">{row.team_name}</span>
                      <span className="text-[12px] font-semibold tabular-nums">
                        {row.current_fpts.toFixed(1)}
                      </span>
                    </div>
                    <div className="h-1 mt-0.5 rounded-full bg-secondary overflow-hidden">
                      <div
                        className={`h-full rounded-full ${row.prob >= 0.5 ? "bg-emerald-500" : "bg-rose-500"}`}
                        style={{ width: `${(row.prob * 100).toFixed(0)}%` }}
                      />
                    </div>
                    {view !== "compact" && (
                      <div className="flex items-center justify-between mt-0.5 gap-2">
                        <span className="text-[10px] text-muted-foreground">
                          Win prob {(row.prob * 100).toFixed(0)}%
                        </span>
                        <span className="text-[10px] text-muted-foreground tabular-nums flex items-center gap-1"
                          data-testid={`side-rail-proj-${row.team_id}`}>
                          <TrendingUp className="h-2.5 w-2.5 text-emerald-400" />
                          Proj {row.projected_final.toFixed(1)}
                          {row.projected_delta > 0 && (
                            <span className="text-emerald-400">(+{row.projected_delta.toFixed(1)})</span>
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Top-3 contributors — hidden in compact view to show just the score. */}
                {view !== "compact" && row.top_contributors && row.top_contributors.length > 0 && (
                  <div className="ml-8 mr-1 space-y-0.5"
                    data-testid={`side-rail-contributors-${row.team_id}`}>
                    {row.top_contributors.slice(0, 3).map((c) => (
                      <ContributorRow key={c.player_id} c={c} />
                    ))}
                  </div>
                )}

                {idx === 0 && (a + h) > 0 && (
                  <div className="ml-8 mr-1 flex items-center justify-end -mt-0.5">
                    <Badge variant="outline" className="h-3.5 text-[9px] px-1 border-primary/30 text-primary">
                      LIVE
                    </Badge>
                  </div>
                )}
              </div>
            ))}

            {/* Footer row: games remaining */}
            {totalGamesLeft > 0 && (
              <div className="pt-1 border-t border-white/5 flex items-center justify-between text-[10px] text-muted-foreground"
                data-testid={`side-rail-games-remaining-${m.matchup_id}`}>
                <span className="flex items-center gap-1">
                  <Clock className="h-2.5 w-2.5" /> {totalGamesLeft} game{totalGamesLeft === 1 ? "" : "s"} remaining
                </span>
                <span className="tabular-nums">
                  {m.away.games_remaining}v{m.home.games_remaining}
                </span>
              </div>
            )}
          </Card>
        );
      })}
    </aside>
  );
}

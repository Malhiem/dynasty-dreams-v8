// @ts-nocheck
import { useState, useCallback, useEffect, useMemo } from "react";
import { useHistoryRequest } from "./history/useHistoryRequest";
import { seasonPlayerAwards, seasonChampions, seasonPresidents, highestPointsRecord, awardCountLeaders } from "./history/awardRecords";
import { HistoryStatus } from "./history/HistoryStatus";
import { Link } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Trophy, Crown, Award, TrendingUp, TrendingDown, Target, Users, BarChart3, Medal, Gift, ArrowRightLeft, UserPlus, UserMinus, ListChecks, History, Download } from "lucide-react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { TrophyRoomView } from "@/lovable/pages/TrophyRoom";

// ─── Streak helpers ────────────────────────────────────────────────────
// A "winning season" = wins > losses; "losing season" = wins < losses;
// ties (W == L) reset both active and longest counters.
type SeasonRow = { year: number; wins: number; losses: number; ties: number; pf: number; pa: number; current?: boolean };
type Streak = { type: "W" | "L"; count: number } | null;

function classifySeason(s: SeasonRow): "W" | "L" | "T" {
  if (s.wins > s.losses) return "W";
  if (s.wins < s.losses) return "L";
  return "T";
}

function computeStreaks(rows: SeasonRow[]): { active: Streak; longest: Streak } {
  if (!rows.length) return { active: null, longest: null };
  // Active streak = trailing run from the latest season backwards
  let active: Streak = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    const t = classifySeason(rows[i]);
    if (t === "T") break;
    if (!active) {
      active = { type: t, count: 1 };
    } else if (active.type === t) {
      active.count += 1;
    } else {
      break;
    }
  }
  // Longest streak = max W or L run anywhere in history
  let longest: Streak = null;
  let cur: { type: "W" | "L"; count: number } | null = null;
  for (const r of rows) {
    const t = classifySeason(r);
    if (t === "T") { cur = null; continue; }
    if (cur && cur.type === t) {
      cur.count += 1;
    } else {
      cur = { type: t, count: 1 };
    }
    if (!longest || cur.count > longest.count) {
      longest = { ...cur };
    }
  }
  return { active, longest };
}

// ─── Dynasty Arc sparkline ─────────────────────────────────────────────
// Tiny 60x16 SVG showing the team's points_for trajectory across seasons,
// with a green/red trend arrow comparing the last 2 seasons. Hover reveals
// per-season tooltip.
function DynastyArc({ rows, testId }: { rows: SeasonRow[]; testId?: string }) {
  if (!rows || rows.length < 1) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const W = 60, H = 16, PAD = 1;
  const max = Math.max(...rows.map((r) => r.pf), 1);
  const min = Math.min(...rows.map((r) => r.pf), 0);
  const range = Math.max(max - min, 1);
  const step = rows.length > 1 ? (W - PAD * 2) / (rows.length - 1) : 0;

  const points = rows.map((r, i) => {
    const x = PAD + step * i;
    const y = H - PAD - ((r.pf - min) / range) * (H - PAD * 2);
    return { x, y, ...r };
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");

  let trend: "up" | "down" | "flat" = "flat";
  if (rows.length >= 2) {
    const a = rows[rows.length - 2].pf;
    const b = rows[rows.length - 1].pf;
    if (b > a) trend = "up";
    else if (b < a) trend = "down";
  }
  const stroke = trend === "up" ? "#10B981" : trend === "down" ? "#EF4444" : "#A1A1AA";
  const tooltip = points
    .map((p) => `${p.year}: ${Math.round(p.pf)} PF · ${p.wins}-${p.losses}-${p.ties}${p.current ? " (live)" : ""}`)
    .join("\n");

  return (
    <span className="inline-flex items-center gap-1" title={tooltip} data-testid={testId}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        <path d={path} fill="none" stroke={stroke} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={i === points.length - 1 ? 1.6 : 1} fill={stroke} opacity={i === points.length - 1 ? 1 : 0.55} />
        ))}
      </svg>
      <span
        aria-hidden
        className="text-[10px] leading-none"
        style={{ color: stroke }}
        data-testid={testId ? `${testId}-trend` : undefined}
      >
        {trend === "up" ? "▲" : trend === "down" ? "▼" : "—"}
      </span>
    </span>
  );
}

const LeagueHistory = () => {
  const { league, leagueTeams } = useActiveLeague();
  const loadHistory = useCallback(async (signal: AbortSignal) => {
    const [s, t, c] = await Promise.all([
      api.get(`/leagues/${league?.id}/seasons?include_team_stats=true`, {signal}),
      api.get(`/leagues/${league?.id}/trophy-room`, {signal}),
      api.get(`/leagues/${league?.id}/team-rewards`, {signal}),
    ]);
    return {seasons: s.data?.seasons || [], trophyData: t.data, consolationWinners: (c.data?.rewards || []).filter((r: any) => r.source === "consolation_winner")};
  }, [league?.id]);
  const historyRequest = useHistoryRequest<any>(league?.id || null, loadHistory);
  const seasons = historyRequest.data?.seasons || [];
  const trophyData = historyRequest.data?.trophyData || null;
  const consolationWinners = historyRequest.data?.consolationWinners || [];
  const loading = historyRequest.loading;
  const [recentChampions, setRecentChampions] = useState<any[]>([]);

  // Live champions = teams with championship_won_at populated (in current season)
  useEffect(() => {
    const champs = (leagueTeams || [])
      .filter((t: any) => t.championship_won_at)
      .sort((a: any, b: any) => new Date(b.championship_won_at).getTime() - new Date(a.championship_won_at).getTime());
    setRecentChampions(champs);
  }, [leagueTeams]);

  // ─── Lifetime Team Records (computed from snapshots) ───
  const lifetimeTeamRecords = useMemo(() => {
    if (!trophyData) return [];
    const tally: Record<string, any> = {};

    const ensure = (tid: string | undefined, name?: string) => {
      if (!tid) return null;
      if (!tally[tid]) {
        tally[tid] = {
          team_id: tid,
          team: name || "—",
          seasons: 0,
          wins: 0,
          losses: 0,
          ties: 0,
          totalPoints: 0,
          totalPointsAgainst: 0,
          championships: 0,
          presidentsTrophies: 0,
          divisionWins: 0,
          conferenceWins: 0,
          seasonRows: [],
        };
      } else if (name) {
        tally[tid].team = name; // freshest name
      }
      return tally[tid];
    };

    // Seed every team that appeared in any season banner
    for (const tb of trophyData.team_banners || []) {
      ensure(tb.team_id, tb.team_name);
    }

    // ─── Sum W/L/T/PF/PA + season count from completed season snapshots ───
    // `seasons` here is the response from /leagues/{id}/seasons?include_team_stats=true
    // and each entry has `team_stats[]` with the snapshot-time totals.
    for (const snap of seasons || []) {
      for (const ts of snap.team_stats || []) {
        const r = ensure(ts.team_id, ts.team_name);
        if (!r) continue;
        r.seasons += 1;
        r.wins += ts.wins || 0;
        r.losses += ts.losses || 0;
        r.ties += ts.ties || 0;
        r.totalPoints += ts.points_for || 0;
        r.totalPointsAgainst += ts.points_against || 0;
        r.seasonRows.push({
          year: snap.season_year,
          wins: ts.wins || 0,
          losses: ts.losses || 0,
          ties: ts.ties || 0,
          pf: ts.points_for || 0,
          pa: ts.points_against || 0,
        });
      }
    }

    // ─── Trophy tally from trophy-room aggregator (championships, etc.) ───
    for (const s of trophyData.seasons || []) {
      for (const winner of seasonChampions(s)) {
        const r = ensure(winner.team_id, winner.team_name);
        if (r) r.championships += 1;
      }
      for (const winner of seasonPresidents(s)) {
        const r = ensure(winner.team_id, winner.team_name);
        if (r) r.presidentsTrophies += 1;
      }
      for (const d of s.division_winners || []) {
        const r = ensure(d.team_id, d.team_name);
        if (r) r.divisionWins += 1;
      }
      for (const c of s.conference_winners || []) {
        const r = ensure(c.team_id, c.team_name);
        if (r) r.conferenceWins += 1;
      }
    }

    // ─── Add LIVE current-season W/L/T/PF for every active team ───
    // If a snapshot for the current year already exists (status != "in_progress"
    // and season_year is in `seasons`), skip — otherwise we'd double count.
    const snapshotYears = new Set((seasons || []).map((s: any) => Number(s.season_year)));
    const currentYear = Number(league?.current_season_year) || new Date().getFullYear();
    const currentYearOpen = !!leagueTeams?.length && !snapshotYears.has(currentYear);
    if (currentYearOpen) {
      for (const t of leagueTeams || []) {
        const r = ensure(t.id, t.name);
        if (!r) continue;
        const liveTotal = (t.wins || 0) + (t.losses || 0) + (t.ties || 0);
        if (liveTotal > 0 || (t.points_for || 0) > 0) {
          // Only count current season once and only if there's gameplay
          r.seasons += 1;
          r.wins += t.wins || 0;
          r.losses += t.losses || 0;
          r.ties += t.ties || 0;
          r.totalPoints += t.points_for || 0;
          r.totalPointsAgainst += t.points_against || 0;
          // Add the live current season as a "current" row (used for arc + streak)
          r.seasonRows.push({
            year: currentYear,
            wins: t.wins || 0,
            losses: t.losses || 0,
            ties: t.ties || 0,
            pf: t.points_for || 0,
            pa: t.points_against || 0,
            current: true,
          });
        } else if (r.seasons === 0) {
          // Brand-new team, no prior snapshots and no games yet — still show as a row
          r.seasons = 1;
        }
      }
    }

    // Sort each team's season rows year ASC for streak + arc rendering
    for (const r of Object.values(tally) as any[]) {
      r.seasonRows.sort((a: any, b: any) => a.year - b.year);
      const streak = computeStreaks(r.seasonRows);
      r.activeStreak = streak.active;       // e.g. { type: 'W', count: 3 } or null
      r.longestStreak = streak.longest;     // e.g. { type: 'W', count: 5 } or null
    }

    const arr = Object.values(tally).map((r: any) => {
      const games = (r.wins || 0) + (r.losses || 0) + (r.ties || 0);
      const winPct = games > 0 ? ((r.wins + r.ties * 0.5) / games).toFixed(3).replace(/^0/, "") : ".000";
      return { ...r, winPct };
    });
    arr.sort(
      (a: any, b: any) =>
        b.championships - a.championships
        || b.wins - a.wins
        || b.totalPoints - a.totalPoints,
    );
    return arr.map((r: any, i: number) => ({ ...r, rank: i + 1 }));
  }, [trophyData, seasons, leagueTeams, league?.current_season_year]);

  // ─── League Records (computed from snapshots + live team data) ───
  const leagueRecords = useMemo(() => {
    if (!trophyData || !lifetimeTeamRecords.length) return null;
    const seasonsList = trophyData.seasons || [];
    const highest = highestPointsRecord(seasonsList);
    const count = Math.max(0, ...lifetimeTeamRecords.map((r: any) => r.championships));
    const holders = count > 0 ? lifetimeTeamRecords.filter((r: any) => r.championships === count).map((r: any) => ({team: r.team, seasons: seasonsList.filter((s: any) => seasonChampions(s).some((t: any) => t.team_id === r.team_id)).map((s: any) => String(s.season_year))})) : [];
    return {
      highestSeasonPoints: highest,
      mostChampionships: {value: count, holders},
      totalSeasons: seasonsList.length,
    };
  }, [trophyData, lifetimeTeamRecords]);

  // ─── Player Awards (per-trophy winners across seasons) ───
  const playerAwards = useMemo(() => {
    if (!trophyData) return [];
    const buckets: Record<string, { name: string; description: string; winners: any[] }> = {
      "Season MVP": {
        name: "Season MVP — Hart Trophy",
        description: "Most fantasy points by a skater across the regular season",
        winners: [],
      },
      "Best Goalie": {
        name: "Best Goalie — Vezina Trophy",
        description: "Most fantasy points by a goaltender",
        winners: [],
      },
      "Best Defenseman": {
        name: "Best Defenseman — Norris Trophy",
        description: "Most fantasy points by a defenseman",
        winners: [],
      },
    };
    for (const s of trophyData.seasons || []) {
      for (const t of seasonPlayerAwards(s)) {
        if (!t) continue;
        const bucket = buckets[t.label];
        if (!bucket) continue;
        bucket.winners.push({
          season: String(s.season_year),
          player: t.player_name,
          playerId: t.player_id,
          position: t.position,
          team: t.owner_team_name || "—",
          fantasyPoints: t.points || 0,
          scoringBasis: t.scoring_basis,
        });
      }
    }
    return Object.values(buckets).filter((b) => b.winners.length > 0);
  }, [trophyData]);

  return (
    <AppLayout>
      <div className="container py-8" data-testid="league-history-page">
        {trophyData?.seasons?.some((s: any) => s.champion_status === "ambiguous") && <p role="alert">Some older championship records have ambiguous franchise names. No champion has been assigned to those records.</p>}
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Trophy className="h-8 w-8 text-primary" />
            League History
          </h1>
          <p className="text-muted-foreground" data-testid="league-history-subtitle">
            {leagueRecords?.totalSeasons
              ? `Celebrating ${leagueRecords.totalSeasons} season${leagueRecords.totalSeasons === 1 ? "" : "s"} of ${league?.name || "dynasty"} hockey`
              : "Records will appear here after the first season is completed"}
          </p>
        </div>

        {!league?.id ? <p role="status">Select a league to view its history.</p> : loading || historyRequest.error ? <HistoryStatus loading={loading} error={historyRequest.error} retry={historyRequest.retry} /> : <Tabs defaultValue="lifetime" className="space-y-6">
          {(recentChampions.length > 0 || consolationWinners.length > 0) && (
            <Card
              className="bg-card/50 backdrop-blur border-amber-500/30"
              data-testid="league-history-recent-crowns"
            >
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Crown className="h-5 w-5 text-amber-400" />
                  Recent Crowns — {league?.name || "This League"}
                </CardTitle>
                <CardDescription>
                  Auto-recorded when playoff final matchups are simulated.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
                    <Trophy className="h-3.5 w-3.5 text-yellow-500" /> Champions
                  </p>
                  {recentChampions.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No champions crowned yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {recentChampions.slice(0, 5).map((t: any) => (
                        <div
                          key={t.id}
                          className="flex items-center gap-2 p-2 rounded-lg border border-amber-500/20 bg-amber-500/5"
                          data-testid={`champion-${t.id}`}
                        >
                          <Trophy className="h-4 w-4 text-yellow-500 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <Link
                              to={`/trophy-room/team/${t.id}`}
                              className="text-sm font-semibold truncate hover:text-amber-300"
                            >
                              {t.name}
                            </Link>
                            <p className="text-[10px] text-muted-foreground">
                              {new Date(t.championship_won_at).toLocaleDateString()} · {t.owner_name || ""}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
                    <Gift className="h-3.5 w-3.5 text-amber-400" /> Consolation Winners
                  </p>
                  {consolationWinners.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No consolation winners yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {consolationWinners.slice(0, 5).map((r: any) => (
                        <div
                          key={r._id}
                          className="flex items-center gap-2 p-2 rounded-lg border border-border bg-secondary/30"
                          data-testid={`consolation-${r._id}`}
                        >
                          <Medal className="h-4 w-4 text-amber-400 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold truncate">{r.team_name || "Team"}</p>
                            <p className="text-[10px] text-muted-foreground truncate">
                              {r.prize?.type?.replace(/_/g, " ") || "prize"}
                              {r.prize?.lottery_boost_spots ? ` · +${r.prize.lottery_boost_spots} spots` : ""}
                              {" · "}{new Date(r.awarded_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
          <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
            <TabsTrigger value="lifetime" className="flex items-center gap-2" data-testid="league-history-tab-lifetime">
              <Users className="h-4 w-4" />
              Lifetime Records
            </TabsTrigger>
            <TabsTrigger value="records" className="flex items-center gap-2" data-testid="league-history-tab-records">
              <Target className="h-4 w-4" />
              League Records
            </TabsTrigger>
            <TabsTrigger value="awards" className="flex items-center gap-2" data-testid="league-history-tab-awards">
              <Award className="h-4 w-4" />
              Player Awards
            </TabsTrigger>
            <TabsTrigger value="transactions" className="flex items-center gap-2" data-testid="league-history-tab-transactions">
              <History className="h-4 w-4" />
              Transactions
            </TabsTrigger>
            <TabsTrigger value="trophyroom" className="flex items-center gap-2" data-testid="league-history-tab-trophy-room">
              <Crown className="h-4 w-4" />
              Trophy Room
            </TabsTrigger>
          </TabsList>

          {/* Lifetime Records Tab */}
          <TabsContent value="lifetime" className="space-y-6">
            <Card className="bg-card/50 backdrop-blur border-border/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-primary" />
                  All-Time Team Standings
                </CardTitle>
                <CardDescription>
                  Lifetime performance records aggregated from completed seasons
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-4 mb-4 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1">🏆 Championship</span>
                  <span className="flex items-center gap-1">🏅 President's Trophy</span>
                  <span className="flex items-center gap-1">🥇 Division Win</span>
                  <span className="flex items-center gap-1">🎯 Conference Win</span>
                  <span className="flex items-center gap-1.5 text-green-400">▲ Arc trending up</span>
                  <span className="flex items-center gap-1.5 text-red-400">▼ Arc trending down</span>
                </div>
                {loading ? (
                  <p className="text-center text-muted-foreground py-8">Loading…</p>
                ) : lifetimeTeamRecords.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8" data-testid="lifetime-records-empty">
                    No team records yet — complete a season to see lifetime stats here.
                  </p>
                ) : (
                  <Table data-testid="lifetime-records-table">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">Rank</TableHead>
                        <TableHead>Team</TableHead>
                        <TableHead className="text-center">Seasons</TableHead>
                        <TableHead className="text-center">W</TableHead>
                        <TableHead className="text-center">L</TableHead>
                        <TableHead className="text-center">Win %</TableHead>
                        <TableHead className="text-right">Total Pts</TableHead>
                        <TableHead className="text-center" title="Current trailing run of winning (W>L) or losing (W<L) seasons">Active Streak</TableHead>
                        <TableHead className="text-center" title="Longest run of consecutive winning or losing seasons">Longest Streak</TableHead>
                        <TableHead className="text-center" title="Dynasty Arc — year-over-year Points For trend (hover for per-season breakdown)">Arc</TableHead>
                        <TableHead className="text-center" title="Championships">🏆</TableHead>
                        <TableHead className="text-center" title="President's Trophy">🏅</TableHead>
                        <TableHead className="text-center" title="Division Wins">🥇</TableHead>
                        <TableHead className="text-center" title="Conference Wins">🎯</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {lifetimeTeamRecords.map((team: any) => (
                        <TableRow
                          key={team.team_id}
                          className={team.rank <= 3 ? "bg-primary/5" : ""}
                          data-testid={`lifetime-row-${team.team_id}`}
                        >
                          <TableCell>
                            {team.rank <= 3 ? (
                              <Badge variant={team.rank === 1 ? "default" : "secondary"} className={
                                team.rank === 1 ? "bg-yellow-500/20 text-yellow-500" :
                                team.rank === 2 ? "bg-gray-400/20 text-gray-400" :
                                "bg-amber-600/20 text-amber-600"
                              }>
                                #{team.rank}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">#{team.rank}</span>
                            )}
                          </TableCell>
                          <TableCell className="font-medium">
                            <Link
                              to={`/trophy-room/team/${team.team_id}`}
                              className="hover:text-primary"
                              data-testid={`lifetime-team-link-${team.team_id}`}
                            >
                              {team.team}
                            </Link>
                          </TableCell>
                          <TableCell className="text-center">{team.seasons}</TableCell>
                          <TableCell className="text-center text-green-500">{team.wins}</TableCell>
                          <TableCell className="text-center text-red-500">{team.losses}</TableCell>
                          <TableCell className="text-center">{team.winPct}</TableCell>
                          <TableCell className="text-right font-semibold">{(team.totalPoints || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</TableCell>
                          <TableCell className="text-center" data-testid={`lifetime-active-streak-${team.team_id}`}>
                            {team.activeStreak ? (
                              <Badge
                                variant="outline"
                                className={team.activeStreak.type === "W"
                                  ? "border-green-500/40 text-green-400"
                                  : "border-red-500/40 text-red-400"}
                              >
                                {team.activeStreak.count}{team.activeStreak.type}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-center" data-testid={`lifetime-longest-streak-${team.team_id}`}>
                            {team.longestStreak ? (
                              <Badge
                                variant="outline"
                                className={team.longestStreak.type === "W"
                                  ? "border-green-500/30 text-green-300"
                                  : "border-red-500/30 text-red-300"}
                              >
                                {team.longestStreak.count}{team.longestStreak.type}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            <DynastyArc rows={team.seasonRows || []} testId={`lifetime-arc-${team.team_id}`} />
                          </TableCell>
                          <TableCell className="text-center">
                            {team.championships > 0
                              ? <span className="text-yellow-500">{"🏆".repeat(team.championships)}</span>
                              : <span className="text-muted-foreground">-</span>}
                          </TableCell>
                          <TableCell className="text-center">
                            {team.presidentsTrophies > 0
                              ? <span>{"🏅".repeat(team.presidentsTrophies)}</span>
                              : <span className="text-muted-foreground">-</span>}
                          </TableCell>
                          <TableCell className="text-center">
                            {team.divisionWins > 0
                              ? <span>{"🥇".repeat(team.divisionWins)}</span>
                              : <span className="text-muted-foreground">-</span>}
                          </TableCell>
                          <TableCell className="text-center">
                            {team.conferenceWins > 0
                              ? <span>{"🎯".repeat(team.conferenceWins)}</span>
                              : <span className="text-muted-foreground">-</span>}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* League Records Tab */}
          <TabsContent value="records" className="space-y-6">
            {!leagueRecords ? (
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardContent className="p-8 text-center text-muted-foreground" data-testid="league-records-empty">
                  No completed seasons yet — records appear here after the first season snapshot.
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                <Card className="bg-card/50 backdrop-blur border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-green-500" />
                      Highest Season Points
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-green-500" data-testid="record-highest-pts-value">
                      {leagueRecords.highestSeasonPoints.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                    </div>
                    {leagueRecords.highestSeasonPoints.holders.map((holder: any) => <div key={`${holder.team_id}-${holder.season}`} data-testid={`record-points-holder-${holder.team_id}-${holder.season}`}><p className="text-sm text-muted-foreground">{holder.team_name}</p><Badge variant="outline" className="mt-2">{holder.season}</Badge></div>)}
                  </CardContent>
                </Card>

                <Card data-testid="record-most-champs-card" className="bg-card/50 backdrop-blur border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <Trophy className="h-4 w-4 text-yellow-500" />
                      Most Championships
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-yellow-500" data-testid="record-most-champs-value">
                      {leagueRecords.mostChampionships.value}
                    </div>
                    {leagueRecords.mostChampionships.holders.length === 0 ? <p>No championships yet.</p> : leagueRecords.mostChampionships.holders.map((holder: any) => <div key={holder.team}><p className="text-sm text-muted-foreground">{holder.team}</p><div className="flex flex-wrap gap-1 mt-2">{holder.seasons.map((year: string) => <Badge key={year} variant="outline" className="text-xs">{year}</Badge>)}</div></div>)}
                  </CardContent>
                </Card>

                <Card className="bg-card/50 backdrop-blur border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <BarChart3 className="h-4 w-4 text-primary" />
                      Total Seasons Played
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-primary" data-testid="record-total-seasons-value">
                      {leagueRecords.totalSeasons}
                    </div>
                    <p className="text-sm text-muted-foreground">Completed dynasty seasons</p>
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          {/* Player Awards Tab */}
          <TabsContent value="awards" className="space-y-6">
            <div className="grid gap-6">
              {playerAwards.length === 0 ? (
                <Card className="bg-card/50 backdrop-blur border-border/50">
                  <CardContent className="p-8 text-center text-muted-foreground" data-testid="player-awards-empty">
                    No player awards yet — they're auto-computed at season completion.
                  </CardContent>
                </Card>
              ) : (
                playerAwards.map((award: any) => {
                  const topWinners = awardCountLeaders(award.winners);
                  return (
                    <Card key={award.name} className="bg-card/50 backdrop-blur border-border/50" data-testid={`player-award-${award.name.replace(/\s+/g, "-").toLowerCase()}`}>
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div>
                            <CardTitle className="flex items-center gap-2">
                              <Award className="h-5 w-5 text-amber-400" />
                              {award.name}
                            </CardTitle>
                            <CardDescription>{award.description}{award.winners.some((w: any) => w.scoringBasis === "legacy_estimate") && " · Older seasons use legacy score estimates."}</CardDescription>
                          </div>
                          {topWinners.map((winner: any) => <Badge key={winner.id} variant="outline" className="shrink-0 border-primary/30 text-primary" data-testid={`player-award-count-${winner.id}`}>{winner.name} — {winner.count}× winner</Badge>)}
                        </div>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Season</TableHead>
                              <TableHead>Player</TableHead>
                              <TableHead className="text-center">Pos</TableHead>
                              <TableHead>Fantasy Team</TableHead>
                              <TableHead className="text-right">FPTS</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {award.winners.map((w: any, i: number) => (
                              <TableRow key={`${w.season}-${w.playerId}`} className={i === 0 ? "bg-primary/5" : ""}>
                                <TableCell>
                                  <Badge variant={i === 0 ? "default" : "outline"} className={i === 0 ? "bg-primary/20 text-primary" : ""}>
                                    {w.season}
                                  </Badge>
                                </TableCell>
                                <TableCell className="font-medium">{w.player}</TableCell>
                                <TableCell className="text-center">
                                  <Badge variant="outline">{w.position}</Badge>
                                </TableCell>
                                <TableCell className="text-muted-foreground">{w.team}</TableCell>
                                <TableCell className="text-right font-semibold">{(w.fantasyPoints || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  );
                })
              )}
            </div>
          </TabsContent>

          {/* Transactions Tab (Iter 124) */}
          <TabsContent value="transactions" className="space-y-6">
            <TransactionsTabContent leagueId={league?.id} leagueTeams={leagueTeams || []} />
          </TabsContent>

          {/* Trophy Room Tab */}
          <TabsContent value="trophyroom" className="space-y-6">
            <div data-testid="league-history-trophy-room">
              <TrophyRoomView leagueId={league?.id} leagueName={league?.name} embedded />
            </div>
          </TabsContent>
        </Tabs>}
      </div>
    </AppLayout>
  );
};

export default LeagueHistory;

// ─── Transactions tab (Iter 124) ──────────────────────────────────────
// Surfaces every roster/trade/lineup move in the league, filtered by
// category (Adds/Drops · Trades · Lineup Changes), by acting team, and
// by player position. Wired to GET /api/leagues/{id}/transactions.

type TxRow = {
  id: string;
  type: string;
  description: string;
  team_id?: string;
  team_name?: string;
  player_id?: string;
  player_name?: string;
  player_position?: string;
  bid_amount?: number;
  winning_team_name?: string;
  winning_bid?: number;
  moves?: Array<{ player_id: string; player_name: string; position: string; from: string; to: string }>;
  move_count?: number;
  created_at?: string;
};

const CATEGORY_OPTIONS = [
  { value: "all", label: "All", icon: ListChecks },
  { value: "adds_drops", label: "Adds & Drops", icon: UserPlus },
  { value: "trades", label: "Trades", icon: ArrowRightLeft },
  { value: "lineup_changes", label: "Lineup Changes", icon: History },
];

const POSITION_OPTIONS = [
  { value: "all", label: "All Positions" },
  { value: "C", label: "C — Center" },
  { value: "W", label: "W — Wing (L/R)" },
  { value: "D", label: "D — Defense" },
  { value: "G", label: "G — Goalie" },
];

function TypeBadge({ type }: { type: string }) {
  const cfg: Record<string, { label: string; cls: string; Icon: any }> = {
    roster_add: { label: "ADD", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40", Icon: UserPlus },
    roster_drop: { label: "DROP", cls: "bg-rose-500/15 text-rose-300 border-rose-500/40", Icon: UserMinus },
    waiver_won: { label: "WAIVER WON", cls: "bg-violet-500/15 text-violet-300 border-violet-500/40", Icon: UserPlus },
    waiver_lost: { label: "WAIVER LOST", cls: "bg-slate-500/15 text-slate-300 border-slate-500/40", Icon: UserMinus },
    trade_executed: { label: "TRADE", cls: "bg-cyan-500/15 text-cyan-300 border-cyan-500/40", Icon: ArrowRightLeft },
    lineup_change: { label: "LINEUP", cls: "bg-amber-500/15 text-amber-300 border-amber-500/40", Icon: History },
  };
  const c = cfg[type] || { label: type.toUpperCase(), cls: "bg-secondary/40 text-foreground border-border", Icon: ListChecks };
  const Icon = c.Icon;
  return (
    <Badge className={`${c.cls} border gap-1 font-semibold`} variant="outline">
      <Icon className="h-3 w-3" />
      {c.label}
    </Badge>
  );
}

function fmtDate(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "2-digit",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

// ─── Iter 129: CSV export helper ───────────────────────────────────────
// Builds a CSV from the currently filtered transactions or trades list and
// triggers a browser download. Shape is intentionally human-readable so
// commissioners can paste into Google Sheets / Discord without preprocessing.
function csvEscape(v: any): string {
  if (v == null) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCSV(filename: string, rows: string[][]) {
  const text = rows.map((r) => r.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([text], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportTransactionsCSV({ isTradeView, tradeStatus, tradeRows, rows, category }: {
  isTradeView: boolean; tradeStatus: string; tradeRows: any[]; rows: TxRow[]; category: string;
}) {
  const stamp = new Date().toISOString().slice(0, 10);
  if (isTradeView) {
    const header = [
      "Status", "From Team", "Assets Sent", "To Team", "Assets Received",
      "Veto Votes", "Approve Votes", "Total Voters", "Conditional",
      "Submitted At", "Processed At",
    ];
    const body = (tradeRows || []).map((t) => [
      t.status,
      t.from_team_name,
      (t.from_assets || []).join(" | "),
      t.to_team_name,
      (t.to_assets || []).join(" | "),
      t.veto_count ?? 0,
      t.approve_count ?? 0,
      t.voters_total ?? 0,
      t.conditional ? "yes" : "",
      t.submitted_at || "",
      t.processed_at || "",
    ]);
    downloadCSV(`trades-${tradeStatus}-${stamp}.csv`, [header, ...body]);
    return;
  }
  const header = [
    "Type", "Team", "Player", "Position", "Description",
    "Bid Amount", "Winning Team", "Winning Bid", "Created At",
  ];
  const body = (rows || []).map((r) => [
    r.type,
    r.team_name || "",
    r.player_name || "",
    r.player_position || "",
    r.description || "",
    r.bid_amount ?? "",
    r.winning_team_name || "",
    r.winning_bid ?? "",
    r.created_at || "",
  ]);
  downloadCSV(`transactions-${category}-${stamp}.csv`, [header, ...body]);
}

function TransactionsTabContent({ leagueId, leagueTeams }: { leagueId?: string; leagueTeams: any[] }) {
  const [rows, setRows] = useState<TxRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState("all");
  const [teamId, setTeamId] = useState("all");
  const [position, setPosition] = useState("all");
  const [limit, setLimit] = useState(50);
  // Iter 125 — trades-specific state. A/B switch between Executed and
  // Vetoed only matters when the Trades category is selected.
  const [tradeStatus, setTradeStatus] = useState<"executed" | "vetoed">("executed");
  const [tradeRows, setTradeRows] = useState<any[]>([]);
  const [tradeLoading, setTradeLoading] = useState(false);

  const isTradeView = category === "trades";

  useEffect(() => {
    if (!leagueId || isTradeView) return;
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (category !== "all") params.set("category", category);
    if (teamId !== "all") params.set("team_id", teamId);
    if (position !== "all") params.set("position", position);
    api
      .get(`/leagues/${leagueId}/transactions?${params.toString()}`)
      .then(({ data }) => { if (!cancelled) setRows(data?.transactions || []); })
      .catch(() => { if (!cancelled) setRows([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId, category, teamId, position, limit, isTradeView]);

  // Iter 125 — fetch trade-history when the Trades category is active.
  useEffect(() => {
    if (!leagueId || !isTradeView) return;
    let cancelled = false;
    setTradeLoading(true);
    const params = new URLSearchParams();
    params.set("status", tradeStatus);
    params.set("limit", String(limit));
    if (teamId !== "all") params.set("team_id", teamId);
    if (position !== "all") params.set("position", position);
    api
      .get(`/leagues/${leagueId}/trade-history?${params.toString()}`)
      .then(({ data }) => { if (!cancelled) setTradeRows(data?.trades || []); })
      .catch(() => { if (!cancelled) setTradeRows([]); })
      .finally(() => { if (!cancelled) setTradeLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId, isTradeView, tradeStatus, teamId, position, limit]);

  const teamLookup = useMemo(() => {
    const m: Record<string, any> = {};
    (leagueTeams || []).forEach((t) => { m[t.id] = t; });
    return m;
  }, [leagueTeams]);

  return (
    <Card className="bg-card border-border" data-testid="league-history-transactions-card">
      <CardHeader>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2">
              <History className="h-5 w-5 text-amber-400" />
              All Transactions
            </CardTitle>
            <CardDescription>
              Every roster move, trade, and lineup change across every team this season.
            </CardDescription>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span data-testid="transactions-result-count">
              {isTradeView
                ? (tradeLoading
                    ? "Loading…"
                    : `${tradeRows.length} ${tradeStatus === "vetoed" ? "vetoed" : "executed"} trade${tradeRows.length === 1 ? "" : "s"}`)
                : (loading ? "Loading…" : `${rows.length} transaction${rows.length === 1 ? "" : "s"}`)}
            </span>
            {/* Iter 129 — CSV export of the current filtered view */}
            <button
              type="button"
              onClick={() => exportTransactionsCSV({
                isTradeView,
                tradeStatus,
                tradeRows,
                rows,
                category,
              })}
              disabled={isTradeView ? (!tradeRows || tradeRows.length === 0) : (!rows || rows.length === 0)}
              data-testid="transactions-export-csv"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <Download className="h-3 w-3" />
              Export CSV
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Filter row */}
        <div className="space-y-3" data-testid="transactions-filter-bar">
          {/* Category pills */}
          <div className="flex flex-wrap gap-2" data-testid="transactions-category-pills">
            {CATEGORY_OPTIONS.map((opt) => {
              const active = category === opt.value;
              const Icon = opt.icon;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setCategory(opt.value)}
                  data-testid={`transactions-category-${opt.value}`}
                  aria-pressed={active}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition ${
                    active
                      ? "bg-amber-500/15 border-amber-500/50 text-amber-200"
                      : "bg-secondary/30 border-border text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {opt.label}
                </button>
              );
            })}
          </div>

          {/* Team + Position selects */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="flex items-center gap-1">
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Team:</span>
              <select
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                data-testid="transactions-team-filter"
                className="bg-secondary/40 border border-border rounded px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-amber-500/40 max-w-[220px]"
              >
                <option value="all">All teams</option>
                {(leagueTeams || []).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>

            <div className="flex flex-wrap gap-1 items-center" data-testid="transactions-position-pills">
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground mr-1">Position:</span>
              {POSITION_OPTIONS.map((opt) => {
                const active = position === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setPosition(opt.value)}
                    data-testid={`transactions-position-${opt.value}`}
                    aria-pressed={active}
                    className={`px-2.5 py-1 rounded-md text-xs border transition ${
                      active
                        ? "bg-cyan-500/15 border-cyan-500/50 text-cyan-200"
                        : "bg-secondary/30 border-border text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                    }`}
                  >
                    {opt.value === "all" ? "All" : opt.value}
                  </button>
                );
              })}
            </div>

            {(category !== "all" || teamId !== "all" || position !== "all") && (
              <button
                type="button"
                onClick={() => { setCategory("all"); setTeamId("all"); setPosition("all"); }}
                data-testid="transactions-clear-filters"
                className="ml-auto px-2.5 py-1 rounded-md text-[11px] border border-rose-500/40 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Result list */}
        {/* Iter 125 — Trades view: A/B switch + tabular history */}
        {isTradeView ? (
          <TradesHistoryView
            tradeRows={tradeRows}
            tradeLoading={tradeLoading}
            tradeStatus={tradeStatus}
            setTradeStatus={setTradeStatus}
            teamLookup={teamLookup}
          />
        ) : loading && rows.length === 0 ? (
          <p className="text-sm text-muted-foreground italic py-6 text-center" data-testid="transactions-loading">
            Loading transactions…
          </p>
        ) : rows.length === 0 ? (
          <div
            className="text-center py-10 border border-dashed border-border rounded-lg"
            data-testid="transactions-empty"
          >
            <History className="h-10 w-10 text-muted-foreground/40 mx-auto mb-2" />
            <p className="text-sm font-medium text-muted-foreground">No transactions match these filters.</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Try clearing a filter or broadening the category.
            </p>
          </div>
        ) : (
          <div className="space-y-2" data-testid="transactions-list">
            {rows.map((tx) => {
              const team = tx.team_id ? teamLookup[tx.team_id] : null;
              return (
                <div
                  key={tx.id}
                  className="flex items-start gap-3 p-3 rounded-lg border border-border bg-secondary/20 hover:bg-secondary/40 transition"
                  data-testid={`transactions-row-${tx.id}`}
                >
                  <div className="flex-shrink-0 pt-0.5">
                    <TypeBadge type={tx.type} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {tx.team_name && (
                        <Link
                          to={team ? `/trophy-room/team/${team.id}` : "#"}
                          className="text-sm font-semibold text-foreground hover:text-amber-300 truncate"
                          data-testid={`transactions-team-link-${tx.id}`}
                        >
                          {tx.team_name}
                        </Link>
                      )}
                      {tx.player_position && (
                        <Badge variant="outline" className="text-[10px] py-0 px-1.5 bg-secondary/60">
                          {tx.player_position}
                        </Badge>
                      )}
                      <span className="text-[10px] text-muted-foreground ml-auto" data-testid={`transactions-time-${tx.id}`}>
                        {fmtDate(tx.created_at)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      {tx.description}
                    </p>
                    {/* Lineup-change moves breakdown */}
                    {tx.moves && tx.moves.length > 0 && (
                      <div className="mt-2 space-y-1" data-testid={`transactions-moves-${tx.id}`}>
                        {tx.moves.slice(0, 5).map((m, i) => (
                          <div
                            key={`${m.player_id}-${i}`}
                            className="flex items-center gap-2 text-[11px] text-muted-foreground"
                          >
                            <span className="font-medium text-foreground/90">{m.player_name}</span>
                            {m.position && (
                              <Badge variant="outline" className="text-[9px] py-0 px-1 bg-secondary/60">
                                {m.position}
                              </Badge>
                            )}
                            <span className="font-mono text-[10px] tracking-tight">
                              <span className="text-rose-300/80">{m.from}</span>
                              <span className="mx-1 text-muted-foreground">→</span>
                              <span className="text-emerald-300">{m.to}</span>
                            </span>
                          </div>
                        ))}
                        {tx.moves.length > 5 && (
                          <p className="text-[10px] text-muted-foreground italic">
                            + {tx.moves.length - 5} more move{tx.moves.length - 5 === 1 ? "" : "s"}
                          </p>
                        )}
                      </div>
                    )}
                    {/* Waiver bid surfacing */}
                    {tx.bid_amount != null && tx.type.startsWith("waiver_") && (
                      <p className="text-[11px] text-violet-300 mt-1">
                        FAAB bid: <span className="font-semibold">${tx.bid_amount}</span>
                        {tx.winning_team_name && tx.winning_team_name !== tx.team_name && (
                          <> · Won by {tx.winning_team_name} (${tx.winning_bid})</>
                        )}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}

            {rows.length >= limit && (
              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={() => setLimit((l) => Math.min(l + 50, 500))}
                  data-testid="transactions-load-more"
                  className="px-4 py-1.5 rounded-md text-xs border border-border bg-secondary/40 hover:bg-secondary/60 text-foreground"
                >
                  Load more ({limit + 50 > 500 ? 500 : limit + 50} max)
                </button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


// ─── Iter 125: Trades History view (A/B switch + table) ───────────────
// When the Trades category is selected on the Transactions tab, render a
// dedicated table view with an Executed/Vetoed A/B switch and explicit
// From / To / Veto-votes / Executed-at columns. Wired to
// GET /api/leagues/{id}/trade-history.

function TradesHistoryView({
  tradeRows,
  tradeLoading,
  tradeStatus,
  setTradeStatus,
  teamLookup,
}: {
  tradeRows: any[];
  tradeLoading: boolean;
  tradeStatus: "executed" | "vetoed";
  setTradeStatus: (s: "executed" | "vetoed") => void;
  teamLookup: Record<string, any>;
}) {
  const stamp = tradeStatus === "vetoed" ? "Vetoed at" : "Executed at";
  return (
    <div className="space-y-3" data-testid="trades-history-view">
      {/* A/B switch */}
      <div
        className="inline-flex items-center rounded-lg border border-border bg-secondary/40 p-1"
        role="tablist"
        data-testid="trades-history-ab-switch"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tradeStatus === "executed"}
          data-testid="trades-history-switch-executed"
          onClick={() => setTradeStatus("executed")}
          className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition ${
            tradeStatus === "executed"
              ? "bg-cyan-500/20 text-cyan-200 shadow-inner"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Trade History
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tradeStatus === "vetoed"}
          data-testid="trades-history-switch-vetoed"
          onClick={() => setTradeStatus("vetoed")}
          className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition ${
            tradeStatus === "vetoed"
              ? "bg-rose-500/20 text-rose-200 shadow-inner"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Vetoed Trades
        </button>
      </div>

      {/* Table */}
      {tradeLoading && tradeRows.length === 0 ? (
        <p className="text-sm text-muted-foreground italic py-6 text-center" data-testid="trades-history-loading">
          Loading trades…
        </p>
      ) : tradeRows.length === 0 ? (
        <div
          className="text-center py-10 border border-dashed border-border rounded-lg"
          data-testid="trades-history-empty"
        >
          <ArrowRightLeft className="h-10 w-10 text-muted-foreground/40 mx-auto mb-2" />
          <p className="text-sm font-medium text-muted-foreground">
            {tradeStatus === "vetoed"
              ? "No vetoed trades — the league has voted everything through."
              : "No executed trades match these filters."}
          </p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            Try clearing a filter or flipping the switch above.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-x-auto" data-testid="trades-history-table-wrapper">
          <Table data-testid="trades-history-table">
            <TableHeader>
              <TableRow>
                <TableHead className="text-[11px] uppercase tracking-wide">From</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wide">Assets sent</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wide w-8 text-center">→</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wide">To</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wide">Assets received</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wide text-center">Votes against</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wide text-right">{stamp}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tradeRows.map((t) => {
                const fromTeam = t.from_team_id ? teamLookup[t.from_team_id] : null;
                const toTeam = t.to_team_id ? teamLookup[t.to_team_id] : null;
                const vetoTone =
                  t.veto_count >= 3
                    ? "bg-rose-500/15 text-rose-300 border-rose-500/40"
                    : t.veto_count > 0
                      ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
                      : "bg-secondary/40 text-muted-foreground border-border";
                return (
                  <TableRow key={t.id} data-testid={`trades-history-row-${t.id}`}>
                    <TableCell>
                      <Link
                        to={fromTeam ? `/trophy-room/team/${fromTeam.id}` : "#"}
                        className="text-sm font-semibold text-foreground hover:text-cyan-300"
                        data-testid={`trades-history-from-${t.id}`}
                      >
                        {t.from_team_name}
                      </Link>
                      {t.conditional && (
                        <Badge variant="outline" className="ml-2 text-[9px] py-0 px-1 bg-violet-500/15 text-violet-300 border-violet-500/40">
                          COND
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1" data-testid={`trades-history-from-assets-${t.id}`}>
                        {(t.from_assets || []).slice(0, 4).map((label: string, i: number) => (
                          <Badge
                            key={`f-${i}`}
                            variant="outline"
                            className="text-[10px] py-0 px-1.5 bg-secondary/60"
                          >
                            {label}
                          </Badge>
                        ))}
                        {t.from_assets && t.from_assets.length > 4 && (
                          <span className="text-[10px] text-muted-foreground italic">
                            +{t.from_assets.length - 4}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-center text-muted-foreground">
                      <ArrowRightLeft className="h-4 w-4 mx-auto text-cyan-300/70" />
                    </TableCell>
                    <TableCell>
                      <Link
                        to={toTeam ? `/trophy-room/team/${toTeam.id}` : "#"}
                        className="text-sm font-semibold text-foreground hover:text-cyan-300"
                        data-testid={`trades-history-to-${t.id}`}
                      >
                        {t.to_team_name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1" data-testid={`trades-history-to-assets-${t.id}`}>
                        {(t.to_assets || []).slice(0, 4).map((label: string, i: number) => (
                          <Badge
                            key={`t-${i}`}
                            variant="outline"
                            className="text-[10px] py-0 px-1.5 bg-secondary/60"
                          >
                            {label}
                          </Badge>
                        ))}
                        {t.to_assets && t.to_assets.length > 4 && (
                          <span className="text-[10px] text-muted-foreground italic">
                            +{t.to_assets.length - 4}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant="outline"
                        className={`${vetoTone} border font-mono text-[11px]`}
                        data-testid={`trades-history-veto-${t.id}`}
                        title={`${t.veto_count} veto · ${t.approve_count} approve · ${t.voters_total} total voters`}
                      >
                        {t.veto_count}
                        {t.voters_total > 0 ? ` / ${t.voters_total}` : ""}
                      </Badge>
                    </TableCell>
                    <TableCell
                      className="text-right text-[11px] text-muted-foreground whitespace-nowrap"
                      data-testid={`trades-history-time-${t.id}`}
                    >
                      {fmtDate(t.processed_at || t.submitted_at)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

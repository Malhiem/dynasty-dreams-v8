// @ts-nocheck
import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Trophy, Crown, Award, TrendingUp, TrendingDown, Target, Users, BarChart3, Medal, Gift } from "lucide-react";
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
  const [seasons, setSeasons] = useState<any[]>([]);
  const [trophyData, setTrophyData] = useState<any>(null);
  const [recentChampions, setRecentChampions] = useState<any[]>([]);
  const [consolationWinners, setConsolationWinners] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!league?.id) return;
    setLoading(true);
    Promise.all([
      api.get(`/leagues/${league.id}/seasons?include_team_stats=true`).then((r) => r.data?.seasons || []).catch(() => []),
      api.get(`/leagues/${league.id}/trophy-room`).then((r) => r.data || null).catch(() => null),
      api.get(`/leagues/${league.id}/team-rewards`)
        .then(({ data }) => (data?.rewards || []).filter((r: any) => r.source === "consolation_winner"))
        .catch(() => []),
    ]).then(([s, t, c]) => {
      setSeasons(s);
      setTrophyData(t);
      setConsolationWinners(c);
    }).finally(() => setLoading(false));
  }, [league?.id]);

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
      if (s.champion?.team_id) {
        const r = ensure(s.champion.team_id, s.champion.team_name);
        if (r) r.championships += 1;
      }
      if (s.presidents_trophy?.team_id) {
        const r = ensure(s.presidents_trophy.team_id, s.presidents_trophy.team_name);
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
    const snapshotYears = new Set((seasons || []).map((s: any) => s.season_year));
    const currentYearOpen = !!leagueTeams?.length && !snapshotYears.has(
      // Heuristic: current_season_year comes from league but we don't have it here;
      // we infer "open" by checking if every team's wins+losses+ties equals 0 → already snapshotted.
      // Simpler: always count live unless we detect a snapshot covers it (best-effort).
      -1,
    );
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
            year: (league?.current_season_year as number) || new Date().getFullYear(),
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
    // Highest season points → from each season's president's trophy team (highest PF that year)
    let highest = { team: "—", value: 0, season: "—" };
    for (const s of seasonsList) {
      const pf = s.presidents_trophy?.points_for || 0;
      if (pf > highest.value) {
        highest = { team: s.presidents_trophy?.team_name || "—", value: pf, season: String(s.season_year) };
      }
    }
    // Most championships
    const champLeader = lifetimeTeamRecords[0];
    const champSeasons = seasonsList
      .filter((s: any) => s.champion?.team_id === champLeader?.team_id)
      .map((s: any) => String(s.season_year));
    return {
      highestSeasonPoints: highest,
      mostChampionships: {
        team: champLeader?.team || "—",
        value: champLeader?.championships || 0,
        seasons: champSeasons,
      },
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
      for (const key of ["season_mvp", "best_goalie", "best_defenseman"] as const) {
        const t = s[key];
        if (!t) continue;
        const bucket = buckets[t.label];
        if (!bucket) continue;
        bucket.winners.push({
          season: String(s.season_year),
          player: t.player_name,
          position: t.position,
          team: t.owner_team_name || "—",
          fantasyPoints: t.points || 0,
        });
      }
    }
    return Object.values(buckets).filter((b) => b.winners.length > 0);
  }, [trophyData]);

  return (
    <AppLayout>
      <div className="container py-8" data-testid="league-history-page">
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

        <Tabs defaultValue="lifetime" className="space-y-6">
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
          <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
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
                    <p className="text-sm text-muted-foreground">{leagueRecords.highestSeasonPoints.team}</p>
                    <Badge variant="outline" className="mt-2">{leagueRecords.highestSeasonPoints.season}</Badge>
                  </CardContent>
                </Card>

                <Card className="bg-card/50 backdrop-blur border-border/50">
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
                    <p className="text-sm text-muted-foreground">{leagueRecords.mostChampionships.team}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {leagueRecords.mostChampionships.seasons.map((s: string) => (
                        <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                      ))}
                    </div>
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
                  const mostWins = award.winners.reduce<Record<string, number>>((acc: any, w: any) => {
                    acc[w.player] = (acc[w.player] || 0) + 1;
                    return acc;
                  }, {});
                  const topWinner = Object.entries(mostWins).sort((a: any, b: any) => b[1] - a[1])[0];
                  return (
                    <Card key={award.name} className="bg-card/50 backdrop-blur border-border/50" data-testid={`player-award-${award.name.replace(/\s+/g, "-").toLowerCase()}`}>
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div>
                            <CardTitle className="flex items-center gap-2">
                              <Award className="h-5 w-5 text-amber-400" />
                              {award.name}
                            </CardTitle>
                            <CardDescription>{award.description}</CardDescription>
                          </div>
                          {topWinner && topWinner[1] > 1 && (
                            <Badge variant="outline" className="shrink-0 border-primary/30 text-primary">
                              {topWinner[0]} — {topWinner[1]}× winner
                            </Badge>
                          )}
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
                              <TableRow key={`${w.season}-${w.player}`} className={i === 0 ? "bg-primary/5" : ""}>
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

          {/* Trophy Room Tab */}
          <TabsContent value="trophyroom" className="space-y-6">
            <div data-testid="league-history-trophy-room">
              <TrophyRoomView leagueId={league?.id} leagueName={league?.name} embedded />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default LeagueHistory;

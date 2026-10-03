// @ts-nocheck
import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { matchupDays, DEFAULT_MY_PLAYERS, DEFAULT_OPP_PLAYERS, makePlayers, matchupPath, normalizeMatchup, type MatchupPlayer } from "./matchup/matchupData";
import { useActiveLeague } from "@/hooks/use-active-league";
import { AppLayout } from "@/components/layout/AppLayout";
import { MatchupSideRail } from "@/lovable/components/matchup/MatchupSideRail";
import RatingChangeBadge from "@/lovable/components/matchup/RatingChangeBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { TrendingUp, TrendingDown, Flame, ChevronLeft, ChevronRight, Grid3X3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import TeamLogo from "@/lovable/components/TeamLogo";
import TeamLink from "@/lovable/components/TeamLink";
import { useNavigate } from "react-router-dom";
import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";
import PullToRefreshIndicator from "@/components/PullToRefreshIndicator";
// Iter 232b — Last-updated freshness pill.
import LastUpdatedBadge from "@/components/LastUpdatedBadge";
// Daily scoring components
import { useDailyScoring } from "@/hooks/use-daily-scoring";
import { DayPillStrip, DailyGrid, WeekSelector } from "@/components/daily-scoring";

type ViewMode = "totals" | "daily" | "grid";

const Matchup = () => {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>("totals");
  const [selectedDayIndex, setSelectedDayIndex] = useState(3); // Thu 2/20 (today)
  const [selectedDay, setSelectedDay] = useState<string | null>(null); // for DayPillStrip
  const [dailyScoringWeek, setDailyScoringWeek] = useState<number | null>(null);

  const { league, leagueTeams, myTeam } = useActiveLeague();
  const [matchup, setMatchup] = useState(null);
  const [myLive, setMyLive] = useState(null);
  const [oppLive, setOppLive] = useState(null);
  // Iter 231au — Pull-to-refresh tick. Threaded into every fetch
  // effect's dep array so a finger-drag forces the matchup grid +
  // live-scoring rails to re-pull from the network.
  // Iter 232a — `onRefresh` now actually awaits the underlying fetches
  // and forces the service worker (stale-while-revalidate) to bypass
  // its cache via `?nocache=1`. Previously it returned a resolved
  // promise immediately, so the spinner snapped back before the
  // network round-trip and the user couldn't tell anything happened.
  const [refreshTick, setRefreshTick] = useState(0);
  // Iter 232b — Freshness timestamp. Bumped whenever any of the
  // matchup-grid / live-scoring fetches successfully resolves.
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const ptr = usePullToRefresh({
    onRefresh: async () => {
      const tasks: Promise<unknown>[] = [];
      if (league?.id) {
        tasks.push(
          api
            .get(matchupPath(league.id, dailyScoringWeek, true))
            .then(({ data }) => setMatchup(normalizeMatchup(data, dailyScoringWeek)))
            .catch(() => undefined),
        );
      }
      if (focusedMyTeam?.id) {
        tasks.push(
          api
            .get(`/live-scoring/team/${focusedMyTeam.id}`)
            .then(({ data }) => setMyLive(data))
            .catch(() => undefined),
        );
      }
      if (opponentTeam?.id) {
        tasks.push(
          api
            .get(`/live-scoring/team/${opponentTeam.id}`)
            .then(({ data }) => setOppLive(data))
            .catch(() => undefined),
        );
      }
      // Also bump refreshTick so any other effects (rating badges,
      // side-rail) that key off it re-run alongside the explicit fetch.
      setRefreshTick((t) => t + 1);
      await Promise.all(tasks);
      setLastUpdatedAt(Date.now());
    },
  });

  // ── Inter-matchup viewer ───────────────────────────────────────
  // When a user clicks a side-rail matchup card, we override the focus from
  // their own matchup to the selected one. Clicking again or hitting "Back to
  // my matchup" resets to null.
  const [viewingMatchup, setViewingMatchup] = useState<any>(null);

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    const path = matchupPath(league.id, dailyScoringWeek);
    setViewingMatchup(null);
    api.get(path).then(({ data }) => {
      if (cancelled) return;
      setMatchup(normalizeMatchup(data, dailyScoringWeek));
      setLastUpdatedAt(Date.now());
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [league?.id, refreshTick, dailyScoringWeek]);

  // Find my matchup (where my team is either home or away)
  const myMatchup = useMemo(() => {
    if (!matchup?.matchups || !myTeam) return null;
    return matchup.matchups.find(m => m.home_team_id === myTeam.id || m.away_team_id === myTeam.id);
  }, [matchup, myTeam]);

  // Active matchup = either the viewed-other matchup or my own. We resolve
  // home/away IDs from `viewingMatchup` (raw side-rail payload) when set.
  const activeHomeTeamId = viewingMatchup
    ? viewingMatchup.home?.team_id
    : (myMatchup?.home_team_id === myTeam?.id ? myTeam?.id : myMatchup?.home_team_id);
  const activeAwayTeamId = viewingMatchup
    ? viewingMatchup.away?.team_id
    : (myMatchup?.home_team_id === myTeam?.id ? myMatchup?.away_team_id : myTeam?.id);

  // For the legacy flow, "my team" = the team in the active home/away pair
  // that the user actually owns (when viewing my own matchup) OR the home
  // team (when viewing someone else's matchup).
  const focusedMyTeam = useMemo(() => {
    if (viewingMatchup) {
      return leagueTeams.find(t => t.id === activeHomeTeamId) || null;
    }
    return myTeam;
  }, [viewingMatchup, leagueTeams, activeHomeTeamId, myTeam]);

  const opponentTeam = useMemo(() => {
    if (viewingMatchup) {
      return leagueTeams.find(t => t.id === activeAwayTeamId) || null;
    }
    if (!myMatchup || !myTeam) return leagueTeams.find(t => t.id !== focusedMyTeam?.id) || null;
    const oppId = myMatchup.home_team_id === myTeam.id ? myMatchup.away_team_id : myMatchup.home_team_id;
    return leagueTeams.find(t => t.id === oppId) || null;
  }, [viewingMatchup, activeAwayTeamId, leagueTeams, myMatchup, myTeam]);

  useEffect(() => {
    const tid = focusedMyTeam?.id;
    if (!tid) return;
    api.get(`/live-scoring/team/${tid}`).then(({data}) => setMyLive(data)).catch(() => {});
  }, [focusedMyTeam, refreshTick]);

  useEffect(() => {
    if (!opponentTeam?.id) return;
    api.get(`/live-scoring/team/${opponentTeam.id}`).then(({data}) => setOppLive(data)).catch(() => {});
  }, [opponentTeam, refreshTick]);

  // Transform live players into MatchupPlayer shape
  // Daily scoring API data
  const currentWeek = matchup?.week;
  const matchupCurrentWeek = currentWeek || 1;
  const matchupTotalWeeks = league?.regular_season_weeks || matchupCurrentWeek;
  const effectiveMatchupWeek = dailyScoringWeek ?? matchupCurrentWeek;
  const { data: myDailyData } = useDailyScoring(
    league?.id, focusedMyTeam?.id, effectiveMatchupWeek
  );
  const { data: oppDailyData } = useDailyScoring(
    league?.id, opponentTeam?.id, effectiveMatchupWeek
  );

  // Derive active matchup days from API or fallback
  const activeDays = useMemo(() => {
    if (myDailyData?.days?.length) return myDailyData.days;
    return [];
  }, [myDailyData]);
  const activeDayLabels = useMemo(() => {
    if (myDailyData?.day_labels?.length) return myDailyData.day_labels;
    return matchupDays;
  }, [myDailyData]);

  const myPlayers: MatchupPlayer[] = useMemo(() => {
    const real = makePlayers(myLive, myDailyData);
    return real.length > 0 ? real : DEFAULT_MY_PLAYERS;
  }, [myLive, myDailyData]);
  const opponentPlayers: MatchupPlayer[] = useMemo(() => {
    const real = makePlayers(oppLive, oppDailyData);
    return real.length > 0 ? real : DEFAULT_OPP_PLAYERS;
  }, [oppLive, oppDailyData]);

  // For the legacy day-selector (used in "daily" pill mode)
  const legacySelectedDay = matchupDays[selectedDayIndex];

  const getDisplayScore = (player: MatchupPlayer) => {
    if (viewMode === "daily") {
      // When a day pill is selected, show that day's score
      if (selectedDay && myDailyData) {
        const label = myDailyData.day_labels[myDailyData.days.indexOf(selectedDay)];
        return player.dailyScores[label] ?? 0;
      }
      return player.dailyScores[legacySelectedDay] ?? 0;
    }
    return player.actual;
  };

  // Compute totals — use API daily totals when available
  const myDailyTotals = myDailyData?.daily_totals || {};
  const oppDailyTotals = oppDailyData?.daily_totals || {};

  const myTotal = viewMode === "daily" && selectedDay
    ? (myDailyTotals[selectedDay] || 0)
    : viewMode === "daily"
      ? myPlayers.reduce((sum, p) => sum + (p.dailyScores[legacySelectedDay] ?? 0), 0)
      : myPlayers.reduce((sum, p) => sum + p.actual, 0);
  const oppTotal = viewMode === "daily" && selectedDay
    ? (oppDailyTotals[selectedDay] || 0)
    : viewMode === "daily"
      ? opponentPlayers.reduce((sum, p) => sum + (p.dailyScores[legacySelectedDay] ?? 0), 0)
      : opponentPlayers.reduce((sum, p) => sum + p.actual, 0);
  const myProjected = myPlayers.reduce((sum, p) => sum + p.projected, 0);
  const oppProjected = opponentPlayers.reduce((sum, p) => sum + p.projected, 0);

  const combinedTotal = myTotal + oppTotal;

  return (
    <AppLayout>
      <PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />
      <div className="container py-8">
        {/* Top-level page tab nav: Matchup vs Live Scoring */}
        <div className="mb-4 flex items-center gap-2 flex-wrap" data-testid="matchup-page-tabs">
          <Button
            size="sm"
            variant="default"
            data-testid="page-tab-matchup"
            className="bg-primary text-primary-foreground"
          >
            My Matchup
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate("/live")}
            data-testid="page-tab-live-scoring"
          >
            Live Scoring (League + NHL)
          </Button>
          {/* Iter 232b — Freshness pill. Pulses green on PTR refresh. */}
          <LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="matchup" />
        </div>
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1 space-y-6 min-w-0">

        {/* "Viewing other matchup" banner — shows when user has clicked a
            League Live card. Reset clears it back to their own matchup. */}
        {viewingMatchup && (
          <div
            className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border border-primary/40 bg-primary/10"
            data-testid="viewing-other-matchup-banner"
          >
            <p className="text-sm">
              <span className="text-[10px] uppercase tracking-widest text-primary font-bold mr-2">
                Viewing
              </span>
              <span className="font-semibold">
                {viewingMatchup.away?.team_name}
              </span>
              <span className="text-muted-foreground mx-1">@</span>
              <span className="font-semibold">
                {viewingMatchup.home?.team_name}
              </span>
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setViewingMatchup(null)}
              data-testid="back-to-my-matchup-btn"
            >
              ← Back to my matchup
            </Button>
          </div>
        )}

        {/* View Toggle */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
            <TabsList>
              <TabsTrigger value="totals" data-testid="matchup-tab-totals">Matchup Totals</TabsTrigger>
              <TabsTrigger value="daily" data-testid="matchup-tab-daily">Daily Scores</TabsTrigger>
              <TabsTrigger value="grid" data-testid="matchup-tab-grid">
                <Grid3X3 className="h-3.5 w-3.5 mr-1" />
                Daily Grid
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {matchup?.week && (
            <span className="text-xs text-muted-foreground flex items-center gap-2">
              <WeekSelector
                currentWeek={matchupCurrentWeek}
                totalWeeks={matchupTotalWeeks}
                selectedWeek={effectiveMatchupWeek}
                onWeekChange={(w) => { setDailyScoringWeek(w); setSelectedDay(null); }}
              />
              {myDailyData?.period_start && (
                <span>{myDailyData.period_start} – {myDailyData.period_end}</span>
              )}
            </span>
          )}
        </div>

        {/* Day Pill Strip (daily mode) */}
        {viewMode === "daily" && activeDays.length > 0 && (
          <DayPillStrip
            days={activeDays}
            dayLabels={activeDayLabels}
            dailyTotals={myDailyTotals}
            selectedDay={selectedDay}
            onSelectDay={setSelectedDay}
            oppDailyTotals={oppDailyTotals}
          />
        )}
        {viewMode === "daily" && activeDays.length === 0 && (
          <div className="grid grid-cols-7 gap-2">
            {matchupDays.map((day, idx) => {
              const myDayTotal = myPlayers.reduce((s, p) => s + (p.dailyScores[day] ?? 0), 0);
              const oppDayTotal = opponentPlayers.reduce((s, p) => s + (p.dailyScores[day] ?? 0), 0);
              const isSelected = idx === selectedDayIndex;
              const isWinning = myDayTotal >= oppDayTotal;
              return (
                <button
                  key={day}
                  onClick={() => setSelectedDayIndex(idx)}
                  className={`rounded-lg p-2 text-center transition-colors border ${
                    isSelected
                      ? "border-primary bg-primary/10"
                      : "border-border bg-secondary/30 hover:bg-secondary/50"
                  }`}
                >
                  <p className="text-[10px] text-muted-foreground font-medium">{day.split(" ")[0]}</p>
                  <p className={`text-sm font-bold ${isWinning ? "text-success" : "text-destructive"}`}>
                    {myDayTotal.toFixed(1)}
                  </p>
                  <p className="text-xs text-muted-foreground">{oppDayTotal.toFixed(1)}</p>
                </button>
              );
            })}
          </div>
        )}

        {/* Matchup Header */}
        <div className="stat-card p-8">
          <div className="flex items-center justify-between">
            <div className="text-center flex-1">
              <TeamLogo logo={focusedMyTeam?.logo_url} name={focusedMyTeam?.name || "—"} abbr={focusedMyTeam?.logo_abbr || "—"} size="lg" className="mx-auto mb-3 rounded-full" />
              <h2 className="text-xl font-bold"><TeamLink name={focusedMyTeam?.name || "—"} id={focusedMyTeam?.id} /></h2>
              <p className="text-muted-foreground text-sm">
                {focusedMyTeam ? `${focusedMyTeam.wins || 0}-${focusedMyTeam.losses || 0}-${focusedMyTeam.ties || 0}` : ''}
                {viewingMatchup && focusedMyTeam?.owner_name
                  ? ` • ${focusedMyTeam.owner_name}`
                  : (league?.name ? ` • ${league.name}` : '')}
              </p>
              {(() => {
                // Show rating change after a simulated week. The matchup record carries
                // `elo_home_delta` + `elo_home_rating_after` (and away equivalents).
                const m = viewingMatchup || myMatchup;
                if (!m || m.status !== "completed") return null;
                const isHome = focusedMyTeam?.id === m.home_team_id;
                const delta = isHome ? m.elo_home_delta : m.elo_away_delta;
                const after = isHome ? m.elo_home_rating_after : m.elo_away_rating_after;
                return (
                  <div className="mt-2">
                    <RatingChangeBadge
                      delta={delta}
                      ratingAfter={after}
                      testId={`matchup-rating-change-home-${focusedMyTeam?.id}`}
                    />
                  </div>
                );
              })()}
            </div>
            
            <div className="text-center px-8">
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <span className="text-4xl font-display text-primary">{myTotal.toFixed(1)}</span>
                  {viewMode === "totals" && (
                    <p className="text-xs text-muted-foreground">Proj: {myProjected.toFixed(1)}</p>
                  )}
                  {viewMode === "daily" && (
                    <p className="text-xs text-muted-foreground">{selectedDay}</p>
                  )}
                </div>
                <span className="text-2xl text-muted-foreground">vs</span>
                <div className="text-left">
                  <span className="text-4xl font-display text-muted-foreground">{oppTotal.toFixed(1)}</span>
                  {viewMode === "totals" && (
                    <p className="text-xs text-muted-foreground">Proj: {oppProjected.toFixed(1)}</p>
                  )}
                  {viewMode === "daily" && (
                    <p className="text-xs text-muted-foreground">{selectedDay}</p>
                  )}
                </div>
              </div>
              <Badge variant="outline" className={`mt-3 ${myTotal >= oppTotal ? 'bg-success/20 text-success border-success/30' : 'bg-destructive/20 text-destructive border-destructive/30'}`}>
                {myTotal >= oppTotal ? <Flame className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                {myTotal >= oppTotal ? "Winning" : "Losing"}
              </Badge>
              {matchup?.week && (
                <p className="text-xs text-muted-foreground mt-2">Week {matchup.week}</p>
              )}
            </div>

            <div className="text-center flex-1">
              <TeamLogo logo={opponentTeam?.logo_url} name={opponentTeam?.name || "—"} abbr={opponentTeam?.logo_abbr || "—"} size="lg" className="mx-auto mb-3 rounded-full" />
              <h2 className="text-xl font-bold"><TeamLink name={opponentTeam?.name || "—"} id={opponentTeam?.id} /></h2>
              <p className="text-muted-foreground text-sm">
                {opponentTeam ? `${opponentTeam.wins || 0}-${opponentTeam.losses || 0}-${opponentTeam.ties || 0}` : ''}
                {opponentTeam?.owner_name ? ` • ${opponentTeam.owner_name}` : ''}
              </p>
              {(() => {
                const m = viewingMatchup || myMatchup;
                if (!m || m.status !== "completed") return null;
                const isHome = opponentTeam?.id === m.home_team_id;
                const delta = isHome ? m.elo_home_delta : m.elo_away_delta;
                const after = isHome ? m.elo_home_rating_after : m.elo_away_rating_after;
                return (
                  <div className="mt-2">
                    <RatingChangeBadge
                      delta={delta}
                      ratingAfter={after}
                      testId={`matchup-rating-change-away-${opponentTeam?.id}`}
                    />
                  </div>
                );
              })()}
            </div>
          </div>

          <div className="mt-6">
            <Progress 
              value={combinedTotal > 0 ? (myTotal / combinedTotal) * 100 : 50} 
              className="h-2 bg-secondary"
            />
          </div>
        </div>

        {/* Daily Grid view (Option C) */}
        {viewMode === "grid" && (
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2 flex items-center gap-2">
                <TeamLogo logo={focusedMyTeam?.logo_url} name={focusedMyTeam?.name || 'ME'} abbr={focusedMyTeam?.logo_abbr || 'ME'} size="xs" />
                {focusedMyTeam?.name || 'My Lineup'}
              </h3>
              <DailyGrid
                days={myDailyData?.days || []}
                dayLabels={myDailyData?.day_labels || []}
                players={myDailyData?.players || []}
                dailyTotals={myDailyTotals}
              />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2 flex items-center gap-2">
                <TeamLogo logo={opponentTeam?.logo_url} name={opponentTeam?.name || 'OPP'} abbr={opponentTeam?.logo_abbr || 'OPP'} size="xs" />
                {opponentTeam?.name || 'Opponent Lineup'}
              </h3>
              <DailyGrid
                days={oppDailyData?.days || []}
                dayLabels={oppDailyData?.day_labels || []}
                players={oppDailyData?.players || []}
                dailyTotals={oppDailyTotals}
              />
            </div>
          </div>
        )}

        {/* Player Comparison (totals + daily modes) */}
        {viewMode !== "grid" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <TeamLogo logo={focusedMyTeam?.logo_url} name={focusedMyTeam?.name || 'ME'} abbr={focusedMyTeam?.logo_abbr || 'ME'} size="xs" />
                {focusedMyTeam?.name || 'My Lineup'}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {myPlayers.map((player) => (
                <PlayerRow key={player.id} player={player} displayScore={getDisplayScore(player)} viewMode={viewMode} isMyTeam />
              ))}
              {myPlayers.length === 0 && (
                <p className="text-sm text-muted-foreground py-6 text-center">No roster data available yet.</p>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <TeamLogo logo={opponentTeam?.logo_url} name={opponentTeam?.name || 'OPP'} abbr={opponentTeam?.logo_abbr || 'OPP'} size="xs" />
                {opponentTeam?.name || 'Opponent Lineup'}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {opponentPlayers.map((player) => (
                <PlayerRow key={player.id} player={player} displayScore={getDisplayScore(player)} viewMode={viewMode} />
              ))}
              {opponentPlayers.length === 0 && (
                <p className="text-sm text-muted-foreground py-6 text-center">No opponent roster loaded.</p>
              )}
            </CardContent>
          </Card>
        </div>
        )}
          </div>
          {league?.id && (
            <MatchupSideRail
              leagueId={league.id}
              myMatchupId={myMatchup?.id}
              currentWeek={matchup?.week}
              viewingMatchupId={viewingMatchup?.matchup_id}
              onSelectMatchup={(m) => setViewingMatchup(m)}
            />
          )}
        </div>
      </div>
    </AppLayout>
  );
};

const formatStatLine = (player: MatchupPlayer): string | null => {
  // Goalies → wins/saves/GA
  if (player.is_goalie) {
    if (!player.games) return null;
    const w = player.wins ?? 0;
    const sv = player.saves ?? 0;
    const ga = player.goals_against ?? 0;
    return `${w}W · ${sv} SVS · ${ga} GA`;
  }
  // Skaters → goals/assists/shots
  if (!player.games && !player.goals && !player.assists && !player.shots) {
    return null;
  }
  const g = player.goals ?? 0;
  const a = player.assists ?? 0;
  const sog = player.shots ?? 0;
  const gp = player.games ?? 0;
  const parts: string[] = [];
  parts.push(`${g}G ${a}A`);
  if (sog) parts.push(`${sog} SOG`);
  if (gp) parts.push(`${gp} GP`);
  return parts.join(" · ");
};

const PlayerRow = ({ player, displayScore, viewMode, isMyTeam }: { player: MatchupPlayer; displayScore: number; viewMode: ViewMode; isMyTeam?: boolean }) => {
  const isOverperforming = player.actual > player.projected;
  const isUnderperforming = player.actual < player.projected && player.actual > 0;
  const statLine = formatStatLine(player);

  return (
    <div
      className="flex items-center justify-between p-3 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors"
      data-testid={`matchup-player-row-${player.id}`}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold shrink-0">
          {player.team}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-medium truncate">{player.name}</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{player.position}</span>
            <span>•</span>
            <span className={`
              ${player.status === "playing" ? "text-success" : ""}
              ${player.status === "done" ? "text-muted-foreground" : ""}
              ${player.status === "upcoming" ? "text-accent" : ""}
            `}>
              {player.status === "playing" && "🟢 Live"}
              {player.status === "done" && "Final"}
              {player.status === "upcoming" && "7:00 PM"}
            </span>
          </div>
          {statLine && (
            <p
              className="text-[11px] text-muted-foreground/90 mt-0.5 font-mono tabular-nums"
              data-testid={`matchup-player-stats-${player.id}`}
            >
              {statLine}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <div className="text-right">
          <p className="font-semibold text-lg tabular-nums">
            {displayScore > 0 ? displayScore.toFixed(1) : "-"}
          </p>
          {viewMode === "totals" && (
            <p className="text-xs text-muted-foreground tabular-nums">
              Proj: {player.projected.toFixed(1)}
            </p>
          )}
        </div>
        {viewMode === "totals" && player.status === "done" && (
          <div className={`${isOverperforming ? "text-success" : isUnderperforming ? "text-destructive" : "text-muted-foreground"}`}>
            {isOverperforming && <TrendingUp className="h-4 w-4" />}
            {isUnderperforming && <TrendingDown className="h-4 w-4" />}
          </div>
        )}
      </div>
    </div>
  );
};

export default Matchup;

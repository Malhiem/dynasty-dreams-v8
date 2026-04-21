// @ts-nocheck
import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { TrendingUp, TrendingDown, Flame, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import TeamLogo from "@/lovable/components/TeamLogo";
import TeamLink from "@/lovable/components/TeamLink";

interface MatchupPlayer {
  id: number;
  name: string;
  position: string;
  team: string;
  projected: number;
  actual: number;
  status: "playing" | "done" | "upcoming";
  dailyScores: Record<string, number>; // date -> points
}

const matchupDays = ["Mon 2/17", "Tue 2/18", "Wed 2/19", "Thu 2/20", "Fri 2/21", "Sat 2/22", "Sun 2/23"];

const makeDailyScores = (total: number, status: string): Record<string, number> => {
  const scores: Record<string, number> = {};
  if (status === "upcoming") return scores;
  const pastDays = status === "done" ? 4 : 3;
  let remaining = total;
  for (let i = 0; i < pastDays; i++) {
    const dayScore = i < pastDays - 1 ? +(Math.random() * (remaining / (pastDays - i)) * 1.5).toFixed(1) : +remaining.toFixed(1);
    const clamped = Math.max(0, Math.min(remaining, dayScore));
    scores[matchupDays[i]] = +clamped.toFixed(1);
    remaining = Math.max(0, remaining - clamped);
  }
  return scores;
};

const DEFAULT_MY_PLAYERS: MatchupPlayer[] = [
  { id: 1, name: "Connor McDavid", position: "C", team: "EDM", projected: 8.5, actual: 12.2, status: "done", dailyScores: { "Mon 2/17": 4.2, "Tue 2/18": 0, "Wed 2/19": 3.8, "Thu 2/20": 4.2 } },
  { id: 2, name: "Nathan MacKinnon", position: "C", team: "COL", projected: 7.2, actual: 5.1, status: "playing", dailyScores: { "Mon 2/17": 2.1, "Tue 2/18": 1.5, "Wed 2/19": 1.5 } },
  { id: 3, name: "Cale Makar", position: "D", team: "COL", projected: 5.8, actual: 0, status: "upcoming", dailyScores: {} },
  { id: 4, name: "Nikita Kucherov", position: "RW", team: "TBL", projected: 6.9, actual: 8.4, status: "done", dailyScores: { "Mon 2/17": 0, "Tue 2/18": 5.2, "Wed 2/19": 0, "Thu 2/20": 3.2 } },
  { id: 5, name: "Igor Shesterkin", position: "G", team: "NYR", projected: 4.2, actual: 0, status: "upcoming", dailyScores: {} },
];

const DEFAULT_OPP_PLAYERS: MatchupPlayer[] = [
  { id: 1, name: "Leon Draisaitl", position: "C", team: "EDM", projected: 7.8, actual: 6.2, status: "done", dailyScores: { "Mon 2/17": 3.1, "Tue 2/18": 0, "Wed 2/19": 1.8, "Thu 2/20": 1.3 } },
  { id: 2, name: "David Pastrnak", position: "RW", team: "BOS", projected: 6.5, actual: 7.8, status: "playing", dailyScores: { "Mon 2/17": 0, "Tue 2/18": 4.6, "Wed 2/19": 3.2 } },
  { id: 3, name: "Quinn Hughes", position: "D", team: "VAN", projected: 5.2, actual: 0, status: "upcoming", dailyScores: {} },
  { id: 4, name: "Kirill Kaprizov", position: "LW", team: "MIN", projected: 6.1, actual: 4.5, status: "done", dailyScores: { "Mon 2/17": 2.2, "Tue 2/18": 0, "Wed 2/19": 0, "Thu 2/20": 2.3 } },
  { id: 5, name: "Andrei Vasilevskiy", position: "G", team: "TBL", projected: 3.8, actual: 0, status: "upcoming", dailyScores: {} },
];

type ViewMode = "totals" | "daily";

const Matchup = () => {
  const [viewMode, setViewMode] = useState<ViewMode>("totals");
  const [selectedDayIndex, setSelectedDayIndex] = useState(3); // Thu 2/20 (today)

  const { league, leagueTeams, myTeam } = useActiveLeague();
  const [matchup, setMatchup] = useState(null);
  const [myLive, setMyLive] = useState(null);
  const [oppLive, setOppLive] = useState(null);

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/matchups/${league.id}/current-week`).then(({data}) => !cancelled && setMatchup(data)).catch(() => {});
    return () => { cancelled = true; };
  }, [league]);

  // Find my matchup (where my team is either home or away)
  const myMatchup = useMemo(() => {
    if (!matchup?.matchups || !myTeam) return null;
    return matchup.matchups.find(m => m.home_team_id === myTeam.id || m.away_team_id === myTeam.id);
  }, [matchup, myTeam]);

  const opponentTeam = useMemo(() => {
    if (!myMatchup || !myTeam) return leagueTeams.find(t => t.id !== myTeam?.id) || null;
    const oppId = myMatchup.home_team_id === myTeam.id ? myMatchup.away_team_id : myMatchup.home_team_id;
    return leagueTeams.find(t => t.id === oppId) || null;
  }, [myMatchup, myTeam, leagueTeams]);

  useEffect(() => {
    if (!myTeam?.id) return;
    api.get(`/live-scoring/team/${myTeam.id}`).then(({data}) => setMyLive(data)).catch(() => {});
  }, [myTeam]);

  useEffect(() => {
    if (!opponentTeam?.id) return;
    api.get(`/live-scoring/team/${opponentTeam.id}`).then(({data}) => setOppLive(data)).catch(() => {});
  }, [opponentTeam]);

  // Transform live players into MatchupPlayer shape
  const makePlayers = (data) => {
    if (!data?.players) return [];
    return data.players.slice(0, 12).map((p, i) => ({
      id: p.id || i,
      name: p.name,
      position: p.position,
      team: p.team,
      projected: +(p.fpts / Math.max(1, p.games) * 7).toFixed(1), // weekly projection
      actual: p.fpts,
      status: p.games > 0 ? "done" : "upcoming",
      dailyScores: { [matchupDays[3]]: p.fpts },
    }));
  };

  const myPlayers: MatchupPlayer[] = useMemo(() => {
    const real = makePlayers(myLive);
    return real.length > 0 ? real : DEFAULT_MY_PLAYERS;
  }, [myLive]);
  const opponentPlayers: MatchupPlayer[] = useMemo(() => {
    const real = makePlayers(oppLive);
    return real.length > 0 ? real : DEFAULT_OPP_PLAYERS;
  }, [oppLive]);

  const selectedDay = matchupDays[selectedDayIndex];

  const getDisplayScore = (player: MatchupPlayer) => {
    if (viewMode === "daily") {
      return player.dailyScores[selectedDay] ?? 0;
    }
    return player.actual;
  };

  const myTotal = viewMode === "daily"
    ? myPlayers.reduce((sum, p) => sum + (p.dailyScores[selectedDay] ?? 0), 0)
    : myPlayers.reduce((sum, p) => sum + p.actual, 0);
  const oppTotal = viewMode === "daily"
    ? opponentPlayers.reduce((sum, p) => sum + (p.dailyScores[selectedDay] ?? 0), 0)
    : opponentPlayers.reduce((sum, p) => sum + p.actual, 0);
  const myProjected = myPlayers.reduce((sum, p) => sum + p.projected, 0);
  const oppProjected = opponentPlayers.reduce((sum, p) => sum + p.projected, 0);

  const combinedTotal = myTotal + oppTotal;

  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        {/* View Toggle */}
        <div className="flex items-center justify-between">
          <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
            <TabsList>
              <TabsTrigger value="totals">Matchup Totals</TabsTrigger>
              <TabsTrigger value="daily">Daily Scores</TabsTrigger>
            </TabsList>
          </Tabs>

          {viewMode === "daily" && (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setSelectedDayIndex(i => Math.max(0, i - 1))}
                disabled={selectedDayIndex <= 0}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm font-semibold min-w-[80px] text-center">{selectedDay}</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setSelectedDayIndex(i => Math.min(matchupDays.length - 1, i + 1))}
                disabled={selectedDayIndex >= matchupDays.length - 1}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        {/* Matchup Header */}
        <div className="stat-card p-8">
          <div className="flex items-center justify-between">
            <div className="text-center flex-1">
              <TeamLogo name={myTeam?.name || "—"} abbr={myTeam?.logo_abbr || "—"} size="lg" className="mx-auto mb-3 rounded-full" />
              <h2 className="text-xl font-bold"><TeamLink name={myTeam?.name || "—"} id={myTeam?.id} /></h2>
              <p className="text-muted-foreground text-sm">
                {myTeam ? `${myTeam.wins || 0}-${myTeam.losses || 0}-${myTeam.ties || 0}` : ''}
                {league?.name ? ` • ${league.name}` : ''}
              </p>
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
              <TeamLogo name={opponentTeam?.name || "—"} abbr={opponentTeam?.logo_abbr || "—"} size="lg" className="mx-auto mb-3 rounded-full" />
              <h2 className="text-xl font-bold"><TeamLink name={opponentTeam?.name || "—"} id={opponentTeam?.id} /></h2>
              <p className="text-muted-foreground text-sm">
                {opponentTeam ? `${opponentTeam.wins || 0}-${opponentTeam.losses || 0}-${opponentTeam.ties || 0}` : ''}
                {opponentTeam?.owner_name ? ` • ${opponentTeam.owner_name}` : ''}
              </p>
            </div>
          </div>

          <div className="mt-6">
            <Progress 
              value={combinedTotal > 0 ? (myTotal / combinedTotal) * 100 : 50} 
              className="h-2 bg-secondary"
            />
          </div>
        </div>

        {/* Daily Score Summary Bar (daily mode) */}
        {viewMode === "daily" && (
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

        {/* Player Comparison */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <div className="h-6 w-6 rounded bg-primary/20 flex items-center justify-center text-xs font-bold text-primary">{myTeam?.logo_abbr || 'ME'}</div>
                {myTeam?.name || 'My Lineup'}
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
                <div className="h-6 w-6 rounded bg-secondary flex items-center justify-center text-xs font-bold text-muted-foreground">{opponentTeam?.logo_abbr || 'OPP'}</div>
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
      </div>
    </AppLayout>
  );
};

const PlayerRow = ({ player, displayScore, viewMode, isMyTeam }: { player: MatchupPlayer; displayScore: number; viewMode: ViewMode; isMyTeam?: boolean }) => {
  const isOverperforming = player.actual > player.projected;
  const isUnderperforming = player.actual < player.projected && player.actual > 0;

  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
          {player.team}
        </div>
        <div>
          <p className="font-medium">{player.name}</p>
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
        </div>
      </div>
      
      <div className="flex items-center gap-3">
        <div className="text-right">
          <p className="font-semibold text-lg">
            {displayScore > 0 ? displayScore.toFixed(1) : "-"}
          </p>
          {viewMode === "totals" && (
            <p className="text-xs text-muted-foreground">
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

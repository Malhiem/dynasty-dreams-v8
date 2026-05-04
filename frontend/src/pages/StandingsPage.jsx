import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trophy, Swords, Play, Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function StandingsPage() {
  const { user } = useAuth();
  const [leagueId, setLeagueId] = useState(null);
  const [leagues, setLeagues] = useState([]);
  const [standings, setStandings] = useState([]);
  const [matchups, setMatchups] = useState([]);
  const [currentWeek, setCurrentWeek] = useState(1);
  const [weekResults, setWeekResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [isCommissioner, setIsCommissioner] = useState(false);

  useEffect(() => {
    const init = async () => {
      try {
        const { data } = await api.get("/leagues?my_leagues=true");
        setLeagues(data);
        if (data.length > 0) {
          setLeagueId(data[0].id);
          setIsCommissioner(data[0].commissioner_id === user?.id);
        }
      } catch (e) { console.error(e); }
    };
    init();
  }, [user]);

  useEffect(() => {
    if (!leagueId) return;
    const fetch = async () => {
      setLoading(true);
      try {
        const [standingsRes, weekRes] = await Promise.all([
          api.get(`/leagues/${leagueId}/standings`),
          api.get(`/matchups/${leagueId}/current-week`),
        ]);
        setStandings(Array.isArray(standingsRes.data) ? standingsRes.data : (standingsRes.data?.standings || []));
        setCurrentWeek(weekRes.data.week);
        setMatchups(weekRes.data.matchups || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    fetch();
  }, [leagueId]);

  const loadWeek = async (week) => {
    try {
      const { data } = await api.get(`/matchups/${leagueId}/results?week=${week}`);
      setWeekResults(data);
      setCurrentWeek(week);
    } catch (e) { console.error(e); }
  };

  const handleGenerateSchedule = async () => {
    setGenerating(true);
    try {
      await api.post("/matchups/generate-schedule", { league_id: leagueId, num_weeks: 18 });
      const { data } = await api.get(`/matchups/${leagueId}/current-week`);
      setCurrentWeek(data.week);
      setMatchups(data.matchups || []);
    } catch (e) { alert(formatApiError(e)); }
    setGenerating(false);
  };

  const handleSimulateWeek = async () => {
    setSimulating(true);
    try {
      const { data } = await api.post("/matchups/simulate-week", { league_id: leagueId, week: currentWeek });
      setWeekResults(data.results || []);
      // Refresh standings
      const standingsRes = await api.get(`/leagues/${leagueId}/standings`);
      setStandings(Array.isArray(standingsRes.data) ? standingsRes.data : (standingsRes.data?.standings || []));
      // Refresh matchups
      const weekRes = await api.get(`/matchups/${leagueId}/current-week`);
      setCurrentWeek(weekRes.data.week);
      setMatchups(weekRes.data.matchups || []);
    } catch (e) { alert(formatApiError(e)); }
    setSimulating(false);
  };

  const displayMatchups = weekResults.length > 0 ? weekResults : matchups;

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="standings-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Trophy className="h-6 w-6 text-[#00D2FF]" />
              Standings & Matchups
            </h1>
            <p className="text-[#A1A1AA]">League standings and weekly matchup results</p>
          </div>
          {leagues.length > 1 && (
            <Select value={leagueId || ""} onValueChange={setLeagueId}>
              <SelectTrigger className="w-48 bg-[#141414] border-white/10 text-white"><SelectValue placeholder="Select League" /></SelectTrigger>
              <SelectContent className="bg-[#141414] border-white/10">
                {leagues.map(l => <SelectItem key={l.id} value={l.id} className="text-white">{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </div>

        {loading ? (
          <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">Loading...</CardContent></Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Standings */}
            <div className="lg:col-span-5">
              <Card className="border-white/10">
                <CardHeader className="pb-3">
                  <CardTitle className="text-white flex items-center gap-2"><Trophy className="h-5 w-5 text-[#00D2FF]" />Standings</CardTitle>
                </CardHeader>
                <CardContent>
                  {standings.length === 0 ? (
                    <p className="text-[#A1A1AA] text-center py-8">No teams yet</p>
                  ) : (
                    <div className="space-y-2">
                      {standings.map((team, idx) => (
                        <div key={team.team_id} className={cn("flex items-center gap-3 p-3 rounded-lg", idx === 0 ? "bg-[#00D2FF]/10 border border-[#00D2FF]/30" : "bg-[#1A1A1A]/30")}>
                          <span className={cn("text-lg font-bold w-8 text-center", idx === 0 ? "text-[#00D2FF]" : "text-[#A1A1AA]")}>
                            {team.rank}
                          </span>
                          <div className="flex-1">
                            <Link
                              to={`/teams/${team.team_id}`}
                              data-testid={`standings-team-link-${team.team_id}`}
                              className="font-medium text-white hover:text-[#00D2FF]"
                            >
                              {team.team_name}
                            </Link>
                            <p className="text-xs text-[#A1A1AA]">{team.owner_name}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold text-white">{team.wins}W-{team.losses}L{team.ties > 0 ? `-${team.ties}T` : ""}</p>
                            <p className="text-xs text-[#A1A1AA]">PF: {team.points_for?.toFixed(1) || 0}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Matchups */}
            <div className="lg:col-span-7">
              <Card className="border-white/10">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-white flex items-center gap-2">
                      <Swords className="h-5 w-5 text-[#00D2FF]" />
                      Week {currentWeek} Matchups
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => loadWeek(Math.max(1, currentWeek - 1))} data-testid="prev-week">
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-sm text-white font-medium">Week {currentWeek}</span>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => loadWeek(currentWeek + 1)} data-testid="next-week">
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {displayMatchups.length === 0 ? (
                    <div className="text-center py-8">
                      <Calendar className="h-12 w-12 text-[#52525B] mx-auto mb-4" />
                      <p className="text-[#A1A1AA] mb-4">No schedule generated yet</p>
                      {isCommissioner && (
                        <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleGenerateSchedule} disabled={generating} data-testid="generate-schedule">
                          <Calendar className="h-4 w-4 mr-2" />
                          {generating ? "Generating..." : "Generate 18-Week Schedule"}
                        </Button>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {displayMatchups.map((m, idx) => {
                        const isResult = m.status === "completed" || m.winner;
                        const homeName = m.home_team_name || m.home;
                        const awayName = m.away_team_name || m.away;
                        const homeScore = m.home_score;
                        const awayScore = m.away_score;
                        const homeWon = isResult && homeScore > awayScore;
                        const awayWon = isResult && awayScore > homeScore;

                        return (
                          <div key={m._id || idx} className="flex items-center gap-4 p-4 rounded-lg bg-[#1A1A1A]/30 border border-white/5">
                            {/* Home */}
                            <div className={cn("flex-1 text-right", homeWon && "text-[#00D2FF]")}>
                              <p className={cn("font-medium", homeWon ? "text-[#00D2FF]" : "text-white")}>{homeName}</p>
                            </div>
                            {/* Score */}
                            <div className="flex items-center gap-2 min-w-[120px] justify-center">
                              {isResult ? (
                                <>
                                  <span className={cn("text-xl font-bold", homeWon ? "text-[#00D2FF]" : "text-white")}>{homeScore}</span>
                                  <span className="text-[#A1A1AA] text-sm">-</span>
                                  <span className={cn("text-xl font-bold", awayWon ? "text-[#00D2FF]" : "text-white")}>{awayScore}</span>
                                </>
                              ) : (
                                <Badge variant="outline" className="text-[#A1A1AA] border-white/20">VS</Badge>
                              )}
                            </div>
                            {/* Away */}
                            <div className={cn("flex-1", awayWon && "text-[#00D2FF]")}>
                              <p className={cn("font-medium", awayWon ? "text-[#00D2FF]" : "text-white")}>{awayName}</p>
                            </div>
                          </div>
                        );
                      })}

                      {isCommissioner && matchups.some(m => m.status === "scheduled") && (
                        <Button className="w-full bg-[#00D2FF] text-black hover:bg-[#33DBFF] mt-4" onClick={handleSimulateWeek} disabled={simulating} data-testid="simulate-week">
                          <Play className="h-4 w-4 mr-2" />
                          {simulating ? "Simulating..." : `Simulate Week ${currentWeek}`}
                        </Button>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

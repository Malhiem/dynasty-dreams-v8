// @ts-nocheck
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";

interface Matchup {
  id: number;
  home: string;
  away: string;
  homeScore: number;
  awayScore: number;
  homeProjection: number;
  awayProjection: number;
  status: "in-progress" | "final" | "upcoming";
}

interface WeekData {
  week: number;
  dateRange: string;
  matchups: Matchup[];
}

const CURRENT_WEEK = 11;

const scheduleData: WeekData[] = [
  {
    week: 10, dateRange: "Feb 24 – Mar 2",
    matchups: [
      { id: 1, home: "Team Frostbite", away: "Blizzard Brigade", homeScore: 142, awayScore: 128, homeProjection: 135, awayProjection: 130, status: "final" },
      { id: 2, home: "Arctic Wolves", away: "Glacier Kings", homeScore: 135, awayScore: 139, homeProjection: 140, awayProjection: 132, status: "final" },
      { id: 3, home: "Ice Crushers", away: "Snow Storm", homeScore: 118, awayScore: 125, homeProjection: 126, awayProjection: 120, status: "final" },
      { id: 4, home: "Frozen Thunder", away: "Puck Masters", homeScore: 131, awayScore: 127, homeProjection: 128, awayProjection: 133, status: "final" },
    ],
  },
  {
    week: 11, dateRange: "Mar 3 – Mar 9",
    matchups: [
      { id: 5, home: "Team Frostbite", away: "Arctic Wolves", homeScore: 86, awayScore: 72, homeProjection: 138, awayProjection: 131, status: "in-progress" },
      { id: 6, home: "Glacier Kings", away: "Snow Storm", homeScore: 64, awayScore: 68, homeProjection: 125, awayProjection: 119, status: "in-progress" },
      { id: 7, home: "Ice Crushers", away: "Blizzard Brigade", homeScore: 55, awayScore: 61, homeProjection: 122, awayProjection: 127, status: "in-progress" },
      { id: 8, home: "Frozen Thunder", away: "Puck Masters", homeScore: 0, awayScore: 0, homeProjection: 130, awayProjection: 126, status: "in-progress" },
    ],
  },
  {
    week: 12, dateRange: "Mar 10 – Mar 16",
    matchups: [
      { id: 9, home: "Glacier Kings", away: "Team Frostbite", homeScore: 0, awayScore: 0, homeProjection: 127, awayProjection: 134, status: "upcoming" },
      { id: 10, home: "Snow Storm", away: "Arctic Wolves", homeScore: 0, awayScore: 0, homeProjection: 121, awayProjection: 136, status: "upcoming" },
      { id: 11, home: "Blizzard Brigade", away: "Frozen Thunder", homeScore: 0, awayScore: 0, homeProjection: 129, awayProjection: 124, status: "upcoming" },
      { id: 12, home: "Puck Masters", away: "Ice Crushers", homeScore: 0, awayScore: 0, homeProjection: 131, awayProjection: 118, status: "upcoming" },
    ],
  },
  {
    week: 13, dateRange: "Mar 17 – Mar 23",
    matchups: [
      { id: 13, home: "Team Frostbite", away: "Frozen Thunder", homeScore: 0, awayScore: 0, homeProjection: 139, awayProjection: 125, status: "upcoming" },
      { id: 14, home: "Arctic Wolves", away: "Ice Crushers", homeScore: 0, awayScore: 0, homeProjection: 133, awayProjection: 120, status: "upcoming" },
      { id: 15, home: "Snow Storm", away: "Glacier Kings", homeScore: 0, awayScore: 0, homeProjection: 117, awayProjection: 128, status: "upcoming" },
      { id: 16, home: "Puck Masters", away: "Blizzard Brigade", homeScore: 0, awayScore: 0, homeProjection: 126, awayProjection: 130, status: "upcoming" },
    ],
  },
];

const LeagueScheduleWidget = () => {
  const [selectedWeek, setSelectedWeek] = useState(CURRENT_WEEK);
  const weekData = scheduleData.find((w) => w.week === selectedWeek);
  const weekIndex = scheduleData.findIndex((w) => w.week === selectedWeek);

  const [liveState, setLiveState] = useState<Record<number, { homeScore: number; awayScore: number; homeProj: number; awayProj: number; progress: number }>>({});

  const initLive = useCallback(() => {
    const initial: Record<number, { homeScore: number; awayScore: number; homeProj: number; awayProj: number; progress: number }> = {};
    scheduleData.forEach((w) =>
      w.matchups.forEach((m) => {
        if (m.status === "in-progress") {
          initial[m.id] = { homeScore: m.homeScore, awayScore: m.awayScore, homeProj: m.homeProjection, awayProj: m.awayProjection, progress: 0.6 };
        }
      })
    );
    return initial;
  }, []);

  useEffect(() => {
    setLiveState(initLive());
    const interval = setInterval(() => {
      setLiveState((prev) => {
        const next = { ...prev };
        for (const id in next) {
          const s = next[id];
          const homeDelta = Math.floor(Math.random() * 4);
          const awayDelta = Math.floor(Math.random() * 4);
          const newProgress = Math.min(s.progress + 0.02, 1);
          const newHome = s.homeScore + homeDelta;
          const newAway = s.awayScore + awayDelta;
          const homeProj = newProgress > 0 ? Math.round(newHome / newProgress) : s.homeProj;
          const awayProj = newProgress > 0 ? Math.round(newAway / newProgress) : s.awayProj;
          next[id] = { homeScore: newHome, awayScore: newAway, homeProj, awayProj, progress: newProgress };
        }
        return next;
      });
    }, 8000);
    return () => clearInterval(interval);
  }, [initLive]);

  const getMatchupData = (m: Matchup) => {
    if (m.status === "in-progress" && liveState[m.id]) {
      return liveState[m.id];
    }
    return { homeScore: m.homeScore, awayScore: m.awayScore, homeProj: m.homeProjection, awayProj: m.awayProjection, progress: 1 };
  };

  const projColor = (currentProj: number, originalProj: number, status: string) => {
    if (status === "upcoming") return "text-muted-foreground";
    if (currentProj >= originalProj) return "text-emerald-400";
    return "text-red-400";
  };

  const isMyTeam = (name: string) => name === "Team Frostbite";

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Calendar className="h-5 w-5 text-primary" />
            League Schedule
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled={weekIndex <= 0} onClick={() => setSelectedWeek(scheduleData[weekIndex - 1].week)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Badge variant={selectedWeek === CURRENT_WEEK ? "default" : "secondary"} className="text-xs cursor-pointer" onClick={() => setSelectedWeek(CURRENT_WEEK)}>
              Wk {selectedWeek}
            </Badge>
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled={weekIndex >= scheduleData.length - 1} onClick={() => setSelectedWeek(scheduleData[weekIndex + 1].week)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {weekData && <p className="text-xs text-muted-foreground mt-1">{weekData.dateRange}</p>}
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-end gap-2 px-3 pb-1">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground w-10 text-right">Score</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground w-10 text-right">Proj</span>
          <span className="w-12" />
        </div>
        {weekData?.matchups.map((matchup) => {
          const data = getMatchupData(matchup);
          const homeWinning = data.homeScore > data.awayScore;
          const awayWinning = data.awayScore > data.homeScore;
          return (
            <div key={matchup.id} className="flex items-center justify-between p-3 rounded-lg bg-muted/30 gap-2">
              <div className="flex-1 min-w-0">
                <p className={`text-sm truncate ${isMyTeam(matchup.home) ? "font-bold text-primary" : "font-medium"}`}>
                  <TeamLink name={matchup.home} className={isMyTeam(matchup.home) ? "text-primary" : ""} />
                </p>
                <p className={`text-sm truncate ${isMyTeam(matchup.away) ? "font-bold text-primary" : "font-medium"}`}>
                  <TeamLink name={matchup.away} className={isMyTeam(matchup.away) ? "text-primary" : ""} />
                </p>
              </div>
              <div className="flex flex-col items-end gap-0.5 w-10">
                {matchup.status === "upcoming" ? (
                  <>
                    <span className="text-sm text-muted-foreground">—</span>
                    <span className="text-sm text-muted-foreground">—</span>
                  </>
                ) : (
                  <>
                    <span className={`text-sm tabular-nums ${homeWinning ? "font-bold" : "text-muted-foreground"}`}>{data.homeScore}</span>
                    <span className={`text-sm tabular-nums ${awayWinning ? "font-bold" : "text-muted-foreground"}`}>{data.awayScore}</span>
                  </>
                )}
              </div>
              <div className="flex flex-col items-end gap-0.5 w-10">
                <span className={`text-xs tabular-nums font-medium ${projColor(data.homeProj, matchup.homeProjection, matchup.status)}`}>{data.homeProj}</span>
                <span className={`text-xs tabular-nums font-medium ${projColor(data.awayProj, matchup.awayProjection, matchup.status)}`}>{data.awayProj}</span>
              </div>
              <div className="w-12 text-right">
                {matchup.status === "final" && (
                  <Badge variant="outline" className="text-[10px] text-muted-foreground">Final</Badge>
                )}
                {matchup.status === "upcoming" && (
                  <Badge variant="outline" className="text-[10px] text-muted-foreground">TBD</Badge>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
};

export default LeagueScheduleWidget;

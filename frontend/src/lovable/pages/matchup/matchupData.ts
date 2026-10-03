// @ts-nocheck
export interface MatchupPlayer {
  id: number | string;
  name: string;
  position: string;
  team: string;
  projected: number;
  actual: number;
  status: "playing" | "done" | "upcoming";
  dailyScores: Record<string, number>; // date -> points
  // Stat breakdown — populated for real (live-scoring) players. Used by
  // the row's secondary line so users can see HOW the FPTS were earned
  // (e.g., "1G 2A · 11 SOG · 3 GP" for skaters, "1W · 28 SVS · 2 GA" for G).
  is_goalie?: boolean;
  goals?: number;
  assists?: number;
  shots?: number;
  saves?: number;
  goals_against?: number;
  wins?: number;
  games?: number;
}

export const matchupDays = ["Mon 2/17", "Tue 2/18", "Wed 2/19", "Thu 2/20", "Fri 2/21", "Sat 2/22", "Sun 2/23"];

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

export const DEFAULT_MY_PLAYERS: MatchupPlayer[] = [
  { id: 1, name: "Connor McDavid", position: "C", team: "EDM", projected: 8.5, actual: 12.2, status: "done", dailyScores: { "Mon 2/17": 4.2, "Tue 2/18": 0, "Wed 2/19": 3.8, "Thu 2/20": 4.2 }, goals: 2, assists: 4, shots: 9, games: 3 },
  { id: 2, name: "Nathan MacKinnon", position: "C", team: "COL", projected: 7.2, actual: 5.1, status: "playing", dailyScores: { "Mon 2/17": 2.1, "Tue 2/18": 1.5, "Wed 2/19": 1.5 }, goals: 1, assists: 1, shots: 6, games: 3 },
  { id: 3, name: "Cale Makar", position: "D", team: "COL", projected: 5.8, actual: 0, status: "upcoming", dailyScores: {} },
  { id: 4, name: "Nikita Kucherov", position: "RW", team: "TBL", projected: 6.9, actual: 8.4, status: "done", dailyScores: { "Mon 2/17": 0, "Tue 2/18": 5.2, "Wed 2/19": 0, "Thu 2/20": 3.2 }, goals: 1, assists: 3, shots: 7, games: 2 },
  { id: 5, name: "Igor Shesterkin", position: "G", team: "NYR", projected: 4.2, actual: 0, status: "upcoming", dailyScores: {}, is_goalie: true },
];

export const DEFAULT_OPP_PLAYERS: MatchupPlayer[] = [
  { id: 1, name: "Leon Draisaitl", position: "C", team: "EDM", projected: 7.8, actual: 6.2, status: "done", dailyScores: { "Mon 2/17": 3.1, "Tue 2/18": 0, "Wed 2/19": 1.8, "Thu 2/20": 1.3 }, goals: 1, assists: 2, shots: 5, games: 3 },
  { id: 2, name: "David Pastrnak", position: "RW", team: "BOS", projected: 6.5, actual: 7.8, status: "playing", dailyScores: { "Mon 2/17": 0, "Tue 2/18": 4.6, "Wed 2/19": 3.2 }, goals: 2, assists: 1, shots: 8, games: 2 },
  { id: 3, name: "Quinn Hughes", position: "D", team: "VAN", projected: 5.2, actual: 0, status: "upcoming", dailyScores: {} },
  { id: 4, name: "Kirill Kaprizov", position: "LW", team: "MIN", projected: 6.1, actual: 4.5, status: "done", dailyScores: { "Mon 2/17": 2.2, "Tue 2/18": 0, "Wed 2/19": 0, "Thu 2/20": 2.3 }, goals: 1, assists: 1, shots: 4, games: 2 },
  { id: 5, name: "Andrei Vasilevskiy", position: "G", team: "TBL", projected: 3.8, actual: 0, status: "upcoming", dailyScores: {}, is_goalie: true },
];


export const makePlayers = (data, dailyData) => {
    if (!data?.players) return [];
    return data.players.slice(0, 12).map((p, i) => {
      // Merge daily scoring data from API when available
      const apiDaily = dailyData?.players?.find(dp => dp.name === p.name);
      let dailyScores: Record<string, number> = {};
      if (apiDaily && dailyData?.day_labels) {
        dailyData.days.forEach((d: string, idx: number) => {
          const label = dailyData.day_labels[idx];
          const dayStats = apiDaily.daily[d];
          if (dayStats) dailyScores[label] = dayStats.fpts;
        });
      } else {
        dailyScores = { [matchupDays[3]]: p.fpts };
      }
      return {
        id: p.id || i,
        name: p.name,
        position: p.position,
        team: p.team,
        projected: +(p.fpts / Math.max(1, p.games) * 7).toFixed(1),
        actual: p.fpts,
        status: p.games > 0 ? "done" : "upcoming",
        dailyScores,
        is_goalie: !!p.is_goalie,
        goals: p.goals || 0,
        assists: p.assists || 0,
        shots: p.shots || 0,
        saves: p.saves || 0,
        goals_against: p.goals_against || 0,
        wins: p.wins || 0,
        games: p.games || 0,
      };
    });
  };


export function matchupPath(leagueId: string, week: number | null, fresh = false) {
  const path = week == null ? `/matchups/${leagueId}/current-week` : `/matchups/${leagueId}/results?week=${week}`;
  return fresh ? `${path}${path.includes("?") ? "&" : "?"}nocache=1` : path;
}

export function normalizeMatchup(data, week: number | null) {
  return Array.isArray(data) ? { week, matchups: data } : data;
}

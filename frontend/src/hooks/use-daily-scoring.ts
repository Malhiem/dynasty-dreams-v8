// @ts-nocheck
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

export interface DailyPlayerStats {
  fpts: number;
  goals: number;
  assists: number;
  shots: number;
  saves: number;
  goals_against: number;
  wins: number;
  games: number;
}

export interface DailyScoringPlayer {
  id: string;
  name: string;
  position: string;
  team: string;
  is_goalie: boolean;
  total_fpts: number;
  total_goals: number;
  total_assists: number;
  total_shots: number;
  total_saves: number;
  total_goals_against: number;
  total_wins: number;
  total_games: number;
  daily: Record<string, DailyPlayerStats>;
}

export interface DailyScoringData {
  league_id: string;
  team_id: string;
  team_name: string;
  week: number;
  scoring_format: string;
  period_start: string;
  period_end: string;
  days: string[];
  day_labels: string[];
  players: DailyScoringPlayer[];
  daily_totals: Record<string, number>;
  period_total_fpts: number;
}

export function useDailyScoring(leagueId?: string, teamId?: string, week?: number) {
  const [data, setData] = useState<DailyScoringData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!leagueId || !teamId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ team_id: teamId });
      if (week != null) params.set("week", String(week));
      const { data: resp } = await api.get(
        `/matchups/${leagueId}/daily-scoring?${params.toString()}`
      );
      setData(resp);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load daily scoring");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [leagueId, teamId, week]);

  useEffect(() => { fetch(); }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

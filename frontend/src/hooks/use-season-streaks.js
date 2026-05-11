// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";

/**
 * Pure helpers — identical logic to LeagueHistory.tsx so the
 * Hot/Cold chip lines up with the Active Streak column on the
 * Lifetime Records table.
 *
 * A "winning season" = wins > losses; "losing season" = wins < losses.
 * Ties (W == L) break both active and longest counters.
 */
export function classifySeason(row) {
  if (row.wins > row.losses) return "W";
  if (row.wins < row.losses) return "L";
  return "T";
}

export function computeStreaks(rows) {
  if (!rows || !rows.length) return { active: null, longest: null };
  let active = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    const t = classifySeason(rows[i]);
    if (t === "T") break;
    if (!active) active = { type: t, count: 1 };
    else if (active.type === t) active.count += 1;
    else break;
  }
  let longest = null;
  let cur = null;
  for (const r of rows) {
    const t = classifySeason(r);
    if (t === "T") { cur = null; continue; }
    if (cur && cur.type === t) cur.count += 1;
    else cur = { type: t, count: 1 };
    if (!longest || cur.count > longest.count) longest = { ...cur };
  }
  return { active, longest };
}

/**
 * useSeasonStreaks(leagueId)
 *
 * One network call per league. Returns a Record<teamId, { active, longest }>.
 *
 * Consumers:
 *   - Standings: render 🔥 Hot / 🥶 Cold chip next to each team name
 *   - Dashboard: same chip on the user's team tile
 *   - LeagueHistory.tsx: already computes its own (deliberately duplicated
 *     to avoid an extra hook there since it already needs the raw rows)
 */
export function useSeasonStreaks(leagueId) {
  const [streaks, setStreaks] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) {
      setStreaks({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .get(`/leagues/${leagueId}/seasons?include_team_stats=true`)
      .then((res) => {
        if (cancelled) return;
        const rowsByTeam = {};
        for (const snap of res.data?.seasons || []) {
          for (const ts of snap.team_stats || []) {
            if (!ts.team_id) continue;
            (rowsByTeam[ts.team_id] = rowsByTeam[ts.team_id] || []).push({
              year: snap.season_year,
              wins: ts.wins || 0,
              losses: ts.losses || 0,
              ties: ts.ties || 0,
            });
          }
        }
        const out = {};
        for (const [tid, rows] of Object.entries(rowsByTeam)) {
          rows.sort((a, b) => a.year - b.year);
          out[tid] = computeStreaks(rows);
        }
        setStreaks(out);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [leagueId]);

  return { streaks, loading };
}

/**
 * Format a streak as a 🔥 Hot / 🥶 Cold chip threshold (3+).
 * Returns null when no chip should be shown.
 */
export function streakChip(activeStreak) {
  if (!activeStreak || activeStreak.count < 3) return null;
  if (activeStreak.type === "W") {
    return { emoji: "🔥", label: "Hot", count: activeStreak.count, tone: "hot" };
  }
  return { emoji: "🥶", label: "Cold", count: activeStreak.count, tone: "cold" };
}

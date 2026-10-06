export const seasonPlayerAwards = (season: any) => season.player_awards ?? [season.season_mvp, season.best_goalie, season.best_defenseman].filter(Boolean);
export const seasonChampions = (season: any) => season.champions ?? [season.champion].filter(Boolean);
export const seasonPresidents = (season: any) => season.presidents_trophies ?? [season.presidents_trophy].filter(Boolean);

export function highestPointsRecord(seasons: any[]) {
  const entries = seasons.flatMap(s => seasonPresidents(s).map((t: any) => ({...t, season: s.season_year})));
  if (!entries.length) return {value: 0, holders: []};
  const value = Math.max(...entries.map(t => Number(t.points_for || 0)));
  return {value, holders: entries.filter(t => Number(t.points_for || 0) === value)};
}

export function awardCountLeaders(winners: any[]) {
  const counts = new Map<string, {id: string; name: string; count: number}>();
  for (const winner of winners) {
    // Legacy rows with no ID remain separate; names never serve as identity.
    const id = winner.playerId || `legacy:${winner.season}:${counts.size}`;
    const entry = counts.get(id) || {id, name: winner.player, count: 0};
    entry.count += 1; counts.set(id, entry);
  }
  const max = Math.max(0, ...[...counts.values()].map(e => e.count));
  return max > 1 ? [...counts.values()].filter(e => e.count === max) : [];
}

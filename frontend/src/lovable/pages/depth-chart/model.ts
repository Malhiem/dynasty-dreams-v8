export const seasonLabel = (year: number) => `${year}-${String(year + 1).slice(-2)}`;
export const money = (value: number) => `$${(value / 1e6).toFixed(2)}M`;
export const points = (value: number) => Math.round(value * 100) / 100;
// Planning season length is explicit and shared by both linked inputs.
export const PLANNING_SEASON_GAMES = 84;
export const totalFromPerGame = (perGame: number) => points(perGame * PLANNING_SEASON_GAMES);
export const perGameFromTotal = (total: number) => Math.round(total / PLANNING_SEASON_GAMES * 10000) / 10000;
export function positionMatches(player: any, position: string) {
  if (position === 'all') return true;
  const positions = String(player.position || '').toUpperCase().split(/[\s,\/|;-]+/);
  return positions.includes(position) || (position === 'F' && positions.some(p => ['C', 'LW', 'RW', 'F'].includes(p)));
}
export function historicalAverage(history: any[], years: number, baseYear: number) {
  const rows = (history || []).filter(r => r.year >= baseYear - years && r.year < baseYear && Number.isFinite(r.pf));
  return { rows, count: rows.length, average: rows.length ? points(rows.reduce((sum, r) => sum + r.pf, 0) / rows.length) : null };
}
export function isProjected(player: any, year: number) {
  return !player.planning_minor || (player.nhl_start_year != null && year >= player.nhl_start_year);
}
export function planValues(player: any, year: number, season: any) {
  const pending = year < Number(player.contract?.start_year ?? year);
  const signed = Object.prototype.hasOwnProperty.call(player.charges || {}, String(year));
  const entered = Object.prototype.hasOwnProperty.call(season.estimates || {}, player.id);
  return { signed, pending, projected: isProjected(player, year), entered, salary: !isProjected(player, year) || pending ? 0 : signed ? player.charges[String(year)] : Number(season.estimates?.[player.id] || 0),
    pf: !isProjected(player, year) ? 0 : Number(season.pf?.[player.id] ?? player.fantasy_points ?? 0), source: season.sources?.[player.id] || 'Current PF baseline' };
}
export function seasonTotals(players: any[], year: number, season: any, dead: number) {
  return players.reduce((total, player) => {
    const value = planValues(player, year, season);
    if (!value.projected) return total;
    total.pf += value.pf;
    if (value.signed) total.locked += value.salary;
    else if (!value.pending) { total.estimated += value.salary; if (!value.entered) total.missing++; }
    return total;
  }, { pf: 0, locked: dead, estimated: 0, missing: 0 });
}

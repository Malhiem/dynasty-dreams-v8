// Date-only arithmetic stays in UTC, including across daylight-saving changes.
const day = 86400000;
const iso = date => date.toISOString().slice(0, 10);
const parse = value => {
  const date = new Date(`${value}T00:00:00Z`);
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(+date) && iso(date) === value ? date : null;
};
export const days = (start, end) => Math.round((+parse(end) - +parse(start)) / day) + 1;
export const addDays = (value, count) => iso(new Date(+parse(value) + count * day));
export function generatePeriods(start, end, interval, type, startDay = 1, merge = 1) {
  if (!parse(start) || !parse(end) || end < start || days(start, end) > 366) throw new Error('Choose valid dates in order, within 366 days.');
  if (!['daily', 'weekly', 'biweekly', 'monthly'].includes(interval)) throw new Error('Choose a scoring interval.');
  const periods = [];
  let current = start;
  while (current <= end) {
    let next;
    if (interval === 'monthly') {
      const date = parse(current);
      const month = date.getUTCMonth() + 1;
      const last = new Date(Date.UTC(date.getUTCFullYear(), month + 1, 0)).getUTCDate();
      next = iso(new Date(Date.UTC(date.getUTCFullYear(), month, Math.min(date.getUTCDate(), last))));
    } else {
      let length = interval === 'daily' ? 1 : interval === 'weekly' ? 7 : 14;
      if (!periods.length && interval !== 'daily') {
        const offset = (Number(startDay) - parse(current).getUTCDay() + 7) % 7;
        if (offset) length = offset;
      }
      next = addDays(current, length);
    }
    periods.push({ id: periods.length + 1, startDate: current, endDate: next > end ? end : addDays(next, -1), type });
    current = next;
  }
  const count = Math.min(Number(merge), periods.length);
  if (count > 1) periods.splice(0, count, { ...periods[0], endDate: periods[count - 1].endDate });
  return periods.map((p, i) => ({ ...p, id: i + 1 }));
}
export function defaults(league) {
  const year = Number(league.current_season_year || String(league.season_start_date || new Date().toISOString()).slice(0, 4));
  const seasonStart = league.season_start_date?.slice(0, 10) || `${year}-10-07`;
  const length = Number(league.matchup_length_days || 7);
  const seasonEnd = league.season_end_date?.slice(0, 10) || addDays(seasonStart, Number(league.regular_season_weeks || 18) * length - 1);
  const playoffStart = addDays(seasonEnd, 1);
  const rounds = Number(league.playoff_rounds || 3);
  const playoffEnd = addDays(playoffStart, rounds * 7 - 1);
  const teams = Math.min(Number(league.max_teams || 12), Number(league.playoff_teams || 8), 2 ** rounds);
  const config = { seasonStart, seasonEnd, scoringInterval: 'weekly', startDay: 1, mergeWeeks: 1,
    matchupsPerPeriod: Math.min(Number(league.opponents_per_matchup_period || 1), Number(league.max_teams || 12) - 1),
    playoffStart, playoffEnd, playoffInterval: 'weekly', regularPeriods: [], playoffPeriods: [],
    brackets: league.playoffs_enabled === false ? [] : [{ id: 'championship', name: 'Championship Bracket', rounds, teams }] };
  try {
    config.regularPeriods = generatePeriods(seasonStart, seasonEnd, config.scoringInterval, 'regular');
    config.playoffPeriods = generatePeriods(playoffStart, playoffEnd, 'weekly', 'playoff', new Date(`${playoffStart}T00:00:00Z`).getUTCDay());
  } catch { /* Invalid legacy dates remain visible for correction. */ }
  return config;
}
export function validate(config, maxTeams) {
  const errors = [], warnings = [];
  let previous;
  for (const [type, start, end, periods] of [
    ['regular', config.seasonStart, config.seasonEnd, config.regularPeriods],
    ['playoff', config.playoffStart, config.playoffEnd, config.playoffPeriods],
  ]) {
    if (!parse(start) || !parse(end) || start > end || days(start, end) > 366) errors.push(`${type}: Choose valid dates in order, within 366 days.`);
    if (!periods.length) warnings.push(`${type}: No scoring periods. Regenerate to create them.`);
    for (const p of periods) {
      if (!parse(p.startDate) || !parse(p.endDate) || p.endDate < p.startDate || p.startDate < start || p.endDate > end) errors.push(`Period ${type} ${p.id} must be within its section dates, with end on or after start.`);
      if (previous) {
        if (p.startDate <= previous.endDate) errors.push(`Period ${type} ${p.id} overlaps an earlier period.`);
        else if (days(previous.endDate, p.startDate) > 2) warnings.push(`Gap before ${type} period ${p.id}.`);
      }
      previous = p;
    }
  }
  if (!Number.isInteger(config.matchupsPerPeriod) || config.matchupsPerPeriod < 1 || config.matchupsPerPeriod >= maxTeams) errors.push(`Opponents must be between 1 and ${maxTeams - 1}.`);
  for (const b of config.brackets) {
    if (!b.name.trim() || b.name.length > 80 || !Number.isInteger(b.teams) || b.teams < 2 || b.teams > maxTeams || !Number.isInteger(b.rounds) || b.rounds < 1 || b.rounds > 7 || 2 ** b.rounds < b.teams || b.rounds > config.playoffPeriods.length) errors.push('Each bracket needs a name, valid team count, and enough rounds and playoff periods to crown a champion.');
  }
  return { errors: [...new Set(errors)], warnings };
}

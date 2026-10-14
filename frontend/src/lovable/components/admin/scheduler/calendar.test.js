import { generatePeriods, validate, defaults, days } from './calendar';

test.each(['daily', 'weekly', 'biweekly', 'monthly'])('includes a one-day season for %s', interval => {
  expect(generatePeriods('2026-10-14', '2026-10-14', interval, 'regular')).toEqual([{ id: 1, startDate: '2026-10-14', endDate: '2026-10-14', type: 'regular' }]);
});
test('includes the final day when it begins its own period', () => {
  expect(generatePeriods('2026-10-12', '2026-10-19', 'weekly', 'regular').map(p => p.endDate)).toEqual(['2026-10-18', '2026-10-19']);
});
test('aligns the first partial week then merges and renumbers', () => {
  const periods = generatePeriods('2026-10-07', '2026-10-25', 'weekly', 'regular', 1, 2);
  expect(periods).toEqual([
    { id: 1, startDate: '2026-10-07', endDate: '2026-10-18', type: 'regular' },
    { id: 2, startDate: '2026-10-19', endDate: '2026-10-25', type: 'regular' },
  ]);
});
test('uses calendar months including leap February', () => {
  const periods = generatePeriods('2028-01-31', '2028-03-31', 'monthly', 'regular');
  expect(periods[0].endDate).toBe('2028-02-28');
  expect(periods[1].startDate).toBe('2028-02-29');
  expect(periods.at(-1).endDate).toBe('2028-03-31');
});
test('DST does not shift or skip dates', () => {
  const periods = generatePeriods('2026-10-26', '2026-11-08', 'weekly', 'regular');
  expect(periods.map(p => [p.startDate, p.endDate, days(p.startDate, p.endDate)])).toEqual([
    ['2026-10-26', '2026-11-01', 7], ['2026-11-02', '2026-11-08', 7],
  ]);
});
test.each([['', '2026-10-14'], ['2026-02-30', '2026-03-01'], ['2026-11-01', '2026-10-01'], ['2026-01-01', '2027-01-02']])('rejects invalid range %s to %s', (start, end) => {
  expect(() => generatePeriods(start, end, 'daily', 'regular')).toThrow();
});
test('default calendar reflects league season and team count', () => {
  const config = defaults({ current_season_year: 2027, max_teams: 4, playoff_teams: 8, playoff_rounds: 3 });
  expect(config.seasonStart).toBe('2027-10-07');
  expect(config.brackets[0].teams).toBe(4);
  expect(validate(config, 4).errors).toEqual([]);
});
test('rejects cross-section overlap, excessive opponents, and impossible bracket', () => {
  const config = defaults({ current_season_year: 2026, max_teams: 8 });
  config.playoffPeriods[0].startDate = config.regularPeriods.at(-1).endDate;
  config.matchupsPerPeriod = 8;
  config.brackets[0].rounds = 1;
  expect(validate(config, 8).errors.length).toBeGreaterThanOrEqual(3);
});
test('empty periods are visible warnings and gaps are distinct from overlaps', () => {
  const config = defaults({ current_season_year: 2026, playoffs_enabled: false });
  config.regularPeriods = []; config.playoffPeriods = [];
  expect(validate(config, 12)).toEqual({ errors: [], warnings: expect.arrayContaining([expect.stringContaining('No scoring periods')]) });
});

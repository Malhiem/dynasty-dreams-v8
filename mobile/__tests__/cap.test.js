const fs = require('fs');
const path = require('path');
jest.mock('react-native', () => ({
  Alert: { alert: jest.fn() }, View: 'View', Text: 'Text', TouchableOpacity: 'TouchableOpacity',
  StyleSheet: { create: (s) => s },
}));
const cap = require('../src/lib/cap');
const TeamCapCard = require('../src/components/TeamCapCard').default;

const compliance = {
  salary_cap_enabled: true, salary_cap: 82500000, salary_used: 70000000,
  salary_retention_slots_total: 3, salary_retention_slots_used: 1, salary_retention_slots_remaining: 2,
  retained_salary_total: 1500000, reasons: [],
};
const text = (n) => JSON.stringify(n, (k, v) => (typeof v === 'function' ? '[fn]' : v));

describe('cap helpers', () => {
  test('formats like the web', () => {
    expect(cap.formatMillions(82500000)).toBe('$82.5M');
    expect(cap.formatMillions(undefined)).toBe('$NaNM'.replace('$NaNM', '—'));
  });
  test('league flag', () => {
    expect(cap.leagueCapEnabled({ salary_cap_enabled: true })).toBe(true);
    expect(cap.leagueCapEnabled({ salary_cap_enabled: false })).toBe(false);
    expect(cap.leagueCapEnabled(undefined)).toBe(false);
  });
  test('capSummary computes remaining and bar', () => {
    const c = cap.capSummary(compliance);
    expect(c.remaining).toBe(12500000);
    expect(c.over).toBe(false);
    expect(Math.round(c.pct)).toBe(85);
    expect(c.slotsRemaining).toBe(2);
    expect(c.retained).toBe(1500000);
  });
  test('capSummary flags over-cap and clamps the bar', () => {
    const c = cap.capSummary({ ...compliance, salary_used: 90000000, reasons: [{ code: 'over_salary_cap', detail: '$90M used vs $82.5M cap' }] });
    expect(c.over).toBe(true);
    expect(c.pct).toBe(100);
    expect(c.overDetail).toMatch(/90M/);
  });
  test('capSummary is null with no cap (no cap, no salaries)', () => {
    expect(cap.capSummary({ ...compliance, salary_cap_enabled: false })).toBeNull();
    expect(cap.capSummary(null)).toBeNull();
  });
  test('salaryByPlayer maps ids and is empty without a cap', () => {
    const detail = { players: [{ id: 'a', contract: { salary: 5000000 } }, { id: 'b', contract: {} }] };
    expect(cap.salaryByPlayer(detail, true)).toEqual({ a: 5000000 });
    expect(cap.salaryByPlayer(detail, false)).toEqual({});
  });
  test('retention options match the web (A/B/C)', () => {
    expect(cap.RETENTION_OPTIONS.map((o) => o.value)).toEqual(['willing_to_retain', 'no_preference', 'seeking_retention']);
    expect(cap.retentionOption('bogus').value).toBe('no_preference');
  });
});

describe('TeamCapCard', () => {
  test('renders nothing for a cap-less league', () => {
    expect(TeamCapCard({ compliance: { salary_cap_enabled: false } })).toBeNull();
  });
  test('shows limit, used, remaining, retention slots and retained salary', () => {
    const t = text(TeamCapCard({ compliance }));
    ['$82.5M', '$70.0M', '$12.5M', 'Cap Remaining', '2 / 3', '$1.5M', 'Retained Salary'].forEach((x) => expect(t).toContain(x));
    expect(t).not.toContain('OVER CAP');
  });
  test('shows the over-cap warning', () => {
    const t = text(TeamCapCard({ compliance: { ...compliance, salary_used: 90000000 } }));
    expect(t).toContain('OVER CAP');
    expect(t).toContain('Over Cap By');
  });
});

describe('screens apply the cap rule', () => {
  const read = (f) => fs.readFileSync(path.join(__dirname, '..', 'src', f), 'utf8');
  test('Roster only loads/shows cap data for cap leagues', () => {
    const src = read('screens/RosterScreen.js');
    expect(src).toMatch(/leagueCapEnabled\(league\)/);
    expect(src).toMatch(/if \(cap\) \{/);
    expect(src).toMatch(/capEnabled \? \(\s*<View>\s*<TeamCapCard/);
    expect(src).toMatch(/capEnabled && salaries\[/);
    expect(src).toMatch(/capEnabled \? \(\s*<TouchableOpacity testID="goto-salary-cap"/);
  });
  test('Trade Block shows salary only when the server sent it', () => {
    expect(read('screens/TradeBlockScreen.js')).toMatch(/item\.aav != null \?/);
  });
});

describe('teamRetention', () => {
  const { teamRetention } = require('../src/lib/cap');
  test('reads slots and retained salary from a team row', () => {
    expect(teamRetention({ retention_slots_total: 3, retention_slots_used: 1, retention_slots_remaining: 2, retained_salary_total: 1500000 }))
      .toMatchObject({ total: 3, used: 1, remaining: 2, label: 'Retention slots 1/3', retainedLabel: '$1.5M retained' });
  });
  test('no retained-salary line when nothing is retained', () => {
    expect(teamRetention({ retention_slots_total: 3, retention_slots_used: 0, retained_salary_total: 0 }).retainedLabel).toBeNull();
  });
  test('derives remaining when the server omits it', () => {
    expect(teamRetention({ retention_slots_total: 2, retention_slots_used: 1 }).remaining).toBe(1);
  });
  test('nothing for an older API that sends no slot data', () => {
    expect(teamRetention({ team_id: 't1' })).toBeNull();
    expect(teamRetention(null)).toBeNull();
  });
  test('the Salary Cap screen renders it for each team', () => {
    const src = require('fs').readFileSync(require('path').join(__dirname, '../src/screens/SalaryCapScreen.js'), 'utf8');
    expect(src).toMatch(/teamRetention\(team\)/);
    expect(src).toMatch(/retention\.label/);
  });
});

const fs = require('fs');
const path = require('path');
jest.mock('react-native', () => ({
  Alert: { alert: jest.fn() }, View: 'View', Text: 'Text', TouchableOpacity: 'TouchableOpacity',
  StyleSheet: { create: (s) => s },
}));
const { floorSummary, isCommissioner } = require('../src/lib/cap');
const CapFloorCard = require('../src/components/CapFloorCard').default;

const watchlist = {
  floor_enabled: true, floor: 60000000, floor_year_plus_1: 62000000, floor_year_plus_2: 62000000, year: 2026,
  summary: { below_count: 1, watchlist_count: 1, above_count: 1 },
  teams: [
    { team_id: 't1', team_name: 'Low', owner_id: 'u1', payroll: 50000000, delta_to_floor: -10000000, status: 'below' },
    { team_id: 't2', team_name: 'Near', owner_id: 'u2', payroll: 62000000, delta_to_floor: 2000000, status: 'watchlist' },
    { team_id: 't3', team_name: 'Fine', owner_id: 'u3', payroll: 80000000, delta_to_floor: 20000000, status: 'above' },
  ],
};
const text = (n) => JSON.stringify(n, (k, v) => (typeof v === 'function' ? '[fn]' : v));

describe('floorSummary', () => {
  test('null with no floor: no cap, no floor', () => {
    expect(floorSummary(null, 'u1')).toBeNull();
    expect(floorSummary({ floor_enabled: false, floor: 0, teams: [] }, 'u1')).toBeNull();
    expect(floorSummary({ floor_enabled: true, floor: 0, teams: [] }, 'u1')).toBeNull();
  });
  test('finds my team, shortfall and at-risk teams', () => {
    const f = floorSummary(watchlist, 'u1');
    expect(f.mine).toMatchObject({ compliant: false, shortfall: 10000000, payroll: 50000000 });
    expect(f.atRisk.map((t) => t.team_id)).toEqual(['t1', 't2']);
    expect(f.yr1).toBe(62000000);
    expect(f.belowCount).toBe(1);
  });
  test('compliant team has no shortfall', () => {
    expect(floorSummary(watchlist, 'u3').mine).toMatchObject({ compliant: true, shortfall: 0 });
  });
  test('user without a team in the league has no "mine"', () => {
    expect(floorSummary(watchlist, 'nobody').mine).toBeNull();
  });
});

test('isCommissioner covers commissioner and co-commissioners', () => {
  expect(isCommissioner({ commissioner_id: 'u1' }, 'u1')).toBe(true);
  expect(isCommissioner({ commissioner_id: 'x', co_commissioners: ['u1'] }, 'u1')).toBe(true);
  expect(isCommissioner({ commissioner_id: 'x', co_commissioners: [] }, 'u1')).toBe(false);
  expect(isCommissioner({ commissioner_id: 'x' }, undefined)).toBe(false);
});

describe('CapFloorCard', () => {
  test('renders nothing without a floor', () => {
    expect(CapFloorCard({ watchlist: { floor_enabled: false, floor: 0 }, userId: 'u1' })).toBeNull();
  });
  test('shows the floor, year preview and my below-floor status', () => {
    const t = text(CapFloorCard({ watchlist, userId: 'u1', showWatchlist: false }));
    ['$60.0M', '$62.0M', 'Below floor', '$10.0M', ' short', 'Year +2'].forEach((x) => expect(t).toContain(x));
    expect(t).not.toContain('cap-floor-watchlist');
  });
  test('shows above-floor for a compliant team', () => {
    expect(text(CapFloorCard({ watchlist, userId: 'u3' }))).toContain('Above floor');
  });
  test('commissioners also see the watchlist of at-risk teams', () => {
    const t = text(CapFloorCard({ watchlist, userId: 'u3', showWatchlist: true }));
    expect(t).toContain('cap-floor-watchlist');
    expect(t).toContain('Low');
    expect(t).toContain('Near');
    expect(t).not.toContain('Fine');
  });
});

test('Salary Cap screen only asks for the floor when the cap is enabled', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'src', 'screens', 'SalaryCapScreen.js'), 'utf8');
  expect(src).toMatch(/if \(o\.data\?\.salary_cap_enabled\) \{[\s\S]*cap-floor-watchlist/);
  expect(src).toMatch(/<CapFloorCard watchlist=\{watchlist\}/);
});

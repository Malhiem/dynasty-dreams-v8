const fs = require('fs');
const path = require('path');
const { pickActiveLeague } = require('../src/lib/leagues');

const L = [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }];

describe('pickActiveLeague', () => {
  test('keeps the remembered league while the user is still in it', () => {
    expect(pickActiveLeague(L, 'b').id).toBe('b');
  });
  test('falls back to the first league when the remembered one is gone', () => {
    expect(pickActiveLeague(L, 'zzz').id).toBe('a');
    expect(pickActiveLeague(L, null).id).toBe('a');
  });
  test('returns null with no leagues', () => {
    expect(pickActiveLeague([], 'a')).toBeNull();
    expect(pickActiveLeague(undefined, 'a')).toBeNull();
  });
});

describe('league screens follow the active league', () => {
  const dir = path.join(__dirname, '..', 'src', 'screens');
  const read = (f) => fs.readFileSync(path.join(dir, f), 'utf8');
  test.each(['Roster', 'Waivers', 'SalaryCap', 'ActivityFeed', 'Standings', 'Chat', 'Matchup'])('%sScreen uses useLeague()', (n) => {
    expect(read(`${n}Screen.js`)).toMatch(/useLeague\(\)/);
  });
  test.each(['Roster', 'Waivers', 'SalaryCap', 'ActivityFeed', 'Standings', 'Chat'])('%sScreen no longer hard-codes the first league', (n) => {
    const src = read(`${n}Screen.js`);
    expect(src).not.toMatch(/leagues\[0\]/);
    expect(src).not.toMatch(/data\[0\]\.id/);
  });
  test.each(['Roster', 'Waivers', 'ActivityFeed', 'Standings', 'Chat'])('%sScreen offers the league switcher', (n) => {
    expect(read(`${n}Screen.js`)).toMatch(/<LeagueSwitcher \/>/);
  });
  test.each(['Roster', 'Waivers', 'SalaryCap', 'ActivityFeed'])('%sScreen reloads when the league changes', (n) => {
    expect(read(`${n}Screen.js`)).toMatch(/\}, \[leagueId\]\)/);
  });
  test('Chat shows load failures and keeps the poll quiet', () => {
    const src = read('ChatScreen.js');
    expect(src).toMatch(/<LoadError message=\{loadError\}/);
    expect(src).toMatch(/loadMessages\(true\)/);
  });
  test('the provider wraps the app', () => {
    expect(fs.readFileSync(path.join(__dirname, '..', 'App.js'), 'utf8')).toMatch(/<LeagueProvider>/);
  });
});

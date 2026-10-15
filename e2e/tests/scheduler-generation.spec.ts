import { test, expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { actors, dispose, type Actors } from '../support/access-history';
import { fixture, database, result } from '../support/h2h';

let a: Actors;
test.beforeAll(async () => { a = await actors(); });
test.afterAll(async () => { if (a) await dispose(a); });

for (const count of [7, 8]) test(`${count}-team live schedule: unique weekly opponents, persistence, repeat generation`, async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points', false, count);
  const weeks = count === 7 ? 7 : count - 1;
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: {
    regular_season_weeks: weeks, season_end_date: '2026-12-30', opponents_per_matchup_period: 2,
  } }));
  // LeagueCreate initializes matchups_per_week=1. Set the explicit canonical
  // field in the isolated fixture to exercise the multiple-opponent generator.
  await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(l.id) }, { $set: { matchups_per_week: 2 } }));
  const generate = () => a.commissioner.api.post('/api/matchups/generate-schedule', { data: { league_id: l.id } });
  const generated = await result(await generate());
  expect(generated.weeks).toBe(weeks);
  expect(generated.opponents_per_period).toBe(2);
  const rows = await result(await a.commissioner.api.get(`/api/matchups/${l.id}`));
  const current = await result(await a.commissioner.api.get(`/api/matchups/${l.id}/current-week`));
  expect(current.week).toBe(1);
  const week = await result(await a.commissioner.api.get(`/api/matchups/${l.id}/results?week=1`));
  expect(week.length).toBe(current.matchups.length);
  const snapshots = await database(db => db.collection('matchups').find({ league_id: l.id, week: 1 }).toArray());
  expect(snapshots.every((m: any) => m.xp_competition?.policy === 'owner-xp-v1')).toBeTruthy();
  const regular = rows.filter((m: any) => !m.is_playoff && !m.is_consolation);
  expect(regular.length).toBe(weeks * count);
  const totals = new Map<string, number>();
  for (let week = 1; week <= weeks; week++) {
    const games = regular.filter((m: any) => m.week === week), seen = new Set<string>(), appearances = new Map<string, number>();
    for (const m of games) {
      expect(m.home_team_id).not.toBe(m.away_team_id);
      expect(l.teams.map(t => t.id)).toContain(m.home_team_id);
      expect(l.teams.map(t => t.id)).toContain(m.away_team_id);
      const pair = [m.home_team_id, m.away_team_id].sort().join(':');
      expect(seen.has(pair)).toBe(false); seen.add(pair);
      for (const id of [m.home_team_id, m.away_team_id]) {
        appearances.set(id, (appearances.get(id) || 0) + 1); totals.set(id, (totals.get(id) || 0) + 1);
      }
    }
    for (const t of l.teams) expect(appearances.get(t.id) || 0).toBeLessThanOrEqual(2);
    expect([...appearances.values()]).toEqual(Array(count).fill(2));
  }
  expect(new Set(totals.values()).size).toBe(1);
  await result(await generate());
  expect((await result(await a.commissioner.api.get(`/api/matchups/${l.id}`))).length).toBe(rows.length);
  const saved = await database(db => db.collection('matchups').find({ league_id: l.id }).toArray());
  expect(saved.length).toBe(rows.length);
});

test('failed live generation leaves existing matchups intact and is commissioner-only', async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  const data = { league_id: l.id, num_weeks: 4 };
  await result(await a.commissioner.api.post('/api/matchups/generate-schedule', { data }));
  const before = await database(db => db.collection('matchups').find({ league_id: l.id }).toArray());
  for (const [actor, status] of [[a.anonymous, 401], [a.outsider, 403], [a.manager, 403]] as const) {
    expect((await actor.api.post('/api/matchups/generate-schedule', { data })).status()).toBe(status);
  }
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { season_end_date: '2026-10-08' } }));
  expect((await a.commissioner.api.post('/api/matchups/generate-schedule', { data })).status()).toBe(400);
  const after = await database(db => db.collection('matchups').find({ league_id: l.id }).toArray());
  expect(after).toEqual(before);
});

test('empty league slots produce schedulable placeholders in its own league', async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points', false, 4);
  await database(db => db.collection('teams').deleteMany({ league_id: l.id }));
  const generated = await result(await a.commissioner.api.post('/api/matchups/generate-schedule', { data: { league_id: l.id, num_weeks: 3 } }));
  expect(generated.placeholder_team_slots).toBe(4);
  const rows = await result(await a.commissioner.api.get(`/api/matchups/${l.id}`));
  expect(rows.length).toBe(6);
  expect(rows.every((m: any) => m.home_team_id.startsWith('open_slot_') && m.away_team_id.startsWith('open_slot_'))).toBeTruthy();
});

test('division/conference rule counts and zero cross-conference games persist and generate exactly', async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { regular_season_weeks: 4, season_end_date: '2027-03-31' } }));
  await database(async db => {
    for (const [i, team] of l.teams.entries()) await db.collection('teams').updateOne({ _id: new ObjectId(team.id) }, { $set: { division: `D${Math.floor(i / 2)}`, conference: `C${Math.floor(i / 4)}` } });
  });
  await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(l.id) }, { $set: { matchups_per_week: 1 } }));
  const rules = { intra_division_games: 2, intra_conference_games: 1, inter_conference_games: 0 };
  const url = `/api/leagues/${l.id}/schedule-config`;
  await result(await a.commissioner.api.put(url, { data: rules }));
  expect(await result(await a.commissioner.api.get(url))).toMatchObject({ ...rules, configured: true });
  expect((await a.commissioner.api.put(url, { data: { ...rules, intra_division_games: 21 } })).status()).toBe(400);
  expect(await result(await a.commissioner.api.get(url))).toMatchObject(rules);
  const generated = await result(await a.commissioner.api.post('/api/matchups/generate-schedule', { data: { league_id: l.id } }));
  expect(generated.mode).toBe('combined');
  const games = await result(await a.commissioner.api.get(`/api/matchups/${l.id}`));
  expect(games.length).toBe(16);
  for (let i = 0; i < l.teams.length; i++) for (let j = i + 1; j < l.teams.length; j++) {
    const matching = games.filter((g: any) => [g.home_team_id, g.away_team_id].includes(l.teams[i].id) && [g.home_team_id, g.away_team_id].includes(l.teams[j].id));
    const expected = Math.floor(i / 2) === Math.floor(j / 2) ? 2 : Math.floor(i / 4) === Math.floor(j / 4) ? 1 : 0;
    expect(matching.length).toBe(expected);
  }
});

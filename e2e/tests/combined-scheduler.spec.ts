import { test, expect, type Page } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { actors, dispose, type Actors } from '../support/access-history';
import { fixture, database, result } from '../support/h2h';

let a: Actors;
test.setTimeout(90000);
test.beforeAll(async () => { a = await actors(); });
test.afterAll(async () => { if (a) await dispose(a); });
const settings = (weeks = 4) => ({ weeks, games_per_week: 2, seed: 1, rules: [] as any[] });
async function grouped(count = 8) {
  const l = await fixture(a.commissioner.api, 'h2h-points', false, count);
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { season_end_date: '2027-03-31' } }));
  await database(async db => {
    for (const [i, t] of l.teams.entries()) await db.collection('teams').updateOne({ _id: new ObjectId(t.id) }, { $set: { division: `D${Math.floor(i / (count / 4))}`, conference: `C${Math.floor(i / (count / 2))}` } });
  });
  return l;
}
async function open(page: Page, id: string) {
  await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
  await page.goto('/dashboard');
  await page.evaluate(id => localStorage.setItem('dd_active_league_id', id), id);
  await page.goto('/commissioner/settings?tab=admin');
  await page.getByRole('tab', { name: 'Schedules', exact: true }).click();
  await page.getByRole('tab', { name: 'Opponent Schedule', exact: true }).click();
  await expect(page.getByTestId('combined-scheduler')).toBeVisible();
}

test('24 teams get two distinct weekly opponents and exact division/conference counts, preserving completed games', async () => {
  const l = await grouped(24), base = `/api/leagues/${l.id}/schedule`;
  const locked = { _id: new ObjectId(), league_id: l.id, week: 1, home_team_id: l.teams[0].id, away_team_id: l.teams[1].id, status: 'completed', home_score: 40, away_score: 20, winner: l.teams[0].id };
  await database(db => db.collection('matchups').insertOne(locked));
  const input = settings(20); input.rules = [
    { group: 'division', scope: 'per_opponent', comparison: 'exact', value: 2 },
    { group: 'conference_other', scope: 'per_opponent', comparison: 'exact', value: 1 },
    { group: 'outside_conference', scope: 'per_opponent', comparison: 'exact', value: 2 },
  ];
  expect((await result(await a.commissioner.api.post(`${base}/check`, { data: input }))).status).toBe('ready');
  const plan = await result(await a.commissioner.api.post(`${base}/preview`, { data: input }));
  expect(plan.status).toBe('feasible'); expect(plan.games.length).toBe(480);
  expect(await database(db => db.collection('matchups').countDocuments({ league_id: l.id }))).toBe(1);
  for (const team of plan.validation.teams) expect(team).toMatchObject({ games: 40, division: 10, conference_other: 6, conference: 16, outside_conference: 24 });
  const applied = await result(await a.commissioner.api.post(`${base}/apply`, { data: { preview_id: plan.preview_id } }));
  expect(applied).toMatchObject({ status: 'applied', games: 480, preserved_games: 1, version: 1 });
  const rows = await result(await a.commissioner.api.get(`/api/matchups/${l.id}`));
  expect(rows.length).toBe(480);
  for (let week = 1; week <= 20; week++) {
    const games = rows.filter((g: any) => g.week === week), pairs = new Set<string>(), counts = new Map<string, number>();
    expect(games.length).toBe(24);
    for (const g of games) {
      const pair = [g.home_team_id, g.away_team_id].sort().join(':'); expect(pairs.has(pair)).toBe(false); pairs.add(pair);
      for (const id of [g.home_team_id, g.away_team_id]) counts.set(id, (counts.get(id) || 0) + 1);
    }
    expect([...counts.values()]).toEqual(Array(24).fill(2));
  }
  const preserved = await database(db => db.collection('matchups').findOne({ _id: locked._id }));
  expect(preserved).toMatchObject(locked);
  expect((await a.commissioner.api.post(`${base}/apply`, { data: { preview_id: plan.preview_id } })).status()).toBe(409);
});

test('impossible constraints, stale previews and concurrent apply never destroy the existing schedule', async () => {
  const l = await grouped(), base = `/api/leagues/${l.id}/schedule`;
  const input = settings(); input.rules = [{ group: 'all', scope: 'per_opponent', comparison: 'exact', value: 4 }];
  const impossible = await result(await a.commissioner.api.post(`${base}/preview`, { data: input }));
  expect(impossible.status).toBe('infeasible'); expect(impossible.errors.length).toBeGreaterThan(0);
  const plan = await result(await a.commissioner.api.post(`${base}/preview`, { data: settings() }));
  await database(db => db.collection('teams').updateOne({ _id: new ObjectId(l.teams[0].id) }, { $set: { division: 'Changed' } }));
  expect((await a.commissioner.api.post(`${base}/apply`, { data: { preview_id: plan.preview_id } })).status()).toBe(409);
  expect(await database(db => db.collection('matchups').countDocuments({ league_id: l.id }))).toBe(0);
  const fresh = await result(await a.commissioner.api.post(`${base}/preview`, { data: settings() }));
  const responses = await Promise.all([1, 2].map(() => a.commissioner.api.post(`${base}/apply`, { data: { preview_id: fresh.preview_id } })));
  expect(responses.map(r => r.status()).sort()).toEqual([200, 409]);
  expect(await database(db => db.collection('matchups').countDocuments({ league_id: l.id }))).toBe(32);
  expect(await database(db => db.collection('schedule_versions').countDocuments({ league_id: l.id }))).toBe(1);
});

test('all combined scheduler endpoints enforce authentication and league administrative permissions', async () => {
  const l = await grouped(), base = `/api/leagues/${l.id}/schedule`;
  await database(db => db.collection('teams').updateOne({ _id: new ObjectId(l.teams[0].id) }, { $set: { owner_id: a.manager.id } }));
  for (const [actor, status] of [[a.anonymous, 401], [a.expired, 401], [a.outsider, 403], [a.manager, 403]] as const) {
    expect((await actor.api.get(`${base}/rules`)).status()).toBe(status);
    for (const action of ['check', 'preview', 'apply']) expect((await actor.api.post(`${base}/${action}`, { data: action === 'apply' ? { preview_id: '000000000000000000000000' } : settings() })).status()).toBe(status);
  }
  expect((await a.anonymous.api.get('/api/leagues/000000000000000000000000/schedule/rules')).status()).toBe(401);
  const { createHmac } = await import('node:crypto'), enc = (x: any) => Buffer.from(JSON.stringify(x)).toString('base64url');
  const input = `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc({ sub: a.commissioner.id, type: 'impersonation', mode: 'read_only', exp: Date.now() / 1000 + 60 })}`;
  const token = `${input}.${createHmac('sha256', 'e2e-only-jwt-secret').update(input).digest('base64url')}`;
  expect((await a.commissioner.api.post(`${base}/preview`, { data: settings(), headers: { Authorization: `Bearer ${token}` } })).status()).toBe(403);
  await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(l.id) }, { $set: { admin_ids: [a.manager.id] } }));
  expect((await result(await a.manager.api.get(`${base}/rules`))).can_apply).toBe(true);
  expect((await a.commissioner.api.post(`${base}/preview`, { data: { ...settings(), games_per_week: 0 } })).status()).toBe(422);
});

for (const mobile of [false, true]) test(`administrator can configure, review, apply and reload ${mobile ? 'mobile' : 'desktop'}`, async ({ page }, info) => {
  const l = await grouped();
  if (mobile) await page.setViewportSize({ width: 390, height: 844 });
  await open(page, l.id);
  const ui = page.getByTestId('combined-scheduler');
  await ui.getByLabel('Matchups per team per period', { exact: true }).fill('2');
  await ui.getByRole('button', { name: 'Add opponent rule', exact: true }).click();
  await ui.getByLabel('Rule 1 opponent group').selectOption('division');
  await ui.getByLabel('Rule 1 requirement').selectOption('minimum');
  await ui.getByLabel('Rule 1 games', { exact: true }).fill('1');
  await ui.getByRole('button', { name: 'Add opponent rule', exact: true }).click();
  await ui.getByLabel('Rule 2 opponent group').selectOption('conference');
  await ui.getByLabel('Rule 2 games', { exact: true }).fill('4');
  await ui.getByRole('button', { name: 'Check feasibility', exact: true }).click();
  await expect(ui.getByRole('status')).toContainText('Basic checks passed');
  await ui.getByRole('button', { name: 'Generate preview', exact: true }).click();
  await expect(ui.getByTestId('opponent-preview')).toBeVisible({ timeout: 30000 });
  await expect(ui.getByRole('heading', { name: /Validated schedule preview/ })).toContainText('32 matchups');
  await expect(ui.getByRole('table', { name: 'Requested versus achieved by team' })).toContainText('minimum 4 total');
  await ui.getByLabel('Matchups per team per period', { exact: true }).fill('1');
  await expect(ui.getByTestId('opponent-preview')).toHaveCount(0);
  await ui.getByLabel('Matchups per team per period', { exact: true }).fill('2');
  await ui.getByRole('button', { name: 'Generate preview', exact: true }).click();
  await expect(ui.getByTestId('opponent-preview')).toBeVisible({ timeout: 30000 });
  await ui.getByRole('button', { name: 'Apply validated schedule', exact: true }).click();
  await expect(ui.getByRole('status')).toContainText('Schedule version 1 applied');
  await page.reload();
  await page.getByRole('tab', { name: 'Schedules', exact: true }).click(); await page.getByRole('tab', { name: 'Opponent Schedule', exact: true }).click();
  await expect(ui.getByLabel('Matchups per team per period', { exact: true })).toHaveValue('2');
  await expect(ui).toContainText('Version 1'); await expect(ui.getByLabel('Rule 2 games', { exact: true })).toHaveValue('4');
  if (mobile) expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await info.attach('combined-scheduler', { body: await page.screenshot(), contentType: 'image/png' });
});

import { test, expect, type Page } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { actors, dispose, type Actors } from '../support/access-history';
import { fixture, database, result } from '../support/h2h';

let a: Actors;
test.beforeAll(async () => { a = await actors(); });
test.afterAll(async () => { if (a) await dispose(a); });
const calendar = () => ({
  seasonStart: '2026-10-07', seasonEnd: '2026-10-20', scoringInterval: 'weekly', startDay: 1, mergeWeeks: 1,
  matchupsPerPeriod: 1, playoffStart: '2026-10-21', playoffEnd: '2026-10-27', playoffInterval: 'weekly',
  regularPeriods: [{ id: 1, type: 'regular', startDate: '2026-10-07', endDate: '2026-10-13' }, { id: 2, type: 'regular', startDate: '2026-10-14', endDate: '2026-10-20' }],
  playoffPeriods: [{ id: 1, type: 'playoff', startDate: '2026-10-21', endDate: '2026-10-27' }],
  brackets: [{ id: 'championship', name: 'Champion', teams: 2, rounds: 1 }],
});
async function open(page: Page, leagueId: string) {
  await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
  await page.goto('/dashboard');
  await page.evaluate(id => localStorage.setItem('dd_active_league_id', id), leagueId);
  await page.goto('/commissioner/settings?tab=admin');
  await page.getByRole('tab', { name: 'Schedules', exact: true }).click();
  await expect(page.getByTestId('scheduler')).toBeVisible();
}

test('season calendar persists without altering live matchups or other league seasons', async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  const other = await fixture(a.commissioner.api, 'h2h-points');
  const url = `/api/leagues/${l.id}/scheduler/2026`;
  const before = await database(db => db.collection('matchups').find({ league_id: l.id }).toArray());
  expect((await result(await a.commissioner.api.get(url))).calendar).toBeNull();
  await result(await a.commissioner.api.put(url, { data: calendar() }));
  expect((await result(await a.commissioner.api.get(url))).calendar).toEqual(calendar());
  expect((await result(await a.commissioner.api.get(`/api/leagues/${other.id}/scheduler/2026`))).calendar).toBeNull();
  const after = await database(db => db.collection('matchups').find({ league_id: l.id }).toArray());
  expect(after).toEqual(before);
  await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(l.id) }, { $set: { current_season_year: 2027 } }));
  expect((await a.commissioner.api.put(url, { data: calendar() })).status()).toBe(409);
  expect((await a.commissioner.api.get(url)).status()).toBe(409);
  expect((await result(await a.commissioner.api.get(`/api/leagues/${l.id}/scheduler/2027`))).calendar).toBeNull();
  const saved = await database(db => db.collection('leagues').findOne({ _id: new ObjectId(l.id) }));
  expect(saved?.scheduler_calendars['2026']).toEqual(calendar());
});

test('authentication, membership, read-only member, co-commissioner and league admin permissions', async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  const url = `/api/leagues/${l.id}/scheduler/2026`;
  for (const actor of [a.anonymous, a.expired]) {
    expect((await actor.api.get(url)).status()).toBe(401);
    expect((await actor.api.put(url, { data: calendar() })).status()).toBe(401);
    expect((await actor.api.get('/api/leagues/000000000000000000000000/scheduler/2026')).status()).toBe(401);
  }
  const { createHmac } = await import('node:crypto');
  const enc = (x: any) => Buffer.from(JSON.stringify(x)).toString('base64url');
  const input = `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc({ sub: a.commissioner.id, type: 'impersonation', mode: 'read_only', exp: Date.now() / 1000 + 60 })}`;
  const token = `${input}.${createHmac('sha256', 'e2e-only-jwt-secret').update(input).digest('base64url')}`;
  const readOnly = await a.commissioner.api.put(url, { data: calendar(), headers: { Authorization: `Bearer ${token}` } });
  expect(readOnly.status()).toBe(403);
  expect(await readOnly.text()).toContain('read-only');
  expect((await a.outsider.api.get(url)).status()).toBe(403);
  expect((await a.outsider.api.put(url, { data: calendar() })).status()).toBe(403);
  await database(db => db.collection('teams').updateOne({ _id: new ObjectId(l.teams[0].id) }, { $set: { owner_id: a.manager.id } }));
  expect((await result(await a.manager.api.get(url))).can_edit).toBe(false);
  expect((await a.manager.api.put(url, { data: calendar() })).status()).toBe(403);
  for (const field of ['co_commissioners', 'admin_ids']) {
    await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(l.id) }, { $set: { [field]: [a.manager.id] } }));
    await result(await a.manager.api.put(url, { data: calendar() }));
    await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(l.id) }, { $unset: { [field]: '' } }));
  }
  expect((await a.commissioner.api.get('/api/leagues/invalid/scheduler/2026')).status()).toBe(400);
  expect((await a.commissioner.api.get('/api/leagues/000000000000000000000000/scheduler/2026')).status()).toBe(404);
});

test('invalid calendars fail without replacing saved data', async () => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  const url = `/api/leagues/${l.id}/scheduler/2026`;
  await result(await a.commissioner.api.put(url, { data: calendar() }));
  const cases: [any, number][] = [];
  let c: any = calendar(); c.regularPeriods[0].endDate = '2026-10-06'; cases.push([c, 422]);
  c = calendar(); c.regularPeriods[1].startDate = '2026-10-13'; cases.push([c, 422]);
  c = calendar(); c.regularPeriods[0].startDate = '2026-10-01'; cases.push([c, 422]);
  c = calendar(); c.matchupsPerPeriod = 8; cases.push([c, 400]);
  c = calendar(); c.brackets[0].teams = 9; c.brackets[0].rounds = 4; cases.push([c, 400]);
  c = calendar(); c.brackets[0].teams = 4; c.brackets[0].rounds = 1; cases.push([c, 422]);
  c = calendar(); c.brackets[0].rounds = 2; cases.push([c, 400]);
  c = calendar(); c.seasonStart = '2026-02-30'; cases.push([c, 422]);
  c = calendar(); c.extra = 'not allowed'; cases.push([c, 422]);
  for (const [data, status] of cases) expect((await a.commissioner.api.put(url, { data })).status()).toBe(status);
  expect((await result(await a.commissioner.api.get(url))).calendar).toEqual(calendar());
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { scoring_format: 'rotisserie' } }));
  expect((await a.commissioner.api.put(url, { data: calendar() })).status()).toBe(400);
});

for (const mobile of [false, true]) test(`calendar generation, editing, keyboard, bracket reset and reload ${mobile ? 'mobile' : 'desktop'}`, async ({ page }, info) => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  const url = `/api/leagues/${l.id}/scheduler/2026`;
  await result(await a.commissioner.api.put(url, { data: calendar() }));
  if (mobile) await page.setViewportSize({ width: 390, height: 844 });
  await open(page, l.id);
  await expect(page.getByLabel('Beginning Scoring Period')).toHaveValue('2026-10-07');
  await page.getByRole('button', { name: 'Edit regular period 1', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByLabel('Start Date', { exact: true })).toBeVisible();
  await page.getByLabel('End Date', { exact: true }).fill('2026-10-06');
  await expect(page.getByRole('button', { name: 'Save Changes', exact: true })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Edit regular period 1', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Edit regular period 2', exact: true }).click();
  await page.getByLabel('Start Date', { exact: true }).fill('2026-10-13');
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('overlaps');
  await page.getByLabel('Start Date', { exact: true }).fill('2026-10-15');
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByRole('status').filter({ hasText: 'Gap before' })).toBeVisible();
  const saved = page.waitForResponse(r => r.url().endsWith(url) && r.request().method() === 'PUT' && r.ok());
  await page.getByRole('button', { name: 'Save Schedule', exact: true }).click(); await saved;
  await page.reload(); await page.getByRole('tab', { name: 'Schedules', exact: true }).click();
  await expect(page.getByTestId('scheduler-periods')).toContainText('2026-10-15');
  await page.getByLabel('Opponents per scoring period (1–7)').fill('8');
  await expect(page.getByRole('button', { name: 'Save Schedule', exact: true })).toBeDisabled();
  await page.getByLabel('Opponents per scoring period (1–7)').fill('1');
  await page.getByLabel('Beginning Scoring Period').fill('2026-10-20');
  await page.getByLabel('Ending Scoring Period').fill('2026-10-20');
  await page.getByRole('button', { name: 'Regenerate Regular Periods', exact: true }).click();
  await expect(page.getByTestId('scheduler-periods').locator('tbody tr')).toHaveCount(1);
  await expect(page.getByTestId('scheduler-periods')).toContainText('2026-10-20');
  await page.getByRole('tab', { name: 'Playoffs', exact: true }).click();
  await page.getByRole('button', { name: 'Remove bracket 1', exact: true }).click();
  await expect(page.getByText('No brackets configured. Add one to get started.')).toBeVisible();
  await page.getByRole('button', { name: 'Add Bracket', exact: true }).click();
  await page.getByLabel('Bracket 1 Name').fill('Consolation');
  await page.getByRole('button', { name: 'Save Schedule', exact: true }).click();
  await expect.poll(async () => (await result(await a.commissioner.api.get(url))).calendar.brackets[0].name).toBe('Consolation');
  await page.getByRole('button', { name: 'Reset to Defaults', exact: true }).click();
  await expect(page.getByText('No brackets configured. Add one to get started.')).toBeVisible();
  await page.getByRole('tab', { name: 'Full Schedule Projection', exact: true }).click();
  await expect(page.getByTestId('scheduler-periods')).toContainText('regular');
  await expect(page.getByTestId('scheduler-periods')).toContainText('playoff');
  if (mobile) expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await info.attach('calendar-view', { body: await page.screenshot(), contentType: 'image/png' });
});

test('loading and load failure retry, empty calendar and failed save preserve the draft', async ({ page }) => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  const url = `/api/leagues/${l.id}/scheduler/2026`;
  const c = calendar(); c.regularPeriods = []; c.playoffPeriods = []; c.brackets = [];
  await result(await a.commissioner.api.put(url, { data: c }));
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**${url}`, async route => { await gate; await route.fulfill({ status: 503, body: '{}' }); });
  await page.context().addCookies((await a.commissioner.api.storageState()).cookies);
  await page.addInitScript(id => localStorage.setItem('dd_active_league_id', id), l.id);
  await page.goto('/commissioner/settings?tab=admin');
  await page.getByRole('tab', { name: 'Schedules', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Loading schedule' })).toBeVisible();
  release();
  await expect(page.getByRole('alert')).toContainText('Unable to load');
  await page.unroute(`**${url}`);
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByText('No scoring periods. Regenerate periods to get started.')).toBeVisible();
  await page.getByRole('button', { name: 'Regenerate Regular Periods', exact: true }).click();
  await page.getByLabel('Opponents per scoring period (1–7)').fill('2');
  await page.route(`**${url}`, route => route.request().method() === 'PUT' ? route.fulfill({ status: 503, body: '{}' }) : route.continue());
  await page.getByRole('button', { name: 'Save Schedule', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Unable to save');
  await expect(page.getByLabel('Opponents per scoring period (1–7)')).toHaveValue('2');
  await expect(page.getByRole('button', { name: 'Save Schedule', exact: true })).toBeEnabled();
  expect((await result(await a.commissioner.api.get(url))).calendar.matchupsPerPeriod).toBe(1);
  await page.unroute(`**${url}`);
  await page.getByRole('button', { name: 'Save Schedule', exact: true }).click();
  await expect.poll(async () => (await result(await a.commissioner.api.get(url))).calendar.matchupsPerPeriod).toBe(2);
});

test('regular members cannot mount administrative scheduler controls', async ({ page }) => {
  const l = await fixture(a.commissioner.api, 'h2h-points');
  await database(db => db.collection('teams').updateOne({ _id: new ObjectId(l.teams[0].id) }, { $set: { owner_id: a.manager.id } }));
  await page.context().addCookies((await a.manager.api.storageState()).cookies);
  await page.addInitScript(id => localStorage.setItem('dd_active_league_id', id), l.id);
  await page.goto('/commissioner/settings?tab=admin');
  await expect(page.getByRole('alert')).toContainText('Only league administrators');
  await expect(page.getByTestId('scheduler')).toHaveCount(0);
});

test('switching league and active season never reuses another calendar draft', async ({ page }) => {
  const first = await fixture(a.commissioner.api, 'h2h-points');
  const second = await fixture(a.commissioner.api, 'h2h-points');
  const next = calendar(); next.matchupsPerPeriod = 2;
  await result(await a.commissioner.api.put(`/api/leagues/${first.id}/scheduler/2026`, { data: calendar() }));
  await result(await a.commissioner.api.put(`/api/leagues/${second.id}/scheduler/2026`, { data: next }));
  await open(page, first.id);
  await page.getByLabel('Opponents per scoring period (1–7)').fill('3');
  await page.getByTestId('current-league-dropdown-trigger').click();
  await page.getByTestId(`current-league-option-${second.id}`).click();
  await expect(page).toHaveURL(`/leagues/${second.id}`);
  await page.getByRole('link', { name: 'League Administration', exact: true }).click();
  await page.getByRole('tab', { name: 'League Administration', exact: true }).click();
  await page.getByRole('tab', { name: 'Schedules', exact: true }).click();
  await expect(page.getByLabel('Opponents per scoring period (1–7)')).toHaveValue('2');
  expect((await result(await a.commissioner.api.get(`/api/leagues/${first.id}/scheduler/2026`))).calendar.matchupsPerPeriod).toBe(1);
  await database(db => db.collection('leagues').updateOne({ _id: new ObjectId(second.id) }, { $set: { current_season_year: 2027 } }));
  await page.reload();
  await page.getByRole('tab', { name: 'Schedules', exact: true }).click();
  await expect(page.getByTestId('scheduler').getByRole('heading', { level: 2 })).toContainText('2027 season');
  await expect(page.getByLabel('Opponents per scoring period (1–7)')).toHaveValue('1');
});

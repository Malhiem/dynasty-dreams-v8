import { test, expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { actors, dispose, league, type Actors } from '../support/access-history';
import { database, result, type League } from '../support/h2h';
import { MobileExperiencePage } from '../pages/mobile-experience/mobile-experience.page';
let a: Actors;
let l: League;
test.beforeAll(async () => { a = await actors(); l = await league(a); });
test.afterAll(async () => { if (a) await dispose(a); });
test.beforeEach(async ({ context }) => {
  await context.addCookies((await a.manager.api.storageState()).cookies);
  await context.addInitScript(id => localStorage.setItem('dd_active_league_id', id), l.id);
});

test('NAV-01 DASH-01 mobile menu opens chat and browser history restores dashboard', async ({ page }, info) => {
  const ui = new MobileExperiencePage(page);
  await ui.goto('/dashboard'); await expect(ui.dashboard).toBeVisible();
  await ui.dismissInstallIfPresent();
  await expect(page.getByRole('heading', { name: /WELCOME BACK/ })).toBeVisible();
  await ui.viaMenu('Chat'); await expect(page).toHaveURL(/\/chat$/); await expect(ui.chat).toBeVisible();
  await expect(ui.drawer).toBeHidden();
  await page.goBack(); await expect(page).toHaveURL(/\/dashboard$/); await expect(ui.dashboard).toBeVisible();
  await page.reload(); await expect(ui.dashboard).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('dd_active_league_id'))).toBe(l.id);
  await info.attach('dashboard', { body: await page.screenshot(), contentType: 'image/png' });
});

test('CHAT-01 sends Unicode and literal markup once, with persistent history', async ({ page }, info) => {
  const ui = new MobileExperiencePage(page); await ui.goto('/chat'); await expect(ui.input).toBeEnabled();
  await ui.dismissInstallIfPresent();
  const text = `Mobile QA ${crypto.randomUUID()} café 🏒 <b>literal</b>`;
  await ui.input.fill(text);
  const sent = page.waitForResponse(r => /\/api\/chat\/channels\/[^/]+\/messages$/.test(new URL(r.url()).pathname) && r.request().method() === 'POST');
  await ui.send.click(); const response = await sent; expect(response.ok(), await response.text()).toBeTruthy();
  const rows = await database(db => db.collection('chat_messages').find({ league_id: l.id, content: text }).toArray());
  expect(rows).toHaveLength(1); const id = String(rows[0]._id);
  await expect(ui.message(id)).toContainText(text); await expect(ui.message(id).getByText('literal', { exact: true })).toHaveCount(0);
  await expect(ui.input).toHaveValue('');
  await page.reload(); await expect(ui.message(id)).toContainText(text);
  await info.attach('chat', { body: await page.screenshot(), contentType: 'image/png' });
});

test('CHAT-01 empty and over-limit messages cannot create entries', async ({ page }) => {
  const ui = new MobileExperiencePage(page); await ui.goto('/chat'); await expect(ui.input).toBeEnabled();
  await ui.input.fill('   '); await expect(ui.send).toBeDisabled();
  const channels = await result(await a.manager.api.get(`/api/chat/channels?league_id=${l.id}`));
  const channel = channels.channels.find((c: any) => c.kind === 'channel'); expect(channel).toBeTruthy();
  const count = await database(db => db.collection('chat_messages').countDocuments({ channel_id: channel._id }));
  expect((await a.manager.api.post(`/api/chat/channels/${channel._id}/messages`, { data: { content: 'x'.repeat(2001) } })).status()).toBe(400);
  expect(await database(db => db.collection('chat_messages').countDocuments({ channel_id: channel._id }))).toBe(count);
});

test('CHAT-02 outsiders and revoked members cannot read or send channel messages', async () => {
  const channels = await result(await a.manager.api.get(`/api/chat/channels?league_id=${l.id}`));
  const channel = channels.channels.find((c: any) => c.kind === 'channel');
  const base = `/api/chat/channels/${channel._id}/messages`;
  for (const actor of [a.anonymous, a.outsider]) {
    const status = actor === a.anonymous ? 401 : 403;
    expect((await actor.api.get(base)).status()).toBe(status);
    expect((await actor.api.post(base, { data: { content: 'Denied fixture message' } })).status()).toBe(status);
  }
  await database(db => db.collection('teams').updateOne({ _id: new ObjectId(l.teams[1].id) }, { $set: { owner_id: a.outsider.id } }));
  expect((await a.manager2.api.get(base)).status()).toBe(403);
  expect((await a.manager2.api.post(base, { data: { content: 'Revoked fixture message' } })).status()).toBe(403);
  await database(db => db.collection('teams').updateOne({ _id: new ObjectId(l.teams[1].id) }, { $set: { owner_id: a.manager2.id } }));
});

test('CHAT-03 RES-02 failed send retains draft and retry creates one message', async ({ page }) => {
  const ui = new MobileExperiencePage(page); await ui.goto('/chat'); await expect(ui.input).toBeEnabled(); await ui.dismissInstallIfPresent();
  const text = `Recoverable QA ${crypto.randomUUID()}`;
  await page.route('**/api/chat/channels/*/messages', async route => {
    if (route.request().method() === 'POST') await route.fulfill({ status: 503, json: { detail: 'QA send unavailable' } }); else await route.continue();
  });
  await ui.input.fill(text); await ui.send.click();
  await expect(page.getByText('QA send unavailable', { exact: true })).toBeVisible(); await expect(ui.input).toHaveValue(text);
  expect(await database(db => db.collection('chat_messages').countDocuments({ league_id: l.id, content: text }))).toBe(0);
  await page.unroute('**/api/chat/channels/*/messages');
  await ui.send.click(); await expect(ui.input).toHaveValue('');
  expect(await database(db => db.collection('chat_messages').countDocuments({ league_id: l.id, content: text }))).toBe(1);
});

test('CHAT-03 second emulated session receives fixture message and clears unread', async ({ page, browser }, info) => {
  const options = info.project.use;
  const second = await browser.newContext({ ...options, storageState: await a.manager2.api.storageState() } as any);
  try {
    await second.addInitScript(id => localStorage.setItem('dd_active_league_id', id), l.id);
    const other = await second.newPage(); const peer = new MobileExperiencePage(other);
    await peer.goto('/chat'); await expect(peer.input).toBeEnabled();
    const ui = new MobileExperiencePage(page); await ui.goto('/chat'); await expect(ui.input).toBeEnabled();
    const text = `Polling QA ${crypto.randomUUID()}`;
    await ui.input.fill(text); await ui.send.click(); await expect(ui.input).toHaveValue('');
    const row = await database(db => db.collection('chat_messages').findOne({ league_id: l.id, content: text })); expect(row).toBeTruthy();
    await expect(peer.message(String(row!._id))).toContainText(text, { timeout: 20000 });
    const channels = await result(await a.manager2.api.get(`/api/chat/channels?league_id=${l.id}`));
    expect(channels.channels.find((c: any) => c._id === row!.channel_id).unread).toBe(0);
  } finally { await second.close(); }
});

test('CHAT-04 notification link marks only recipient row read and survives reload', async ({ page }, info) => {
  const id = new ObjectId(), privateId = new ObjectId();
  await database(db => db.collection('notifications').insertMany([
    { _id: id, user_id: a.manager.id, league_id: l.id, type: 'announcement', title: 'Mobile QA navigation', message: 'Disposable notification', link: '/chat', read: false, created_at: new Date() },
    { _id: privateId, user_id: a.manager2.id, league_id: l.id, type: 'announcement', title: 'Other recipient only', message: 'Private fixture', read: false, created_at: new Date() }
  ]));
  const ui = new MobileExperiencePage(page); await ui.goto('/dashboard'); await expect(ui.dashboard).toBeVisible();
  await ui.notificationButton.click(); await expect(ui.notifications).toBeVisible(); await expect(ui.notification(String(id))).toBeVisible();
  await expect(ui.notification(String(privateId))).toHaveCount(0);
  await ui.notification(String(id)).click(); await expect(page).toHaveURL(/\/chat$/);
  await expect.poll(async () => (await database(db => db.collection('notifications').findOne({ _id: id })))!.read).toBe(true);
  expect((await database(db => db.collection('notifications').findOne({ _id: privateId })))!.read).toBe(false);
  await page.reload(); await ui.notificationButton.click(); await expect(ui.notification(String(id))).toBeVisible();
  await info.attach('notifications', { body: await page.screenshot(), contentType: 'image/png' });
});

for (const width of [320, 390, 430]) test(`MOB-01 dashboard and chat fit ${width}px without hiding composer`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 844 }); const ui = new MobileExperiencePage(page);
  await ui.goto('/dashboard'); await expect(ui.dashboard).toBeVisible(); await ui.dismissInstallIfPresent();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
  await ui.goto('/chat'); await expect(ui.input).toBeEnabled();
  await info.attach('chat-width', { body: await page.screenshot(), contentType: 'image/png' });
  const bounds = await ui.send.boundingBox(); expect(bounds).toBeTruthy();
  expect(bounds!.x).toBeGreaterThanOrEqual(0); expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
});

test('CHAT-01 X-02 rapid repeated send cannot persist duplicate message', async ({ page }) => {
  const ui = new MobileExperiencePage(page); await ui.goto('/chat'); await expect(ui.input).toBeEnabled(); await ui.dismissInstallIfPresent();
  const text = `Repeat QA ${crypto.randomUUID()}`;
  let release!: () => void; let intercepted = 0; let completed = 0;
  page.on('response', response => { if (response.request().method() === 'POST' && /\/api\/chat\/channels\/[^/]+\/messages$/.test(new URL(response.url()).pathname)) completed++; });
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/chat/channels/*/messages', async route => {
    if (route.request().method() !== 'POST') { await route.continue(); return; }
    intercepted++; await gate; await route.continue();
  });
  try {
    await ui.input.fill(text); await ui.send.click();
    await expect.poll(() => intercepted).toBe(1);
    if (await ui.send.isEnabled()) { await ui.send.click(); await expect.poll(() => intercepted).toBe(2); }
  } finally { release(); }
  await expect.poll(() => completed).toBe(intercepted);
  await expect(ui.input).toHaveValue('');
  await expect.poll(async () => database(db => db.collection('chat_messages').countDocuments({ league_id: l.id, content: text }))).toBe(1);
});

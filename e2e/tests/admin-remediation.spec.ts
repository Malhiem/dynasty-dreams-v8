import { test, expect } from '@playwright/test';
import { database } from '../support/h2h';
import { ObjectId } from 'mongodb';

test.beforeEach(async ({ page }) => {
  if (process.env.E2E_BASE_URL !== 'http://web' || process.env.H2H_ISOLATED !== '1') throw new Error('Admin tests require the disposable Compose stack');
  const response = await page.request.post('/api/auth/login', { data: { email: process.env.E2E_ADMIN_EMAIL, password: process.env.E2E_ADMIN_PASSWORD } });
  expect(response.ok()).toBeTruthy();
  await page.goto('/admin'); await expect(page.getByTestId('admin-dashboard-page')).toBeVisible();
});

for (const width of [390, 768, 1440]) test(`all Admin tabs stay usable at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
  const tabs = await page.getByTestId('admin-sidebar-nav').getByRole('tab').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-testid')!));
  expect(tabs).toHaveLength(25);
  for (const id of tabs) {
    await page.getByTestId(id).click();
    const panel = page.locator('[role="tabpanel"][data-state="active"]');
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('button', { name: '', exact: true })).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(await panel.evaluate(node => node.getBoundingClientRect().width)).toBeGreaterThanOrEqual(Math.min(280, width - 40));
  }
});

test('keyboard opens named user drawer, traps focus, closes and restores opener', async ({ page }) => {
  await page.getByTestId('admin-tab-users').click();
  const opener = page.getByRole('button', { name: /^View details for/ }).first();
  await opener.focus(); await page.keyboard.press('Enter');
  const drawer = page.getByRole('dialog', { name: 'User detail', exact: true });
  await expect(drawer).toBeVisible();
  await expect.poll(() => drawer.evaluate(node => node.contains(document.activeElement))).toBe(true);
  for (let i = 0; i < 12; i++) { await page.keyboard.press('Shift+Tab'); expect(await drawer.evaluate(node => node.contains(document.activeElement))).toBe(true); }
  await page.keyboard.press('Escape'); await expect(drawer).toHaveCount(0); await expect(opener).toBeFocused();
});

test('keyword loading and failed refresh never masquerade as successful empty rules', async ({ page }) => {
  let reply: () => void = () => {};
  const gate = new Promise<void>(resolve => { reply = resolve; });
  let calls = 0;
  await page.route('**/api/admin/platform/keyword-filters', async route => {
    calls++;
    if (calls === 1) { await gate; await route.fulfill({ status: 200, json: { filters: [{ filter_id: 'old', word: 'old-rule', severity: 'high' }] } }); }
    else if (calls === 2) await route.fulfill({ status: 500, json: { detail: 'Controlled refresh failure' } });
    else await route.fulfill({ status: 200, json: { filters: [{ filter_id: 'new', word: 'new-rule', severity: 'low' }] } });
  });
  await page.getByTestId('admin-tab-moderation').click(); const rules = page.getByTestId('keyword-filters-section');
  await expect(rules.getByRole('status')).toContainText('Loading'); await expect(rules).not.toContainText('No keywords configured');
  reply(); await expect(rules).toContainText('old-rule');
  await rules.getByRole('button', { name: 'Refresh rules' }).click();
  await expect(rules.getByRole('alert')).toContainText('Controlled refresh failure');
  await expect(rules).toContainText('old-rule'); await expect(rules).toContainText('may be out of date');
  await rules.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(rules.getByRole('alert')).toHaveCount(0); await expect(rules).toContainText('new-rule'); await expect(rules).not.toContainText('old-rule');
});

test('keyword access denial clears previously loaded sensitive rules', async ({ page }) => {
  let count = 0;
  await page.route('**/api/admin/platform/keyword-filters', route => ++count === 1
    ? route.fulfill({ status: 200, json: { filters: [{ filter_id: 'private', word: 'private-rule', severity: 'high' }] } })
    : route.fulfill({ status: 403, json: { detail: 'Access revoked' } }));
  await page.getByTestId('admin-tab-moderation').click(); const rules = page.getByTestId('keyword-filters-section');
  await expect(rules).toContainText('private-rule'); await rules.getByRole('button', { name: 'Refresh rules' }).click();
  await expect(rules.getByRole('alert')).toContainText('Access revoked'); await expect(rules).not.toContainText('private-rule');
  await expect(rules.getByTestId('keyword-add-btn')).toBeDisabled(); await expect(rules).not.toContainText('No keywords configured');
});

test('user results retain the latest search when responses arrive out of order', async ({ page }) => {
  let release: () => void = () => {}, seen: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; }), received = new Promise<void>(resolve => { seen = resolve; });
  await page.route('**/api/admin/platform/users?*', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'older-query') { seen(); await gate; }
    if (q === 'older-query' || q === 'newer-query') await route.fulfill({ status: 200, json: { total: 1, users: [{ id: q, username: q, email: q + '@acceptance.local', role: 'user' }] } });
    else await route.continue();
  });
  await page.getByTestId('admin-tab-users').click(); const search = page.getByTestId('users-search-input');
  await search.fill('older-query'); await received; await search.fill('newer-query');
  await expect(page.getByTestId('users-table')).toContainText('newer-query');
  const older = page.waitForResponse(response => response.url().includes('q=older-query')); release(); await older;
  await expect(page.getByTestId('users-table')).toContainText('newer-query'); await expect(page.getByTestId('users-table')).not.toContainText('older-query');
});

test('credit retry after an uncertain response reuses its operation key and applies once', async ({ page, request }) => {
  const suffix = crypto.randomUUID().replace(/-/g, '').slice(0, 10), email = `admin-retry-${suffix}@example.com`;
  const registered = await request.post('/api/auth/register', { data: { email, username: 'retry' + suffix, name: 'Credit retry fixture', password: 'RetryFixture123!' } });
  expect(registered.ok()).toBeTruthy(); const target = await registered.json();
  await page.getByTestId('admin-tab-users').click(); await page.getByTestId('users-search-input').fill(email);
  await page.getByRole('button', { name: 'View details for retry' + suffix, exact: true }).click();
  await page.getByTestId('action-promo-credit').click(); const dialog = page.getByTestId('action-dialog-promo-credit');
  await dialog.getByTestId('field-amount_cents').fill('100'); await dialog.getByTestId('field-note').fill('One browser operation');
  const keys: string[] = [];
  await page.route(`**/api/admin/platform/users/${target.id}/promo-credit`, async route => {
    keys.push(route.request().headers()['idempotency-key']);
    const response = await route.fetch(); expect(response.ok()).toBeTruthy();
    if (keys.length === 1) await route.fulfill({ status: 503, json: { detail: 'Response lost after commit; retry the same operation' } });
    else await route.fulfill({ response });
  });
  await dialog.getByTestId('dialog-submit-btn').click(); await expect(dialog.getByTestId('dialog-submit-btn')).toBeEnabled();
  await dialog.getByTestId('dialog-submit-btn').click(); await expect(dialog).toHaveCount(0);
  expect(keys).toHaveLength(2); expect(keys[0]).toBeTruthy(); expect(keys[1]).toBe(keys[0]);
  await database(async db => {
    expect((await db.collection('users').findOne({ _id: new ObjectId(target.id) }))?.promo_credits_cents).toBe(100);
    expect(await db.collection('admin_user_actions').countDocuments({ target_user_id: target.id, action: 'promo_credit' })).toBe(1);
  });
});

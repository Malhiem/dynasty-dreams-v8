import { test, expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { actors, dispose, league, type Actors } from '../support/access-history';
import { database, result, type League } from '../support/h2h';
import { MobileExperiencePage } from '../pages/mobile-experience/mobile-experience.page';
class DashboardRecoveryPage extends MobileExperiencePage {
  get leagues() { return this.page.getByTestId('my-leagues-ordered'); }
  get loading() { return this.page.getByTestId('my-leagues-loading'); }
  leagueLink(id: string) { return this.page.getByTestId(`my-leagues-link-${id}`); }
  get loadError() { return this.page.getByRole('alert').filter({ hasText: /league|load|unavailable|failed/i }); }
  get install() { return this.page.getByRole('dialog', { name: 'Install DynastyDreams', exact: true }); }
  get bottomChat() { return this.page.getByTestId('mobile-bottom-nav-chat'); }
}
let a: Actors; let l: League; let name: string;
test.beforeAll(async () => {
  a = await actors(); l = await league(a); name = `Mobile dashboard ${crypto.randomUUID()}`;
  await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { name } }));
});
test.afterAll(async () => { if (a) await dispose(a); });
test.beforeEach(async ({ context }) => {
  await context.addCookies((await a.manager.api.storageState()).cookies);
  await context.addInitScript(id => localStorage.setItem('dd_active_league_id', id), l.id);
});
test('DASH-01 DASH-04 known league widget opens correct league and browser back restores dashboard', async ({ page }) => {
  const ui = new DashboardRecoveryPage(page); await ui.goto('/dashboard');
  await expect(ui.leagueLink(l.id)).toHaveText(name); await ui.dismissInstallIfPresent();
  await ui.leagueLink(l.id).click(); await expect(page).toHaveURL(new RegExp(`/leagues/${l.id}$`));
  await page.goBack(); await expect(ui.dashboard).toBeVisible(); await expect(ui.leagueLink(l.id)).toHaveText(name);
});
test('DASH-02 reload uses authoritative renamed league without duplicate rows', async ({ page }) => {
  const ui = new DashboardRecoveryPage(page); await ui.goto('/dashboard'); await expect(ui.leagueLink(l.id)).toHaveText(name);
  const changed = `${name} revised`;
  try {
    await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { name: changed } }));
    await page.reload(); await expect(ui.leagueLink(l.id)).toHaveText(changed); await expect(ui.leagueLink(l.id)).toHaveCount(1);
  } finally { await result(await a.commissioner.api.put(`/api/leagues/${l.id}`, { data: { name } })); }
});
test('DASH-03 RES-01 failed league widget load is distinguishable from empty data', async ({ page }, info) => {
  const ui = new DashboardRecoveryPage(page);
  await page.route('**/api/leagues?my_leagues=true&exclude_archived=true&exclude_test=true', route => route.fulfill({ status: 503, json: { detail: 'QA league load unavailable' } }));
  await ui.goto('/dashboard'); await expect(ui.dashboard).toBeVisible(); await expect(ui.loading).toBeHidden();
  await info.attach('failed-dashboard-load', { body: await page.screenshot(), contentType: 'image/png' });
  await expect(ui.loadError).toBeVisible();
  await page.unroute('**/api/leagues?my_leagues=true&exclude_archived=true&exclude_test=true');
  await page.reload(); await expect(ui.leagueLink(l.id)).toHaveText(name);
});
test('A11Y-01 notification control has meaningful accessible name', async ({ page }) => {
  const ui = new DashboardRecoveryPage(page); await ui.goto('/dashboard'); await expect(ui.notificationButton).toBeVisible();
  await expect(ui.notificationButton).toHaveAccessibleName(/notification/i);
});
test('A11Y-01 chat send control has meaningful accessible name', async ({ page }) => {
  const ui = new DashboardRecoveryPage(page); await ui.goto('/chat'); await expect(ui.input).toBeEnabled();
  await expect(ui.send).toHaveAccessibleName(/send/i);
});
test('MOB-05 iPhone install dismissal restores bottom chat navigation and persists on reload', async ({ page }, info) => {
  test.skip(info.project.name !== 'iphone-webkit-emulated', 'iOS install guidance requires the iPhone WebKit context.');
  const ui = new DashboardRecoveryPage(page); await ui.goto('/dashboard'); await expect(ui.install).toBeVisible();
  await ui.bannerDismiss.click(); await expect(ui.install).toBeHidden();
  await ui.bottomChat.click(); await expect(page).toHaveURL(/\/chat$/); await expect(ui.input).toBeEnabled();
  await page.reload(); await expect(ui.install).toBeHidden(); await expect(ui.input).toBeEnabled();
});

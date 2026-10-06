import type { Page } from '@playwright/test';
import { selectors } from './history-trophy.selectors';
export async function open(page: Page, league: string, route: string) {
  await page.addInitScript(id => localStorage.setItem('dd_active_league_id', id), league);
  await page.goto(route, {waitUntil: 'domcontentloaded'});
}
export async function selectYear(page: Page, year: number | 'all') {
  await selectors(page).years().selectOption(String(year));
}
export async function selectTeam(page: Page, currentName: string, nextName: string) {
  await selectors(page).teamPicker(currentName).click();
  await page.getByRole('option', {name: new RegExp(nextName)}).click();
}

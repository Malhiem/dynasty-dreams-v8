import type { Page } from '@playwright/test';
import { selectors } from './history-trophy.selectors';
import * as actions from './history-trophy.actions';
export class HistoryTrophyPage {
  readonly ui;
  constructor(readonly page: Page) { this.ui = selectors(page); }
  open(league: string, route: string) { return actions.open(this.page, league, route); }
  year(year: number | 'all') { return actions.selectYear(this.page, year); }
  selectTeam(current: string, next: string) { return actions.selectTeam(this.page, current, next); }
}

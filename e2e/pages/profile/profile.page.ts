import type { Page } from '@playwright/test';
import { profileSelectors } from './profile.selectors';
import { profileActions } from './profile.actions';
export class ProfilePage {
  readonly ui;
  readonly actions;
  constructor(page: Page) { this.ui=profileSelectors(page); this.actions=profileActions(page); }
}

import type { Page } from "@playwright/test";

import {
  savePlayoffs,
  saveRegularSeason,
  saveScheduleMix,
} from "./league-structure.actions";

/** Commissioner League Structure tab for regular-season and playoff setup. */
export class LeagueStructurePage {
  constructor(private readonly page: Page) {}

  async goto(leagueId: string): Promise<void> {
    await this.page.addInitScript((id) => {
      window.localStorage.setItem("dd_active_league_id", id);
    }, leagueId);
    await this.page.goto("/commissioner/settings?tab=divisions");
  }

  async saveScheduleMix(): Promise<void> {
    await saveScheduleMix(this.page);
  }

  async saveRegularSeason(): Promise<void> {
    await saveRegularSeason(this.page);
  }

  async savePlayoffs(): Promise<void> {
    await savePlayoffs(this.page);
  }
}

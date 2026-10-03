import type { Page } from "@playwright/test";
import { leagueScoringSelectors as selectors } from "./league-scoring.selectors";

export async function openLeaguePage(page: Page, leagueId: string, path: string) {
  await page.addInitScript((id) => localStorage.setItem("dd_active_league_id", id), leagueId);
  await page.goto(path);
}

export async function selectFormat(page: Page, label: string) {
  await selectors.format(page, label).click();
}

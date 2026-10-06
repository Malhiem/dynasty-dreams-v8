import type { Page } from "@playwright/test";

import { joinLeagueSelectors } from "./join-league.selectors";

export async function joinLeague(page: Page, teamName: string): Promise<void> {
  await page.getByTestId(joinLeagueSelectors.teamName).fill(teamName);
  await page.getByTestId(joinLeagueSelectors.submit).click();
}

export async function openJoinedLeague(page: Page): Promise<void> {
  await page.getByTestId(joinLeagueSelectors.goToLeague).click();
}

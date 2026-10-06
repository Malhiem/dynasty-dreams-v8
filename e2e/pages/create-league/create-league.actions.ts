import type { Page } from "@playwright/test";

import { createLeagueSelectors } from "./create-league.selectors";

export interface CreatedLeague {
  id: string;
  invite_code: string;
}

export async function createPrivateLeague(
  page: Page,
  name: string,
): Promise<CreatedLeague> {
  await page.getByTestId(createLeagueSelectors.name).fill(name);
  await page.getByTestId(createLeagueSelectors.maxTeams).click();
  await page.getByRole("option", { name: "24 Teams", exact: true }).click();
  await page.getByTestId(createLeagueSelectors.private).click();

  const response = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "POST" &&
      new URL(candidate.url()).pathname === "/api/leagues" &&
      candidate.ok(),
  );
  await page.getByTestId(createLeagueSelectors.submit).click();
  return (await (await response).json()) as CreatedLeague;
}

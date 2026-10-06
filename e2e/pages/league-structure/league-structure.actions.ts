import type { Page } from "@playwright/test";

import { leagueStructureSelectors } from "./league-structure.selectors";

async function selectOption(page: Page, testId: string, name: string): Promise<void> {
  await page.getByTestId(testId).click();
  await page.getByRole("option", { name, exact: true }).click();
}

export async function saveScheduleMix(page: Page): Promise<void> {
  const defer = page.getByRole("button", { name: "Set Up Later", exact: true });
  if (await defer.isVisible()) await defer.click();
  await page.getByTestId(leagueStructureSelectors.scheduleMixIntraDivision).fill("5");
  await page.getByTestId(leagueStructureSelectors.scheduleMixIntraConference).fill("2");
  await page.getByTestId(leagueStructureSelectors.scheduleMixInterConference).fill("12");
  await page.getByTestId(leagueStructureSelectors.scheduleMixSave).click();
}

export async function saveRegularSeason(page: Page): Promise<void> {
  await page.getByTestId(leagueStructureSelectors.regularSeasonWeeks).fill("25");
  await page.getByTestId(leagueStructureSelectors.matchupLength).fill("7");
  await page.getByTestId(leagueStructureSelectors.opponentsPerPeriod).fill("2");
  await selectOption(page, leagueStructureSelectors.statsStart, "Week 1 (Oct 6 – Oct 12)");
  await selectOption(page, leagueStructureSelectors.statsEnd, "Week 28 (Apr 13 – Apr 19)");
  await page.getByTestId(leagueStructureSelectors.regularSeasonSave).click();
}

export async function savePlayoffs(page: Page): Promise<void> {
  await page.getByTestId(leagueStructureSelectors.playoffTeams).fill("8");
  await selectOption(page, leagueStructureSelectors.playoffStartWeek, "Week 26");
  await selectOption(page, leagueStructureSelectors.playoffEndWeek, "Week 28");
  await selectOption(page, leagueStructureSelectors.playoffRounds, "3 Rounds");
  await selectOption(
    page,
    leagueStructureSelectors.playoffFormat,
    "Playoff Tree (elimination bracket)",
  );
  await page.getByTestId(leagueStructureSelectors.playoffsSave).click();
}

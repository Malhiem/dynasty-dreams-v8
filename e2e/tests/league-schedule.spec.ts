import { expect, test } from "@playwright/test";

import { CreateLeaguePage } from "../pages/create-league/create-league.page";
import { LeagueStructurePage } from "../pages/league-structure/league-structure.page";
import { leagueStructureSelectors } from "../pages/league-structure/league-structure.selectors";
import { LoginPage } from "../pages/login/login.page";

const adminCredentials = {
  email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com",
  password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password",
};

test("commissioner can configure the requested regular season and playoff tree", async ({
  page,
}) => {
  const suffix = Date.now();
  const loginPage = new LoginPage(page);
  const createLeaguePage = new CreateLeaguePage(page);
  const leagueStructurePage = new LeagueStructurePage(page);

  await loginPage.goto();
  await loginPage.logIn(adminCredentials);
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);

  await createLeaguePage.goto();
  const league = await createLeaguePage.createPrivateLeague(`E2E Schedule League ${suffix}`);
  await leagueStructurePage.goto(league.id);
  await expect(page.getByTestId("divisions-tab")).toBeVisible();

  const scheduleMixSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === `/api/leagues/${league.id}/schedule-config` &&
      response.ok(),
  );
  await leagueStructurePage.saveScheduleMix();
  const scheduleMixResponse = await scheduleMixSaved;
  expect(scheduleMixResponse.request().postDataJSON()).toEqual({
    intra_division_games: 5,
    intra_conference_games: 2,
    inter_conference_games: 12,
  });
  await expect(page.getByTestId("schedule-mix-status-configured")).toBeVisible();
  await expect(page.getByTestId(leagueStructureSelectors.scheduleMixInterConference)).toHaveValue("12");

  const regularSeasonSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === `/api/leagues/${league.id}` &&
      response.ok(),
  );
  await leagueStructurePage.saveRegularSeason();
  await regularSeasonSaved;
  await expect(page.getByTestId(leagueStructureSelectors.regularSeasonWeeks)).toHaveValue("25");
  await expect(page.getByTestId(leagueStructureSelectors.matchupLength)).toHaveValue("7");
  await expect(page.getByTestId(leagueStructureSelectors.opponentsPerPeriod)).toHaveValue("2");

  const playoffsSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === `/api/leagues/${league.id}` &&
      response.ok(),
  );
  await leagueStructurePage.savePlayoffs();
  await playoffsSaved;
  await expect(page.getByTestId(leagueStructureSelectors.playoffTeams)).toHaveValue("8");
  await expect(page.getByTestId(leagueStructureSelectors.playoffStartWeek)).toContainText("Week 26");
  await expect(page.getByTestId(leagueStructureSelectors.playoffEndWeek)).toContainText("Week 28");
  await expect(page.getByTestId(leagueStructureSelectors.playoffRounds)).toContainText("3 Rounds");
  await expect(page.getByTestId(leagueStructureSelectors.playoffFormat)).toContainText(
    "Playoff Tree (elimination bracket)",
  );
});

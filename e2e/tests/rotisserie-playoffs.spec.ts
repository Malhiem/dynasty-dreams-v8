import { expect, test } from "@playwright/test";
import { LoginPage } from "../pages/login/login.page";
import { LeagueScoringPage } from "../pages/league-scoring/league-scoring.page";
import { LeagueStructurePage } from "../pages/league-structure/league-structure.page";
import { createRotisserieFixture } from "../support/rotisserie";

test.beforeEach(async ({ page }) => {
  const login = new LoginPage(page);
  await login.goto();
  await login.logIn({ email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com",
    password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password" });
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);
});

test("Rotisserie administration provides a main playoff enable/disable toggle", async ({ page }) => {
  const league = await createRotisserieFixture(page.request);
  const scoring = new LeagueScoringPage(page);
  await scoring.goto(league.id);
  await expect(scoring.selectors.setup(page)).toBeVisible();
  await expect(scoring.selectors.playoffToggle(page)).toBeVisible();
  await expect(scoring.selectors.playoffToggle(page)).toBeEnabled();
});

test("Rotisserie supports saving an eight-team three-round elimination bracket", async ({ page }, info) => {
  const league = await createRotisserieFixture(page.request);
  // API setup avoids coupling this test to the already-failing scoring-format UI.
  const setup = await page.request.put(`/api/leagues/${league.id}`, { data: { regular_season_weeks: 25 } });
  expect(setup.ok()).toBeTruthy();
  const scoring = new LeagueScoringPage(page);
  await scoring.structure(league.id);
  await expect(scoring.selectors.structure(page)).toBeVisible();
  const saved = page.waitForResponse(r => r.request().method() === "PUT" &&
    new URL(r.url()).pathname === `/api/leagues/${league.id}`);
  await new LeagueStructurePage(page).savePlayoffs();
  expect((await saved).ok()).toBeTruthy();
  const response = await page.request.get(`/api/leagues/${league.id}`);
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toMatchObject({ scoring_format: "rotisserie", playoff_teams: 8,
    playoff_start_week: 26, playoff_end_week: 28, playoff_rounds: 3, playoff_format: "playoff_tree" });
  await page.reload();
  await expect(scoring.selectors.playoffTeams(page)).toHaveValue("8");
  await expect(scoring.selectors.playoffStart(page)).toContainText("Week 26");
  await expect(scoring.selectors.playoffEnd(page)).toContainText("Week 28");
  await expect(scoring.selectors.playoffRounds(page)).toContainText("3 Rounds");
  await expect(scoring.selectors.playoffFormat(page)).toContainText("Playoff Tree");
  const bracketResponse = await page.request.get(`/api/leagues/${league.id}/playoff-bracket`);
  expect(bracketResponse.ok()).toBeTruthy();
  const bracket = await bracketResponse.json();
  await info.attach("eight-team-bracket", { body: JSON.stringify(bracket, null, 2), contentType: "application/json" });
  expect(bracket.playoff_teams).toHaveLength(8);
  expect(bracket.rounds.map((round: { matchups: unknown[] }) => round.matchups.length)).toEqual([4, 2, 1]);
  // This is a projected bracket, not evidence of completed eliminations or a champion.
  expect(bracket.status).toBe("projected");
});

test("Rotisserie playoff format offers a condensed Rotisserie scoring period", async ({ page }, info) => {
  const league = await createRotisserieFixture(page.request);
  const scoring = new LeagueScoringPage(page);
  await scoring.structure(league.id);
  await expect(scoring.selectors.structure(page)).toBeVisible();
  await scoring.selectors.playoffFormat(page).click();
  await info.attach("available-playoff-formats", { body: JSON.stringify(await scoring.selectors.playoffOptions(page).allTextContents()), contentType: "application/json" });
  await expect(scoring.selectors.condensedOption(page)).toBeVisible();
});

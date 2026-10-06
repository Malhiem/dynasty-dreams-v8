import { expect, test } from "@playwright/test";

import { CreateLeaguePage } from "../pages/create-league/create-league.page";
import { JoinLeaguePage } from "../pages/join-league/join-league.page";
import { LeagueDetailPage } from "../pages/league-detail/league-detail.page";
import { LoginPage } from "../pages/login/login.page";
import { RegisterPage } from "../pages/register/register.page";

const adminCredentials = {
  email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com",
  password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password",
};
const playerPassword = "E2ePlayer1!";

test("admin can create a league and a player can join with its invite code", async ({
  page,
}) => {
  const suffix = Date.now();
  const leagueName = `E2E Invite League ${suffix}`;
  const player = {
    username: `e2eplayer${suffix}`,
    email: `e2eplayer${suffix}@e2e.dynastydreams.com`,
    password: playerPassword,
  };
  const teamName = `Invite Team ${suffix}`;
  const loginPage = new LoginPage(page);
  const createLeaguePage = new CreateLeaguePage(page);
  const registerPage = new RegisterPage(page);
  const joinLeaguePage = new JoinLeaguePage(page);
  const leagueDetailPage = new LeagueDetailPage(page);

  await loginPage.goto();
  await loginPage.logIn(adminCredentials);
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);

  await createLeaguePage.goto();
  const league = await createLeaguePage.createPrivateLeague(leagueName);
  expect(league.invite_code).toBeTruthy();
  await expect(page).toHaveURL(new RegExp(`/leagues/${league.id}(?:$|\\?)`));

  await page.context().clearCookies();
  await registerPage.goto();
  await registerPage.register(player);
  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);

  await joinLeaguePage.goto(league.invite_code);
  await joinLeaguePage.join(teamName);
  await expect(page.getByText(`Welcome to ${leagueName}!`)).toBeVisible();
  await expect(page.getByText("Your team has been created")).toBeVisible();
  await joinLeaguePage.openLeague();

  await expect(page).toHaveURL(new RegExp(`/leagues/${league.id}(?:$|\\?)`));
  await expect(leagueDetailPage.standings).toContainText(teamName);
});

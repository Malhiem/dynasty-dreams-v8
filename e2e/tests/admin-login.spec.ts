import { expect, test } from "@playwright/test";

import { LoginPage } from "../pages/login/login.page";

const adminCredentials = {
  email: process.env.E2E_ADMIN_EMAIL || "admin@e2e.dynastydreams.com",
  password: process.env.E2E_ADMIN_PASSWORD || "e2e-admin-password",
};

test("admin can log in to the platform", async ({ page }) => {
  const loginPage = new LoginPage(page);

  await loginPage.goto();
  await loginPage.logInRemembered(adminCredentials);

  await expect(page).toHaveURL(/\/dashboard(?:\?|$)/);
});

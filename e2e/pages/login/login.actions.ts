import type { Page } from "@playwright/test";

import { loginSelectors } from "./login.selectors";

export interface Credentials {
  email: string;
  password: string;
}

export async function logIn(
  page: Page,
  credentials: Credentials,
): Promise<void> {
  await page.getByTestId(loginSelectors.email).fill(credentials.email);
  await page.getByTestId(loginSelectors.password).fill(credentials.password);
  await page.getByTestId(loginSelectors.submit).click();
}

export async function logInRemembered(
  page: Page,
  credentials: Credentials,
): Promise<void> {
  await page.getByTestId(loginSelectors.email).fill(credentials.email);
  await page.getByTestId(loginSelectors.password).fill(credentials.password);
  await page.getByTestId(loginSelectors.rememberMe).check();
  await page.getByTestId(loginSelectors.submit).click();
}

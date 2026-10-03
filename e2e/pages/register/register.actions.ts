import type { Page } from "@playwright/test";

import { registerSelectors } from "./register.selectors";

export interface RegistrationDetails {
  username: string;
  email: string;
  password: string;
}

export async function register(
  page: Page,
  details: RegistrationDetails,
): Promise<void> {
  await page.getByTestId(registerSelectors.username).fill(details.username);
  await page.getByTestId(registerSelectors.email).fill(details.email);
  await page.getByTestId(registerSelectors.password).fill(details.password);
  await page
    .getByTestId(registerSelectors.confirmPassword)
    .fill(details.password);
  await page.getByTestId(registerSelectors.submit).click();
}

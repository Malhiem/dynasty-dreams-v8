import type { Page } from "@playwright/test";

import { logIn, logInRemembered, type Credentials } from "./login.actions";

/** UI model for the authentication screen. */
export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/login");
  }

  async logIn(credentials: Credentials): Promise<void> {
    await logIn(this.page, credentials);
  }

  async logInRemembered(credentials: Credentials): Promise<void> {
    await logInRemembered(this.page, credentials);
  }
}

import type { Page } from "@playwright/test";
import { createPrivateLeague, type CreatedLeague } from "./create-league.actions";
export class CreateLeaguePage { constructor(private readonly page: Page) {} async goto(): Promise<void> { await this.page.goto("/leagues/create"); } async createPrivateLeague(name: string): Promise<CreatedLeague> { return createPrivateLeague(this.page, name); } }

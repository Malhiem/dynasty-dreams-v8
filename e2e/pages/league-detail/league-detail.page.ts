import type { Locator, Page } from "@playwright/test";
import { standings } from "./league-detail.actions";
export class LeagueDetailPage { constructor(private readonly page: Page) {} get standings(): Locator { return standings(this.page); } }

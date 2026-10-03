import type { Page } from "@playwright/test";
import { joinLeague, openJoinedLeague } from "./join-league.actions";
export class JoinLeaguePage { constructor(private readonly page: Page) {} async goto(code: string): Promise<void> { await this.page.goto(`/join/${code}`); } async join(teamName: string): Promise<void> { await joinLeague(this.page, teamName); } async openLeague(): Promise<void> { await openJoinedLeague(this.page); } }

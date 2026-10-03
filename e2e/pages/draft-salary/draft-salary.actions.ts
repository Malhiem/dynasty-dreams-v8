import type { Page } from "@playwright/test";
import { selectors } from "./draft-salary.selectors";
export async function open(page:Page,leagueId:string){await page.addInitScript(id=>localStorage.setItem("dd_active_league_id",id),leagueId);await page.goto("/draft-room");}
export async function choose(page:Page,id:string){const s=selectors(page);await s.candidate(id).click();await s.draftButton().click();}

export async function move(page:Page,name:string,destination:string){const s=selectors(page);await s.assignments().click();await s.rosterDestination(name).selectOption(destination);}

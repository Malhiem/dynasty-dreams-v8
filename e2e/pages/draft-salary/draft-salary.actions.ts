import type { Page } from "@playwright/test";
import { selectors } from "./draft-salary.selectors";
export async function open(page:Page,leagueId:string){await page.addInitScript(id=>localStorage.setItem("dd_active_league_id",id),leagueId);await page.goto("/draft-room");}

/** Narrow the eligible list to the fixture's "Candidate" players. On a database with many players they rank far down the list, and the room renders the whole list. */
export async function searchCandidates(page:Page){await page.getByPlaceholder("Search players...",{exact:true}).filter({visible:true}).first().fill("Candidate");}
export async function choose(page:Page,id:string){const s=selectors(page);await s.candidate(id).click();await s.draftButton().click();}

export async function move(page:Page,name:string,destination:string){const s=selectors(page);await s.assignments().click();await s.rosterDestination(name).selectOption(destination);}

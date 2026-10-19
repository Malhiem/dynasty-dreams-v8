import type { Page } from "@playwright/test";
import { selectors } from "./draft-salary.selectors";
export async function open(page:Page,leagueId:string){await page.addInitScript(id=>localStorage.setItem("dd_active_league_id",id),leagueId);await page.goto("/draft-room");}
export async function loadMore(page:Page){await selectors(page).more().click();}
export async function search(page:Page,name:string){await selectors(page).search().fill(name);}
export async function preview(page:Page,id:string,name?:string){if(name)await search(page,name);await selectors(page).candidate(id).click();}
export async function choose(page:Page,id:string,name?:string){await preview(page,id,name);await selectors(page).draftButton().click();}

export async function move(page:Page,name:string,destination:string){const s=selectors(page);await s.assignments().click();await s.rosterDestination(name).selectOption(destination);}

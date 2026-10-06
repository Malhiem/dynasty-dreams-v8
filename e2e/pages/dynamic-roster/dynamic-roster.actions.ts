import type {Page} from "@playwright/test";
import {selectors} from "./dynamic-roster.selectors";
export async function open(page:Page,leagueId:string,teamId:string){await page.addInitScript(id=>localStorage.setItem("dd_active_league_id",id),leagueId);await page.goto(`/team?team=${teamId}`);}
export async function position(page:Page,id:string,slot:string){await selectors(page).row(id).getByRole("button",{name:slot,exact:true}).click();}

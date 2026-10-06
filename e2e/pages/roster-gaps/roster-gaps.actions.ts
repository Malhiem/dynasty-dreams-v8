import type {Page} from "@playwright/test";
import {selectors} from "./roster-gaps.selectors";
export async function open(page:Page,league:string,team:string){await page.addInitScript(id=>localStorage.setItem("dd_active_league_id",id),league);await page.goto(`/team?team=${team}`);}
export async function position(page:Page,id:string,slot:string){await selectors(page).row(id).getByRole("button",{name:slot,exact:true}).click();}
export async function section(page:Page,name:string){await selectors(page).section(name).click();}

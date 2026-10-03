import type { Page } from "@playwright/test";
import { openLeaguePage } from "../league-scoring/league-scoring.actions";
import { matchupSelectors as s } from "./h2h-matchup.selectors";
export const openMatchup=(p:Page,id:string)=>openLeaguePage(p,id,"/matchup");
export async function selectWeek(p:Page,w:number){await s.week(p).click();await s.option(p,w).click();}

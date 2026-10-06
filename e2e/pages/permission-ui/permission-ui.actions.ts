import type {Page} from '@playwright/test';
import {selectors} from './permission-ui.selectors';
export async function open(p:Page,id:string){
 await p.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),id);
 await p.goto('/commissioner/settings?tab=scoring');
}
export async function saveGoals(p:Page,value:string){await selectors.goals(p).fill(value);await selectors.save(p).click();}

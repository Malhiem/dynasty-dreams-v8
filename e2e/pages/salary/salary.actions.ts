import type {Page} from '@playwright/test';
import {selectors} from './salary.selectors';
export async function open(p:Page,id:string){
 await p.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),id);
 await p.goto('/commissioner/settings');await selectors.tab(p).click();
}

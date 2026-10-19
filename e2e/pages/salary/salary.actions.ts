import type {Page} from '@playwright/test';
import {selectors} from './salary.selectors';
export async function selectTab(p:Page){
 if ((p.viewportSize()?.width ?? 1280) < 768) {
  await p.getByTestId('commissioner-settings-mobile-tab-select').selectOption('salary-cap-contracts');
 } else await selectors.tab(p).click();
}
export async function open(p:Page,id:string){
 await p.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),id);
 await p.goto('/commissioner/settings');await selectTab(p);
}

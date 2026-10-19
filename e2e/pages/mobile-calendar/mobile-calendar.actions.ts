import type {Page,Locator} from '@playwright/test';
import {selectors} from './mobile-calendar.selectors';
export async function open(page:Page,leagueId:string){
 await page.goto('/dashboard');await page.evaluate(id=>localStorage.setItem('dd_active_league_id',id),leagueId);
 await page.goto('/commissioner/settings?tab=admin');await selectors(page).schedules().click();
}
export async function theme(page:Page,light:boolean){await page.evaluate(value=>{document.documentElement.classList.toggle('light',value);document.documentElement.classList.toggle('dark',!value);},light);}
export async function appearance(control:Locator){return control.evaluate(el=>{const s=getComputedStyle(el);const r=el.getBoundingClientRect();return {color:s.color,background:s.backgroundColor,colorScheme:s.colorScheme,height:r.height};});}
export async function scaleText(page:Page){await page.evaluate(()=>{document.documentElement.style.fontSize='200%';});}

import type {Page} from '@playwright/test';
import {selectors} from './league-exit.selectors';
export async function open(page:Page,id:string){const s=selectors(page,id);await s.menu().click();await s.leave().click();}

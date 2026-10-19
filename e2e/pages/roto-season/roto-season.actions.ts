import type {Page} from '@playwright/test';
import {open as openCalendar} from '../mobile-calendar/mobile-calendar.actions';
import {selectors} from './roto-season.selectors';
export async function open(page:Page,id:string){await openCalendar(page,id);await selectors(page).tab().click();}

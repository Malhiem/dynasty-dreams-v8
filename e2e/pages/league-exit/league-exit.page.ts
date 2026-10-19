import type {Page} from '@playwright/test';
import {selectors} from './league-exit.selectors';
import {open} from './league-exit.actions';
export class LeagueExitPage{readonly controls;constructor(readonly page:Page,readonly id:string){this.controls=selectors(page,id);}open(){return open(this.page,this.id);}cancel(){return this.controls.stay().click();}confirm(){return this.controls.confirm().click();}}

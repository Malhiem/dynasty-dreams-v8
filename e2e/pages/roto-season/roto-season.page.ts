import type {Page} from '@playwright/test';
import {selectors} from './roto-season.selectors';
import {open} from './roto-season.actions';
export class RotoSeasonPage{readonly controls;constructor(readonly page:Page){this.controls=selectors(page);}open(id:string){return open(this.page,id);}generate(){return this.controls.generate().click();}finalize(){return this.controls.finalize().click();}}

import type {Page} from '@playwright/test';
import {selectors} from './salary.selectors';
import {open,selectTab} from './salary.actions';
export class SalaryPage{readonly selectors=selectors;constructor(readonly page:Page){} goto(id:string){return open(this.page,id);} selectTab(){return selectTab(this.page);}}

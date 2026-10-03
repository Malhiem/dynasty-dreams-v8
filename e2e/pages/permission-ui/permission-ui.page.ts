import type {Page} from '@playwright/test';
import {selectors} from './permission-ui.selectors';
import {open,saveGoals} from './permission-ui.actions';
export class PermissionPage{
 readonly selectors=selectors;
 constructor(private page:Page){}
 goto(id:string){return open(this.page,id);}
 saveGoals(value:string){return saveGoals(this.page,value);}
}

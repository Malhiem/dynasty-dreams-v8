import type {Page} from '@playwright/test';
import {selectors} from './mobile-calendar.selectors';
import * as actions from './mobile-calendar.actions';
export class MobileCalendarPage{
 constructor(readonly page:Page){}
 open(id:string){return actions.open(this.page,id);}
 theme(light:boolean){return actions.theme(this.page,light);}
 calendar(){return selectors(this.page).calendar();}
 interval(){return selectors(this.page).interval();}
 startDay(){return selectors(this.page).startDay();}
 appearance(){return actions.appearance(this.interval());}
 scaleText(){return actions.scaleText(this.page);}
}

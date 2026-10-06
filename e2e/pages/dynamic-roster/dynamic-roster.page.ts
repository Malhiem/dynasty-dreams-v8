import type {Page} from "@playwright/test";
import {selectors} from "./dynamic-roster.selectors";
import * as actions from "./dynamic-roster.actions";
export class DynamicRosterPage{
 constructor(readonly page:Page){}
 async open(league:string,team:string){await actions.open(this.page,league,team);}
 async position(id:string,slot:string){await actions.position(this.page,id,slot);}
 assigned(id:string,slot:string){return selectors(this.page).row(id).getByRole("button",{name:slot,exact:true});}
 async save(){await selectors(this.page).save().click();}
}

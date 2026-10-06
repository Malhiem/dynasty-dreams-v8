import {expect,type Page} from "@playwright/test";
import {selectors} from "./roster-gaps.selectors";
import * as actions from "./roster-gaps.actions";
export class RosterPage{constructor(readonly page:Page){} get ui(){return selectors(this.page);}async open(l:string,t:string){await actions.open(this.page,l,t);}async position(id:string,slot:string){await actions.position(this.page,id,slot);}async section(name:string){await actions.section(this.page,name);}async searchAdd(name:string,id:string){await this.page.goto("/players");await this.ui.search().fill(name);await this.ui.add(id).click();}async save(){await expect(this.ui.save()).toHaveCount(1);await this.ui.save().click();}async swap(a:string,b:string){await this.position(a,"LW");await this.position(b,"C");}}

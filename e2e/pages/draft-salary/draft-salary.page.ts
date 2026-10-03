import type { Page } from "@playwright/test";
import {selectors} from "./draft-salary.selectors";
import * as actions from "./draft-salary.actions";
export class DraftSalaryPage {
  constructor(readonly page:Page){}
  async open(id:string){await actions.open(this.page,id);}
  async move(name:string,destination:string){await actions.move(this.page,name,destination);}
  async choose(id:string){await actions.choose(this.page,id);}
  overview(){return selectors(this.page).overview();}
  payroll(){return selectors(this.page).payroll();}
  positions(){return selectors(this.page).positions();}
  teamSelect(){return selectors(this.page).teamSelect();}
  candidate(id:string){return selectors(this.page).candidate(id);}
  destination(){return selectors(this.page).destination();}
  confirm(){return selectors(this.page).confirm();}
}

import type { Page } from "@playwright/test";
import { openMatchup,selectWeek } from "./h2h-matchup.actions";
import { matchupSelectors } from "./h2h-matchup.selectors";
export class H2HMatchupPage {
 readonly selectors=matchupSelectors;
 constructor(private readonly page:Page){}
 goto(id:string){return openMatchup(this.page,id);}
 selectWeek(w:number){return selectWeek(this.page,w);}
}

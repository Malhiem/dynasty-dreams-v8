import type {Page} from "@playwright/test";
export const selectors=(page:Page)=>({row:(id:string)=>page.getByTestId(`player-row-${id}`).filter({visible:true}),save:()=>page.getByRole("button",{name:"Save Roster",exact:true})});

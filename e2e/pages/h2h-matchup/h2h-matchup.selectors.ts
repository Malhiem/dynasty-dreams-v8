import type { Page } from "@playwright/test";
export const matchupSelectors={
 week:(p:Page)=>p.getByTestId("week-selector-trigger"),
 option:(p:Page,w:number)=>p.getByTestId(`week-option-${w}`),
 daily:(p:Page)=>p.getByTestId("matchup-tab-daily"),
 totals:(p:Page)=>p.getByTestId("matchup-tab-totals"),
};

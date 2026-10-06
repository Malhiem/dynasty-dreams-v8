import type { Page } from "@playwright/test";
export const selectors = (page:Page) => ({
  overview: () => page.getByTestId("draft-roster-overview"),
  payroll: () => page.getByTestId("draft-team-payroll"),
  positions: () => page.getByTestId("draft-team-positions"),
  teamSelect: () => page.getByLabel("View team totals"),
  candidate: (id:string) => page.getByTestId(`draft-room-eligible-row-${id}`).filter({visible:true}),
  destination: () => page.getByLabel("Draft roster destination"),
  confirm: () => page.getByTestId("draft-salary-confirm"),
  assignments: () => page.getByText("Roster assignments and salary charges",{exact:true}),
  rosterDestination: (name:string) => page.getByLabel(`Destination for ${name}`,{exact:true}),
  draftButton: () => page.getByTestId("draft-room-selected-card-draft-btn").filter({visible:true}),
});

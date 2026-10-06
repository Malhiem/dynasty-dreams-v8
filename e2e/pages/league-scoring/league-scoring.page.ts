import type { Page } from "@playwright/test";
import { openLeaguePage, selectFormat } from "./league-scoring.actions";
import { leagueScoringSelectors } from "./league-scoring.selectors";

export class LeagueScoringPage {
  readonly selectors = leagueScoringSelectors;
  constructor(private readonly page: Page) {}
  goto(id: string) { return openLeaguePage(this.page, id, "/commissioner/settings?tab=league-setup"); }
  roto(id: string) { return openLeaguePage(this.page, id, `/leagues/${id}/roto`); }
  standings(id: string) { return openLeaguePage(this.page, id, "/standings"); }
  structure(id: string) { return openLeaguePage(this.page, id, "/commissioner/settings?tab=divisions"); }
  select(label: string) { return selectFormat(this.page, label); }
}

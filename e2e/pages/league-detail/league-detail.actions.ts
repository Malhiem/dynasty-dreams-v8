import type { Page } from "@playwright/test";

import { leagueDetailSelectors } from "./league-detail.selectors";

export function standings(page: Page) {
  return page.getByTestId(leagueDetailSelectors.standings);
}

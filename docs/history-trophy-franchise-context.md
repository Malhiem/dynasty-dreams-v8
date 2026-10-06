# Franchise trophy URL context

A direct franchise trophy URL resolves its parent league from the authenticated
team trophy response, including archived franchises. It loads that league's
history and updates the standalone page's global league selection after the
authorized league history loads. Embedded views retain the host page context.

Franchise season choices come from its saved season records, banners, and
individual honors. All Time, Last 3 Seasons, and selected-year intersections
share these choices. Navigation to another franchise or league resets filters.
An existing unrelated league selection is not a prerequisite for franchise reads.

Coverage: `e2e/tests/history-final-sweep.spec.ts` uses disjoint league season
years across H2H Points, H2H Categories, and Rotisserie, including direct URL,
reload, filters, return navigation, and request races.

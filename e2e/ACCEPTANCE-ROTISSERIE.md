# Rotisserie prioritized acceptance coverage

## Regression
Run the complete existing Playwright suite, including login/invite, five scoring formats, category ranks and arithmetic, schedule configuration, optional playoffs, closed-week accumulation, elimination progression, and both champion configurations. All tests must pass; failures/skips must be reported individually. Season-only tests must explicitly disable playoffs.

## Multiweek condensed playoffs
Eight teams, goals and assists, playoff weeks 26–27, fresh totals enabled. Rank each category using combined raw statistics across those weeks, not the sum of weekly ranks/points. Expected raw stats per category for Teams 01–08: 50,46,42,38,34,30,26,22; ranks 1–8; points 8–1. Add seed bonuses 4,3,2,1 once: totals 20,17,14,11,8,6,4,2. Large seeded statistics from weeks 25 and 28 must be excluded even when those weeks are closed. Exactly two playoff periods are closed. Reclosing week 27 and rereading standings must preserve totals.

## Bonus changes champion
Use separate equivalent leagues with reversed regular-season and week-26 rankings. Without bonuses, Team 08 wins with 16 points and Team 01 has 2. With a 15-point seed-1 bonus, Team 01 has 17 and wins, while Team 08 remains at 16. Verify both standings totals and complete-season responses.

## Scope
These priorities do not cover every previously proposed gap. Live NHL ingestion, roster ownership history, permissions, rate-category ties, restart persistence, qualifier filtering, and a complete UI-only administration workflow remain separate follow-ups. Fixtures use the isolated Compose database and real HTTP endpoints; no scoring responses are mocked.

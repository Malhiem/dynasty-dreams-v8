# Acceptance criteria — remaining history and trophy gaps

Scope: League History lifetime/franchise standings, league record cards, league and franchise trophy rooms, Roster's embedded trophy room, and the player career endpoint used by player pages.

| ID | Required behavior | Regression coverage |
|---|---|---|
| GAP-01 | Switching leagues synchronizes the global picker and page. Clear the previous selection's records while loading; an older delayed response cannot overwrite the new league. | Delayed-response browser cases for League History and Trophy Room; assertions use distinct franchise IDs. |
| GAP-02 | Switching roster teams clears the old franchise's awards. Display franchise loading separately; never substitute league banners while the requested franchise is loading or fails. | Delayed embedded-franchise request and team-switch browser case. |
| GAP-03 | Primary history failures show distinct sign-in (401), access-denied (403), missing-resource (404), and request-failure states. Retry recovers when the service becomes available. Draft award failure remains distinguishable from an empty draft archive. | Twelve browser error/retry cases across League History, league trophy room, and franchise trophy room, plus draft failure/retry. |
| GAP-04 | Player dynasty-career reads authenticate before snapshot lookup. History and totals include only accessible leagues. Outsiders receive an empty history without private league names, owners, awards, or counts. Platform admins retain cross-league access. | Anonymous-before-lookup test; eight member/admin/outsider role cases across two private leagues. |
| GAP-05 | Manual and automatic completion save the league's skater/goalie point weights in the season snapshot. MVP, defenseman, goalie, franchise honors, and career scores use those frozen weights. Later live settings/stat changes do not alter historical reads. Default live scoring remains unchanged. | Six snapshot cases: manual/automatic × Points/Categories/Rotisserie; exact award scores and cross-view agreement; default engine regression. |
| GAP-06 | Most Championships displays every franchise tied for the maximum count, with each holder's winning years. When all counts are zero, display “No championships yet” without naming a record holder. | Tied-holder and zero-championship browser cases. |
| GAP-07 | When a year/recent filter excludes every award, show “No awards match these filters” and Reset filters. Reset restores All Time / All years and both banners and individual honors. Genuine unfiltered empty histories retain their existing empty messages. | League and franchise filtered-empty/reset browser cases, plus existing award-free franchise coverage. |

## Historical scoring contract

Individual awards use the application's weighted fantasy-point engine for all three formats. Category and Rotisserie standings continue using their existing category rules. Missing scoring configuration uses the application's default weights for newly captured seasons.

Older snapshots never saved their scoring rules. They retain the previous score estimates, marked `legacy_estimate` in the API and labeled in Trophy Room and Player Awards. Current rules are not retroactively applied to those snapshots. Recovering exact historical scores requires the original historical rules; this fix does not invent them.

An explicit commissioner action to recreate/correct a snapshot can replace its saved values, consistent with the existing completion workflow. Ordinary reads and later live changes do not rewrite it.

## Existing regressions retained

The previous six failed scenarios remain in the suite: anonymous and outsider history access, active-season duplication, consistent Last 3 Seasons, franchise year selection, and franchise recent selection. Championship and renewal consistency remain covered in Points and Categories; basic navigation and history aggregation remain covered in all three formats.

## Final verification

80 backend tests and 49 browser/API tests passed; no failures. Four legacy tests skipped for absent fixture prerequisites. Includes 17 new backend cases and 20 new browser cases. Production frontend build, changed-file lint, e2e TypeScript checks, and the required 13 security regressions passed. Browser tests ran serially in Chromium with retries disabled against the verified latest web container. No deployment was performed.

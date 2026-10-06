# Acceptance criteria — history integrity, tied records and archived franchises

Scope: League Hub → League History and Trophy Room; Roster → franchise Trophy Room; season completion and automatic snapshot creation; player dynasty-career reads.

## Snapshot completeness

| ID | Fixture / action | Required result | Coverage |
|---|---|---|---|
| HI-01 | A roster references a nonexistent player; attempt manual and automatic completion. | Return/raise 409. Do not overwrite a prior valid snapshot, mark the league complete, add completion metadata, or stamp a new champion. | Two backend missing-player cases. |
| HI-02 | A roster contains a malformed player ID; attempt both completion paths. | Return/raise 409 with the same preservation guarantees. | Two malformed-ID cases. |
| HI-03 | Player snapshot lookup fails transiently; attempt both paths. | Return/raise 503 explaining the snapshot was not completed. Preserve the previous snapshot and league status so completion can be retried. | Two injected database-failure cases. |
| HI-04 | No player capture errors and every roster ID resolves. | Capture all referenced players, then save the completed snapshot and status. An empty roster is valid. | Existing manual/automatic snapshot and lifecycle regressions. |

## Champion identity

| ID | Fixture / action | Required result | Coverage |
|---|---|---|---|
| HI-05 | Two franchises share a name; one has the championship flag; complete through either path. | Save the winner's team ID and championship ID list. Saved IDs remain authoritative if legacy names or flags later disagree. Preserve an existing championship award timestamp. League banners, franchise banners, lifetime titles and player career titles use the same identity. | Two backend completion cases and a duplicate-name browser case. |
| HI-06 | Two live H2H franchises have conflicting championship flags; attempt either completion path. | Return/raise 409 and create no season snapshot; require correction instead of selecting a winner by collection order. | Two conflicting-flag backend cases. |
| HI-07 | An older snapshot has no champion ID and multiple matching names. | Resolve only when exactly one matching franchise has championship evidence. Otherwise return no champion, mark the record ambiguous, and show a warning without inventing a banner. | Backend legacy-resolution case and browser ambiguity case. |

## Shared honors and record holders

| ID | Fixture / action | Required result | Coverage |
|---|---|---|---|
| HI-08 | Two teams share the highest saved season PF. | Both receive President's Trophy banners in league and franchise rooms, and both count in lifetime trophy totals. | Cross-view backend tie case and browser shared-award case. |
| HI-09 | Multiple eligible players share the highest score for MVP, goalie or defenseman. | Every tied player receives the applicable honor. League display, franchise display and player careers include each winner once per honor/year; shared honors contribute to Hall of Fame counts. | Backend all-three-award tie fixture and browser MVP tie fixture; existing configured-scoring regressions. |
| HI-10 | Several team/season entries share the all-time highest season points. | Display every tied team with its corresponding year, rather than choosing the first season/team. | Browser tied points-record case. |
| HI-11 | Two different player IDs have identical names and win twice each; change a live name afterward. | Keep two separate 2× award leaders, never merge into a 4× leader. Display saved historical names. | Browser duplicate-name/rename case. |

## Historical franchise access and ranks

| ID | Fixture / action | Required result | Coverage |
|---|---|---|---|
| HI-12 | Delete a live franchise document while retaining its snapshots; open its lifetime-history link. | Resolve identity from its newest saved snapshot; display an archived-franchise label, banners, individual honors and season records. | Archive backend and browser cases. |
| HI-13 | Read that archive anonymously or as a league outsider. | Anonymous callers receive 401 before lookup; outsiders receive 403. Current league members retain access. A missing archive returns 404 through the existing resource contract. | Archive backend case and retained access regressions. |
| HI-14 | Complete Points or Categories with known wins/PF, then change live records/settings. | Save and retain the existing H2H rank order: wins descending, PF + live points descending, then team ID ascending. Show the saved rank in franchise season records. | Two format-specific frozen-rank backend cases and browser historical H2H rank assertion. |
| HI-15 | Complete Rotisserie using category-derived totals with a tied top score, then change live settings. | Save category-derived total points and competition ranks (e.g. 1,1,3), preserving ties. With no pre-awarded champion, tied season leaders receive shared championship IDs. Repeating completion with the same tied leaders remains valid. | Rotisserie frozen-rank backend case. |
| HI-16 | Read an older Rotisserie snapshot without saved totals/ranks. | Do not infer its rank from H2H PF. Return an explicit unavailable basis and display “Unavailable (legacy standings not saved).” | Backend and browser legacy-Roto cases. |

## Contracts and boundaries

- President's Trophy continues to use saved regular-season PF; this change shares equal top scores rather than changing its existing scoring policy.
- Player award ties use the existing season scoring engine, including its score precision. All shared honors are returned in `player_awards`; all President's Trophy winners in `presidents_trophies`; champions in `champions`. Older singular fields remain available as compatibility representatives. Updated web views use the complete winner lists.
- New snapshots save `champion_team_id`, `champion_team_ids`, and per-team `rank` / `rank_basis`; Rotisserie also saves `roto_total_points`.
- Legacy H2H ranks can be reconstructed from saved records. Missing legacy Roto standings and ambiguous legacy champion identities require original data or commissioner correction; this change does not invent them.
- Archive access uses current membership in the parent league. Removing a franchise does not grant access to users outside that league.
- Prior access-control, filter, request-race, error/retry, frozen-scoring and championship/renewal regressions remain in the verification suite.
- This request implements source-code fixes and automated codebase verification. Deployment, full mobile testing, and an accessibility audit remain outside this fix set.

## Final verification

96 backend cases and 55 browser/API cases passed; no failures. 5 legacy fixture-dependent tests skipped. All 17 new backend and six new browser cases passed, alongside retained regressions and the 13 required security checks. Frontend production build, changed-file lint, e2e TypeScript checks and Git whitespace checking passed. Final API and web images were verified against their latest builds. No deployment was performed.

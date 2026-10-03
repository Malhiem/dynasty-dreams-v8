# Acceptance criteria and results

Results apply to the stated assertions, not every possible feature variant. FAIL means at least one required behavior was contradicted; PARTIAL and BLOCKED are not passes.

| ID | Result | Acceptance criterion | Evidence / limit |
|---|---|---|---|
| P01 | FAIL | Commissioner scoring changes persist through API and UI. | API passes. Browser Save Settings leaves goals at 1 after entering 7; ScoringTab receives no onSave callback. |
| P02 | PASS | Commissioner creates, edits, and removes bonuses; reload preserves values. | Real API writes and browser changes 10 → 20 → 0 pass. API deletion starts with an existing seed bonus. |
| P03 | PASS | Commissioner completes a season and persists its snapshot. | API and browser completion pass; season history contains one snapshot. |
| P04 | PASS | Both ordinary managers are denied administrative API writes, with no league-scoped mutation. | Scoring, three bonus operations, completion, period close, simulation and recalculation all denied. |
| P05 | FAIL | Restricted UI controls are hidden or disabled for managers. | Scoring Save, bonus Save and season-completion controls remain enabled. Direct API write authorization still holds. |
| P06 | FAIL | An authenticated non-member cannot read protected private-league data. | 11 of 14 tested read paths return HTTP 200. Team and two roster paths correctly deny access. |
| P07 | PASS | Non-members cannot mutate private-league administrative data. | All eight tested administrative write variants denied; relevant persistent state unchanged. |
| P08 | FAIL | Missing and expired authentication reject protected reads and writes. | Administrative writes denied. Eight read paths return HTTP 200 for each unauthenticated/expired identity. |
| P09 | FAIL | Authorization follows requested league/team identifiers. | Cross-league commissioner mutation denied; mixed league/team daily-scoring request returns another league’s data. |
| P10 | PASS | Client-supplied role and identity cannot grant administrative access. | Manager request with commissioner/user/admin fields is denied and does not mutate state. |
| P11 | FAIL | Revocation applies to reused sessions. | Revoked commissioner write denied immediately; removed member still reads 11 of 14 protected paths. |
| P12 | FAIL | Alternate scoring and nested access paths enforce the same policy. | Extra finalization/recalculation writes are protected; legacy scoring and other read paths leak data. No claim of exhaustive API-wide coverage. |
| R01 | FAIL | Past 10 units remain with A; subsequent 6 units go to B after a real trade. | H2H Points, H2H Categories and Rotisserie return A=0/B=16. H2H post-trade finalization also checks configured points-for. |
| R02 | FAIL | Recomputation preserves historical allocation. | Roto recompute reallocates old stats and category points. H2H saved records remain stable, but historical daily breakdown moves to the new owner; its recalculation only sums saved matchups. |
| R03 | FAIL | Late-arriving stats are allocated by historical ownership. | Import after trade yields A=0/B=16 instead of A=10/B=6 in all formats. |
| R04 | PARTIAL | Accepted future-effective trades retain current allocation until effective. | Pending acceptance and future processes_at verified, allocation unchanged. Automatic delayed execution is not exercised because the inherited E2E environment disables workers. |
| R05 | BLOCKED | Events before/at/after the effective boundary follow an explicit rule. | No effective-interval scoring source or documented exact-boundary contract exists; no invented boundary oracle. |
| R06 | FAIL | Drop preserves prior credit; pickup does not acquire earlier team credit. | Drop loses A’s 10 units; pickup assigns all 16 to B. Real drop/add APIs were used. |
| R07 | FAIL | Pending waiver claim earns nothing; effective pickup excludes earlier unowned stats. | Pending assertion passes; commissioner force-processing succeeds, then B receives 16 instead of 6. Scheduled worker timing is outside this run. |
| R08 | FAIL | Multiple ownership changes preserve earlier allocations. | A→B→C with no middle-interval contribution assigns all 16 to C instead of A=10/C=6. |
| R09 | FAIL | Drop/reacquire does not credit an unowned gap. | A receives 14 instead of 10 after a four-unit unowned event. |
| R10 | FAIL | Moving active→bench retains prior credit and excludes subsequent bench stats. | All tested formats return 16 instead of 10 under the active-only acceptance rule. |
| R11 | FAIL | Moving bench→active excludes earlier bench stats. | All formats return 16 instead of 6 under the active-only acceptance rule. |
| R12 | PASS | A locked ordinary-manager lineup change is rejected without mutation. | Daily lock with a 1440-minute cushion and emergency swaps disabled returns 400; saved lineup unchanged. |
| R13 | BLOCKED | A game spanning a transaction follows an explicit game/event rule. | Game-start versus event-time allocation is undefined; no validated oracle. |
| R14 | FAIL | Historical correction follows the former owner. | A’s earlier 10→12 correction instead yields A=0/B=18, rather than A=12/B=6. |
| R15 | PASS | Rejected and cancelled trades do not alter ownership or scoring. | Both actions retain A=10/B=0 across all three formats. |
| R16 | BLOCKED | Midnight and daylight-saving allocation follow the league timezone contract. | No historical league-timezone allocation contract exists; current daily grouping derives dates from updated_at. |
| R17 | FAIL | Repeated recomputation and incremental results converge on correct historical allocations. | Repeated recompute is stable for current inputs but does not preserve correct ownership. A full H2H event-based season rebuild is not exposed. |
| R18 | FAIL | Historical allocation remains consistent in standings and finalized results. | Roto’s prior A=8/B=4 category points change to A=4/B=8 on recompute. H2H scores finalized after a trade use the new owner. |
| R19 | PASS | Changing ownership in one league does not change a second league’s allocation. | The same player’s second-league allocation remains unchanged after a first-league trade; separate ownership correctness is covered by the failing R01 tests. |

# Draft salary policy

League settings: `salary_adherence_mode` (`strict` or `informal`), `draft_roster_target` (non-IR completion target), and `ir_salary_charge_pct` (0–100). Strict targets must cover configured active positions and may not exceed active + bench + minors capacity. Explicit floor-only configuration is supported. Disabling a cap without explicitly keeping the floor enabled preserves the previous disable-both behavior.

Draft salary evaluation defaults legacy leagues to Informal without imposing new Strict draft enforcement. Existing trade cap enforcement is preserved for leagues without an explicit mode; saving Informal enables salary-only trade exceptions. Ordinary ownership, eligibility, capacity and authorization remain enforced.

`services/draft_salary.py` evaluates full eligible-pool completion with distinct player identities and integer cents. Required active slots remain required even when a player is on minors or IR. Optional bench/minors requirements depend on the configured target. IR never fills a required active slot. A completed required roster cannot receive another draft selection.

Canonical payroll in `services/salary_policy.py` includes contracts, retained/buyout obligations, and assignment charges. Direct-to-IR drafting evaluates the intended destination before committing. Full/partial/zero IR charging is configured by percentage. Unknown price or bounded-search exhaustion is blocking in Strict and warned in Informal. Exact search is bounded to 30,000 states and 300 ms per uncached evaluation; a min/max interval is used only for pruning, never proof.

The league financial lease serializes picks, roster moves, cap settings and trade execution. `draft_mutations` journals the prior team state before a standalone-Mongo pick/roster update; recovery keeps committed draft picks and rolls back partial roster writes. Manual/autopick entry points recover pending journals before a new action. No-legal-choice autopick marks `salary_blocked` without advancing the turn; authorized roster/settings/trade changes clear it.

League-scoped read APIs: `GET /api/drafts/{id}/roster-status` and `POST /api/drafts/{id}/salary-eligibility` (up to 200 candidate IDs per batch). They authenticate, load the resource, then check membership. Candidate batches always evaluate against the full eligible pool. `POST /api/drafts/{id}/roster-move` additionally requires team ownership/co-ownership or administration. Picks accept `destination` and `expected_pick`.

Informal issues are deduplicated in `draft_salary_issues` and create in-app notifications; completed drafts store canonical team summaries, an explicit compliance flag, and adjustment summaries. Draft-room totals refresh after actions, every three seconds, and on focus; stale refresh failures are labelled. Fixed-charge rules do not implement auction bid/commitment feasibility.

Runtime coverage: `tests/test_draft_salary_feasibility.py`, existing draft/timer/salary boundary tests, and Chromium `e2e/tests/draft-salary.spec.ts` / `draft-creation.spec.ts`. Run only against explicitly isolated disposable databases and E2E Compose stacks; backend pytest cleanup must never target ambient/shared data.

Regular roster detail preserves the player’s complete eligible-position set and honors persisted active slots. Roster-page saving sends the selected slot (e.g. C), rather than the player’s primary position (e.g. LW). Configured active-position eligibility and individual capacities are validated even when no draft is scheduled, active or completed. Utility-slot eligibility shares the same F/SK/UTIL rules in the roster and draft paths.

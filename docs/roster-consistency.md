# Roster consistency

Valid lineup saves use last-write-wins: a later valid save may replace an earlier lineup. Every submitted assignment must still belong to the team's current roster; stale assignments for dropped or transferred players are rejected. Owner and `co_owner_ids` actors may save their team's lineup, and commissioner permissions retain their existing scope.

Direct pickups validate league-wide availability inside the existing cross-worker financial lease before membership or salary writes. Dropping a player removes its lineup entry in the same update. Pickup prechecks and direct adds both use total membership against `roster_spots`, including reserved players.

Regular lineup edits use shared assignment payroll even without a draft. Strict salary adherence rejects enabled cap/floor violations; Informal saves return visible warnings. Rejected saves retain pending edits and Save/Undo, and do not consume emergency changes. A lost response is shown as unconfirmed so users can reload authoritative state.

The roster page refreshes every five seconds and on focus/reconnect while there are no pending local edits. It preserves displayed data on transport failure and offers a stale-data notice and Retry. Real-team assignments come from the API rather than local storage. Configured section capacities, including explicit zero, govern destination controls. All owned players receive a display assignment, with overflow shown on the bench. Commissioner history records both section and positional changes with actor and before/after slots.

Live recomputation normalizes Mongo timestamps to UTC, uses game start/puck drop, and includes historical ownership after a player leaves the current roster. Lineup eligibility is checked at game start; corrections and repeat polls recompute qualifying contributions using league scoring weights. Unknown game times do not grant historical ownership credit. Legacy records without ownership tracking retain current-roster fallback.

Validation lives in `e2e/tests/roster-gaps*.spec.ts`, `roster-fix-consistency.spec.ts`, and the backend `test_roster_live_allocation.py` / `test_roster_ingestion_allocation.py` regressions. Use disposable Compose stacks. The ingestion regression requires explicit `ROSTER_TEST_ISOLATED=1`, a `DB_NAME` beginning `roster_fixes_`, and an isolated `MONGO_URL`; only NHL provider schedule/boxscore inputs are substituted.

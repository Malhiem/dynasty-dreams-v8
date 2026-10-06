# Salary cap and retention

Payroll uses an active league contract for each player when available, then
the existing inline/synthetic player price for uncovered players. A partial
contract ledger never hides remaining roster salaries or doubles a player.
Retention subtracts active dollar obligations from the receiving player's
charge and adds them to the retaining team exactly once. Explicit zero values
are preserved. Minors treatment remains governed by existing league rules.

Teams have at most three retention slots. Commissioners may configure 0–3;
zero disables new retained trades. Existing executed obligations are preserved
when settings change. Pending proposals do not reserve committed slots.
The configured percentage maximum is rechecked at execution. A second
retention applies to the transferring team's remaining financial obligation.
Amounts round to cents, half up; the remaining charge conserves the full AAV.

Retention applies to one fantasy season: the current season during play, or
the next season after completion/end. `current_season_year` supplies identity;
`complete-season` or the league's `season_end_date` supplies its end. A date-only
end includes the full UTC day, while an ISO timestamp ends at that exact instant.
Old dates retained after renewal do not end the new season. Charges and slots
release together; historical schedules and season financial snapshots remain.
Expired discounts never reduce the renewed receiving team's obligation.

Mongo-backed league leases serialize validation and financial mutations across
workers. Execution always uses current payroll/settings. Trades journal their
pre-execution financial/ownership state before writes. Errors restore that
state; a prepared journal is restored before retry after a crash. The executed
trade status marks commitment. Cached totals are presentation caches only.

Further retention chains and drop/reacquisition rules are not defined here.

## Confirmed buyout and forgiveness policy
Current applicable-season buyout charges count toward cap usage alongside roster payroll and retained charges. Future-season buyouts are excluded until their season.

League administration offers `receiver_pays` (default) and `league_waives` for retained-salary forgiveness. Both release the retainer charge and slot. The former restores the receiving player obligation; the latter preserves the discount through that fantasy season. Cancelled records and an audit event retain the amount, actor, time and selected policy. Later settings changes do not alter prior forgiveness decisions.

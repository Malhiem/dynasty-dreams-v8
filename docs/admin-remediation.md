# Admin mutation and dashboard contracts

Admin promo-credit updates and appeal resolutions require MongoDB transactions (replica set or mongos). Standalone servers return 503 before any write. Credit balance, operation record and success audit commit together; appeal decision, account sanction and success audit commit together. Existing permissions are checked before these operations.

## Credit retry contract

Send `Idempotency-Key` (1–128 ASCII characters), unique per acting administrator and intended operation, on `POST /api/admin/platform/users/{id}/promo-credit`. Keep the same key and identical target/amount/currency/note when retrying an uncertain network result. A successful replay returns the original balance-at-operation and audit ID without applying again. Reusing a key with different input returns 409. Distinct keys represent distinct credits. The dashboard retains the key during retries and replaces it when inputs change or a new action starts. Legacy calls without a key remain supported as independent operations; automatic network retries must supply a stable key.

Amount is a nonzero signed 32-bit integer number of cents. Currency is three ASCII letters; switching a nonzero balance to another currency is rejected. Operation records are durable and must not be pruned independently of the declared retry policy. A 503 can mean an uncertain credit outcome: retry with the same key, never create a new key merely because the response was lost.

## Validation and exports

Suspension duration is an integer from 1 through 3650 days. Suspension and permission-tier changes require a trimmed nonblank reason, at most 2000 characters. Invalid input is rejected before mutation. User exports expose only allowlisted linked-provider identity fields (`provider`, `subject`, `email`, `linked_at`), never arbitrary provider credentials.

## Reporting and navigation

Adoption numerator and denominator use the same current non-admin user cohort; anonymous and unresolved identities are excluded. Onboarding normalizes BSON dates and legacy ISO creation timestamps. Search/detail requests only update the current selection. Admin navigation becomes a horizontally scrollable compact tab strip on narrow screens; wide layouts retain the sidebar. Wide tables scroll within bounded regions.

Keyword rules distinguish loading, empty, loaded, failed and authorization-denied states. Retry recovers without clearing the last successful rules on an ordinary refresh error; authorization failure clears them. User details use a named modal with a native keyboard opener, focus management and Escape dismissal. Real account merge is labeled as a data transfer with confirmation, not an audit-only stub.

## Verification

Run `backend/tests/test_admin_mutations.py` and `backend/tests/test_admin_reporting.py` with explicit disposable Mongo settings; never ambient/shared configuration. Include required security suites and existing Admin regressions. Browser checks must exercise failure/retry, response ordering, keyboard navigation, compact tabs, and all 25 layouts. Verify normal production build with lint enabled. Security PDF layout checks must render every page, including wrapped Markdown tables/code.


## Release preflight and rollback

Run `python -m scripts.check_admin_readiness` from `backend/` with explicit
`MONGO_URL` and `DB_NAME` for the intended environment before releasing. The
command performs one transaction read and aborts it; it never writes. Exit 0
means the transaction read succeeded. Exit 1 blocks release: inspect connectivity,
replica-set/mongos topology, server transaction support and database permissions.
The output intentionally omits connection strings and database error details.
This does not replace credit/appeal smoke tests in a disposable staging database.

Do not convert a shared standalone server or change its connection string as part
of application startup. Provision the supported topology through the deployment
process, verify backups and run this preflight against the actual target.
Preserve `admin_credit_operations` during migrations and rollback. Rolling back
to code without the retry contract can reapply an uncertain credit: suspend
credit writes first, reconcile the original operation ID, and only resume with
a compatible writer. Never delete operation records to clear an error.

After deployment, verify the deployed revision, authenticated dashboard access,
unauthenticated/forbidden responses and read-only dashboard loading. Exercise a
credit replay and appeal resolution only with disposable staging accounts.
Review sanitized application errors. Roll back the application revision if
release gates fail; retain database records and audits for reconciliation.

## Preserved permission policy

The configured-admin-email restrictions on archived drafts and player verification
are intentional and retained. A platform-admin role alone does not grant those
two endpoints. League commissioner, co-commissioner and league-admin status do
not grant platform Admin access. User actions additionally enforce permission
tiers: moderator has only the declared soft moderation actions; admin cannot
perform senior-only financial or irreversible actions; senior_admin can. Legacy
`role=admin` without an explicit tier retains the senior-admin fallback. Read-only
impersonation cannot mutate. See `_require_admin`, `_SENIOR_ACTIONS` and
`_MODERATOR_ACTIONS` in `routes/admin_user_actions.py` for the action matrix.

Acceptance requires allowed and denied API requests for each actor, including
configured-email restrictions, and unchanged persisted data on denial. This
policy was explicitly retained during the October 16 remediation follow-up.

## Acceptance limits

Local performance measurements are a baseline, not a production service-level
objective. Record candidate revision, hardware/runtime, dataset sizes, workload,
concurrency, request count, errors, median and p95 before comparing candidates.
An agreed production dataset and latency/error budget remain a release decision.
Automated accessible-name, focus and zoom checks do not replace a human test
with a supported screen reader. Record browser/reader versions, spoken names,
errors and focus progression through navigation, user details and action dialogs.

Reproduce local zoom/name/baseline checks with `node e2e/scripts/admin-release-check.cjs`
inside the disposable E2E container, with a running Xvfb display (`DISPLAY`) and
`E2E_BASE_URL=http://web`, `H2H_ISOLATED=1`, `E2E_ADMIN_EMAIL`,
`E2E_ADMIN_PASSWORD`. Set `ADMIN_CHECK_OUTPUT` to a writable evidence directory.
The script applies actual Chromium tab zoom through a temporary test extension,
checks all 25 panels, and measures three read endpoints with four workers and
40 requests each. Failures are nonzero; JSON and a dialog screenshot are saved.
This is a seeded local baseline, not a load-test claim.

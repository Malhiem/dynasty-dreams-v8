# Account registration and management

Registration, verification, recovery and account settings use the existing React pages, FastAPI dependency injection and SendGrid integration.

## Public behavior

- Usernames are 3–32 ASCII letters, numbers, underscore, dot or hyphen. Registration and profile/admin edits check collisions case-insensitively. New or edited names also use a partial unique `username_key` index to enforce concurrent writes. Existing historical accounts are not renamed or backfilled.
- New passwords require eight characters, an ASCII uppercase letter and an ASCII number, with a 72-byte UTF-8 ceiling matching bcrypt. Existing passwords continue to work; registration, resets and changes enforce the policy.
- Signup signs the user in and requests an email-verification link. Verification is single-use and expires in one hour. Resends are limited to one per minute and replace the previous link. Verification status is available in `/auth/me` and account settings. Unverified accounts retain their existing access; no new restriction policy is introduced.
- Profile email changes require the current password. The current login address remains active until the new address is verified. Only then does the new address become the login address; the previous address receives a change notice. Resending a pending verification continues to use its pending address.
- `/forgot-password` and `/reset-password` are real browser routes. Recovery uses the existing non-enumerating response and throttle policy. Links expire after one hour, are claimed atomically, and cannot be replayed. A successful reset invalidates all other reset links, access credentials and refresh credentials. Administrative password resets issue links through this same flow and report delivery status.
- Account settings support current-password reauthentication for password changes. Password changes sign out all sessions. Username changes persist the display name and record history.
- Access tokens last 15 minutes and refresh tokens last seven days. Remember me controls persistent versus browser-session cookies, including after refresh. Mobile callers omitting the option retain persistent-token behavior.
- Logout revokes the actual issued session and clears authentication and impersonation-backup cookies. Older credentials without a session ID revoke the account's previous token version. Other tabs receive logout state and private API caches are invalidated. Forced logout revokes all sessions; individual-session revocation preserves other valid sessions.
- Banned, suspended, deactivated, deleted and merged-source accounts cannot authenticate or refresh. Account transitions revoke old credentials, and affected live Socket.IO sessions are disconnected. Reinstatement requires a fresh login. Expired timed suspensions permit fresh login.
- Existing administrative anonymization retains the account identity and team/history references, removes credential/verification state, and prevents access. Self-service deletion and automatic team handover are outside this change because their retention/ownership policy has not been defined.

## Email configuration

Production delivery uses the existing SendGrid helper with `SENDGRID_API_KEY`, `SENDER_EMAIL` and `FRONTEND_URL`. Reset links are not logged. Delivery failures are logged without tokens; the public forgot-password response remains generic. Real production delivery must be checked with configured credentials before release.

Only explicitly disposable stacks with `E2E_MODE=true` capture generated links in `account_test_mail`. This is a test-mail capture, not a production fallback or a claim that a provider accepted mail.

## Acceptance tests

`backend/tests/test_account_management.py` exercises real HTTP and Mongo behavior. Run it with the required security regressions, existing user/profile identity checks and moderation checks in an explicitly disposable API/Mongo stack. Set `SECURITY_TEST_ISOLATED=1`, `MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `JWT_SECRET` explicitly. The API and pytest database settings must match. Backend cleanup must finish before browser tests begin; it deliberately removes reserved `@example.com` fixtures.

The browser suite is `e2e/tests/account-management.spec.ts`, with selectors/actions/page model under `e2e/pages/account`, disposable API/mail fixtures under `e2e/support/account.ts`, and `e2e/account.config.ts`. Run inside the isolated network with `E2E_BASE_URL=http://web` and `ACCOUNT_ISOLATED=1`. The fixture targets the named disposable database `account_20261009`; adjust the fixture and the API database together when moving it to a new named run. It refuses ordinary local browser URLs. Use one worker and zero retries.

```
npm --prefix e2e run typecheck
npx playwright test --config=e2e/account.config.ts --reporter=list,json
```

The browser scenarios cover signup/reload/fresh login, real generated verification and reset links, invalid/expired/reused links, collision feedback, username persistence, email confirmation, password reauthentication and login, automatic refresh, revoked and merged accounts, cross-tab logout, and labelled/keyboard-operable forms at 320px in Chromium, Firefox and WebKit. Keyboard smoke checks do not replace a complete assistive-technology audit.

No production accounts, data, deployment or mail provider were used for acceptance testing.

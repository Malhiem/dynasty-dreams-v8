# Mobile fixes and acceptance criteria

Each of the 39 distinct failed tests has a remediation and observable acceptance criteria below. Implemented means code has changed; it does not mean verification passed. Tests run against disposable data, one worker, with no forced clicks. API checks do not substitute for mobile UI checks. Real-device keyboard, safe-area and screen-reader criteria remain separate.

## Implementation scope

Application changes address responsive Chat, duplicate/retried sends, dashboard load recovery, control names, depth projection overlap, season resolution, draft refresh ordering/list size, and the Trade Builder viewport. Existing local work is preserved; pre-edit files and a focused patch are retained. Test/environment and unresolved product-contract items remain explicitly separate.

The schedule trace additionally confirmed a wrong-league fallback: the selected league was missing from a capped list, and a later write targeted an older listed league. The shared hook now preserves explicit selection; direct access failures cannot substitute another league. A separate regression covers both omitted-list selection and the 200-membership boundary.

## MF-01: ROS-12 ROS-35 browser claim cancellation and automatic waiver processing

**Source test:** `roster-gaps-waiver-worker.spec.ts` · **Affected:** iPhone WebKit
**Status:** Test environment

**Fix:** Enable a bounded fixture waiver engine in the disposable stack; never enable E2E mode in production.

**Acceptance:** Cancelled claims never execute; a due valid claim runs exactly once, updates ownership/FAAB/priority consistently, and survives reload. Disabled workers must be reported as a prerequisite failure.

## MF-02: ROS-35 automatic scheduled trade h2h-categories

**Source test:** `roster-gaps-worker.spec.ts` · **Affected:** Android Chromium
**Status:** Test environment

**Fix:** Run the production trade engine against due disposable trades before asserting automatic settlement.

**Acceptance:** For this scoring format, a due accepted trade executes once; both rosters and effective-date scoring allocation reconcile. Pending/not-due/cancelled trades remain unchanged.

## MF-03: ROS-35 automatic scheduled trade h2h-points

**Source test:** `roster-gaps-worker.spec.ts` · **Affected:** Android Chromium
**Status:** Test environment

**Fix:** Run the production trade engine against due disposable trades before asserting automatic settlement.

**Acceptance:** For this scoring format, a due accepted trade executes once; both rosters and effective-date scoring allocation reconcile. Pending/not-due/cancelled trades remain unchanged.

## MF-04: ROS-35 automatic scheduled trade rotisserie

**Source test:** `roster-gaps-worker.spec.ts` · **Affected:** Android Chromium
**Status:** Test environment

**Fix:** Run the production trade engine against due disposable trades before asserting automatic settlement.

**Acceptance:** For this scoring format, a due accepted trade executes once; both rosters and effective-date scoring allocation reconcile. Pending/not-due/cancelled trades remain unchanged.

## MF-05: G10 all desktop Settings tabs render without uncaught page errors

**Source test:** `settings-gaps.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Test helper
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Select the current mobile settings dropdown instead of hidden desktop tabs.

**Acceptance:** Every available mobile settings section opens with its saved values and no uncaught page error at 320/390/430px; equivalent desktop tab navigation still works.

## MF-06: future-start contracts stay at zero before start and expire after their actual term

**Source test:** `depth-edge-cases.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-07: minors join projections from their assumed NHL year and saving leaves the real roster intact

**Source test:** `depth-edge-cases.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-08: retention expiry, RFA estimates, explicit zero, clearing and overspending preserve payroll

**Source test:** `depth-edge-cases.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-09: separate player and position columns sort both ways and salary sorting follows each year

**Source test:** `depth-edge-cases.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-10: full 25-player roster supports sorting, filtering, editing and persistence

**Source test:** `depth-gap-fixes.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-11: copying the current plan preserves UFA planning assignments and disabled cap state

**Source test:** `depth-planning.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-12: future lineup includes unsigned players and pool moves keep cap room unchanged

**Source test:** `depth-planning.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-13: salary estimates, historical averaging, manual overrides and filtering survive save

**Source test:** `depth-planning.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep both identity columns sticky on larger screens and only a bounded player-name column sticky on phones.

**Acceptance:** Player names remain visible while scrolling across seasons. Reach all season headers and edit controls with normal touch/scroll; execute the full named business assertions, save, reload, and verify the real roster/payroll is unchanged. No forced clicks or obscured controls.

## MF-14: MOB-01 dashboard and chat fit 320px without hiding composer

**Source test:** `mobile-experience.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Stack Chat on phones and provide a channel-list toggle; allow the composer and channel title to shrink.

**Acceptance:** At 320/390/430px, channel selection, message entry and Send stay inside the viewport, without page-wide horizontal scrolling; closing/reopening Channels preserves the selected thread.

## MF-15: CHAT-01 X-02 rapid repeated send cannot persist duplicate message

**Source test:** `mobile-experience.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Lock in-flight sends and persist a channel/user-scoped idempotent message ID.

**Acceptance:** Rapid tap/Enter submits once; concurrent same-ID requests return one authoritative ID; retry after committed response loss creates no duplicate; failed sends preserve the draft; a new completed intent can intentionally repeat text.

## MF-16: DASH-03 RES-01 failed league widget load is distinguishable from empty data

**Source test:** `dashboard-recovery.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Distinguish load failure from an empty league list and provide an in-place Retry button.

**Acceptance:** A 503 produces a visible named error; other widgets remain usable; Retry restores current league links once, without reload; successful empty data shows an empty state.

## MF-17: A11Y-01 chat send control has meaningful accessible name

**Source test:** `dashboard-recovery.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Name Send message and Notifications, retaining unread/busy/expanded state.

**Acceptance:** Both emulated accessibility trees identify the action; unread counts augment Notifications, and Send exposes disabled/busy state. Verify VoiceOver/TalkBack separately on real phones.

## MF-18: A11Y-01 notification control has meaningful accessible name

**Source test:** `dashboard-recovery.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Name Send message and Notifications, retaining unread/busy/expanded state.

**Acceptance:** Both emulated accessibility trees identify the action; unread counts augment Notifications, and Send exposes disabled/busy state. Verify VoiceOver/TalkBack separately on real phones.

## MF-19: H2H-29 h2h-categories scored elimination progression

**Source test:** `h2h-lifecycle.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending

**Fix:** Use the season start year consistently for generated and queried matchups; retain explicit labels.

**Acceptance:** The final is immediately returned after simulation in both H2H formats; explicit historical season remains queryable; winner, bracket advancement and trophy/history reconcile; no data migration or cross-season mixing.

## MF-20: H2H-29 h2h-points scored elimination progression

**Source test:** `h2h-lifecycle.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending

**Fix:** Use the season start year consistently for generated and queried matchups; retain explicit labels.

**Acceptance:** The final is immediately returned after simulation in both H2H formats; explicit historical season remains queryable; winner, bracket advancement and trophy/history reconcile; no data migration or cross-season mixing.

## MF-21: H2H-30 h2h-categories championship history trophy consistency

**Source test:** `h2h-lifecycle.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending

**Fix:** Use the season start year consistently for generated and queried matchups; retain explicit labels.

**Acceptance:** The final is immediately returned after simulation in both H2H formats; explicit historical season remains queryable; winner, bracket advancement and trophy/history reconcile; no data migration or cross-season mixing.

## MF-22: H2H-30 h2h-points championship history trophy consistency

**Source test:** `h2h-lifecycle.spec.ts` · **Affected:** Android Chromium
**Status:** Implemented; verification pending

**Fix:** Use the season start year consistently for generated and queried matchups; retain explicit labels.

**Acceptance:** The final is immediately returned after simulation in both H2H formats; explicit historical season remains queryable; winner, bracket advancement and trophy/history reconcile; no data migration or cross-season mixing.

## MF-23: direct IR drafting is salary exempt and activation is blocked in Strict mode

**Source test:** `draft-salary.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented draft changes; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Publish authoritative payroll before eligibility batches, abort superseded refreshes, and bound player-list rendering; inspect the exact roster UI failure independently.

**Acceptance:** Roster totals and slot controls appear without waiting for candidate checks; successful move/trade converges to authoritative payroll and occupancy; delayed old responses cannot overwrite new draft state; save/reload preserves ownership and valid dual-position assignments. Two concurrent rooms remain responsive without an OOM kill.

## MF-24: strict salary feasibility rejects illegal API picks without mutation and shows team totals

**Source test:** `draft-salary.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented draft changes; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Publish authoritative payroll before eligibility batches, abort superseded refreshes, and bound player-list rendering; inspect the exact roster UI failure independently.

**Acceptance:** Roster totals and slot controls appear without waiting for candidate checks; successful move/trade converges to authoritative payroll and occupancy; delayed old responses cannot overwrite new draft state; save/reload preserves ownership and valid dual-position assignments. Two concurrent rooms remain responsive without an OOM kill.

## MF-25: regular roster UI dual-position swap saves selected slots and survives reload

**Source test:** `dynamic-positions.spec.ts` · **Affected:** iPhone WebKit
**Status:** Needs focused triage
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Publish authoritative payroll before eligibility batches, abort superseded refreshes, and bound player-list rendering; inspect the exact roster UI failure independently.

**Acceptance:** Roster totals and slot controls appear without waiting for candidate checks; successful move/trade converges to authoritative payroll and occupancy; delayed old responses cannot overwrite new draft state; save/reload preserves ownership and valid dual-position assignments. Two concurrent rooms remain responsive without an OOM kill.

## MF-26: U01 real trade builder uses configured 40 percent maximum

**Source test:** `salary-ui.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Implemented; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Constrain Trade Builder to phone width, keep it above bottom navigation, and permit inner scrolling.

**Acceptance:** At 320/390/430px, normal tapping reaches Retain salary and its slider; configured 40% is the exposed/enforced maximum; disabled retention stays disabled; no clipping or forced clicks.

## MF-27: switching league and active season never reuses another calendar draft

**Source test:** `scheduler.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Needs focused triage
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Scope mobile picker actions and await menu transitions; inspect delayed-response behavior with the current helper.

**Acceptance:** Switch A→B while A response is held; after releasing A, only B league/season/draft data renders. Cancellation preserves the original selection and unsaved state; back/reload retains the intended context.

## MF-28: draft LW to C updates occupancy, persists on reload and preserves payroll

**Source test:** `dynamic-positions.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented draft changes; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Publish authoritative payroll before eligibility batches, abort superseded refreshes, and bound player-list rendering; inspect the exact roster UI failure independently.

**Acceptance:** Roster totals and slot controls appear without waiting for candidate checks; successful move/trade converges to authoritative payroll and occupancy; delayed old responses cannot overwrite new draft state; save/reload preserves ownership and valid dual-position assignments. Two concurrent rooms remain responsive without an OOM kill.

## MF-29: GAP delayed league response cannot overwrite new selection /league-history

**Source test:** `history-gaps.spec.ts` · **Affected:** iPhone WebKit
**Status:** Needs focused triage
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Scope mobile picker actions and await menu transitions; inspect delayed-response behavior with the current helper.

**Acceptance:** Switch A→B while A response is held; after releasing A, only B league/season/draft data renders. Cancellation preserves the original selection and unsaved state; back/reload retains the intended context.

## MF-30: GAP delayed league response cannot overwrite new selection /trophy-room

**Source test:** `history-gaps.spec.ts` · **Affected:** iPhone WebKit
**Status:** Needs focused triage
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Scope mobile picker actions and await menu transitions; inspect delayed-response behavior with the current helper.

**Acceptance:** Switch A→B while A response is held; after releasing A, only B league/season/draft data renders. Cancellation preserves the original selection and unsaved state; back/reload retains the intended context.

## MF-31: commissioner can configure the requested regular season and playoff tree

**Source test:** `league-schedule.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented context fix; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Retain the explicitly selected league even when it is absent from a capped/stale membership list. Return recent leagues first so newly created leagues remain discoverable.

**Acceptance:** Omit selected B from the list while A remains listed: every settings write must target B, A stays unchanged, and reload retains B. Beyond 200 memberships, a newly created league remains listed. All valid week options are reachable and saved regular-season / eight-team three-round settings survive reload. Invalid overlap/order remains rejected.

## MF-32: ROS-31 correct player details opens and closes

**Source test:** `roster-gaps.spec.ts` · **Affected:** iPhone WebKit
**Status:** Needs focused triage
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Scope player-card assertions to the player dialog so install guidance cannot be mistaken for a card; fix dismissal only if the card itself persists.

**Acceptance:** Open the named player, close using the visible Close control and Escape, confirm that specific player dialog closes, return focus to its trigger, and preserve unrelated install guidance and roster/contract state.

## MF-33: Rotisserie supports saving an eight-team three-round elimination bracket

**Source test:** `rotisserie-playoffs.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented context fix; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Retain the explicitly selected league even when it is absent from a capped/stale membership list. Return recent leagues first so newly created leagues remain discoverable.

**Acceptance:** Omit selected B from the list while A remains listed: every settings write must target B, A stays unchanged, and reload retains B. Beyond 200 memberships, a newly created league remains listed. All valid week options are reachable and saved regular-season / eight-team three-round settings survive reload. Invalid overlap/order remains rejected.

## MF-34: salary page remains usable on a narrow viewport and player drilldown opens

**Source test:** `salary-page-gaps.spec.ts` · **Affected:** iPhone WebKit
**Status:** Needs focused triage
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Scope player-card assertions to the player dialog so install guidance cannot be mistaken for a card; fix dismissal only if the card itself persists.

**Acceptance:** Open the named player, close using the visible Close control and Escape, confirm that specific player dialog closes, return focus to its trigger, and preserve unrelated install guidance and roster/contract state.

## MF-35: C04 manager cannot update league or generate schedules using explicit fixtures

**Source test:** `settings-confirmation.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Test helper
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Assert the current administrator denial contract while retaining 403 and unchanged-data checks.

**Acceptance:** Manager and outsider requests receive 403; persisted settings stay identical and no schedule is created; UI denies the action. Match semantic role denial rather than obsolete commissioner-only wording.

## MF-36: C04 outsider cannot update league or generate schedules using explicit fixtures

**Source test:** `settings-confirmation.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Test helper
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Assert the current administrator denial contract while retaining 403 and unchanged-data checks.

**Acceptance:** Manager and outsider requests receive 403; persisted settings stay identical and no schedule is created; UI denies the action. Match semantic role denial rather than obsolete commissioner-only wording.

## MF-37: active draft trade updates two managers rooms and survives reconnect

**Source test:** `draft-sweep.spec.ts` · **Affected:** iPhone WebKit
**Status:** Implemented draft changes; verification pending
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Publish authoritative payroll before eligibility batches, abort superseded refreshes, and bound player-list rendering; inspect the exact roster UI failure independently.

**Acceptance:** Roster totals and slot controls appear without waiting for candidate checks; successful move/trade converges to authoritative payroll and occupancy; delayed old responses cannot overwrite new draft state; save/reload preserves ownership and valid dual-position assignments. Two concurrent rooms remain responsive without an OOM kill.

## MF-38: Disabled playoffs preserve a full-season schedule with no playoff matchups

**Source test:** `outstanding-roto.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Product contract unresolved
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep Roto numeric tests separate from unsupported opponent-generation requests; specify and implement a supported season/bracket generation route before clearing.

**Acceptance:** Disabled playoffs yield a full regular season and zero playoff games through the supported workflow. Enabled eight-team elimination advances 8→4→2→champion from real scored weeks with one champion. A projected bracket alone is insufficient; do not convert HTTP 400 into a pass.

## MF-39: Generated elimination playoffs advance 8 to 4 to 2 to champion through scored weeks

**Source test:** `outstanding-roto.spec.ts` · **Affected:** Android Chromium, iPhone WebKit
**Status:** Product contract unresolved
**Automated verification:** android-chrome-emulated: passed; iphone-webkit-emulated: passed. Final frozen-runtime run; manual criteria remain subject to the documented gaps.

**Fix:** Keep Roto numeric tests separate from unsupported opponent-generation requests; specify and implement a supported season/bracket generation route before clearing.

**Acceptance:** Disabled playoffs yield a full regular season and zero playoff games through the supported workflow. Enabled eight-team elimination advances 8→4→2→champion from real scored weeks with one champion. A projected bracket alone is insufficient; do not convert HTTP 400 into a pass.

## Public behavior and API contracts

- Chat accepts optional `client_message_id`, a string of 1–128 characters. The key is scoped to channel and authenticated user. Retrying the same ID/content returns the same stored message; conflicting content returns 409, invalid IDs return 400, and channel authorization still runs first. Clients omitting the field retain ordinary append behavior. Notification/moderation fan-out runs only for the new insert.
- Matchup season resolution honors an explicit `season` label. Otherwise `current_season_year` denotes the starting year: 2026 resolves to `2026-27`. Existing records are not rewritten.
- The draft player list initially renders 50 matching candidates. Show more adds 50; changing the search or filters resets the visible page. Candidates beyond the first page remain searchable and selectable.
- Draft payroll/slot totals publish immediately from roster-status, independently of candidate eligibility batches. Superseded refreshes are aborted and cannot commit old context.

## Release verification

Run focused browser regressions on the rebuilt fixed source, then the related business and authorization checks. Capture test counts, image/source identity, failures and resource conditions. Never describe helper corrections as app fixes, projected brackets as completed seasons, or physical-device/screen-reader criteria as passed through emulation.

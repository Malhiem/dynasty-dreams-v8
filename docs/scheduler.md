# League Administration scheduler

The Schedules tab edits a season-scoped scoring calendar. `GET/PUT
/api/leagues/{league_id}/scheduler/{season}` loads and saves that calendar in
`leagues.scheduler_calendars.<season>`. The season is the league's
`current_season_year`, falling back to the season start date's year for legacy
leagues. Save rejects stale season links with HTTP 409. Loading an unsaved
calendar shows defaults derived from the selected league rather than a fixed
2025 season and 12 teams. Reset restores those defaults in the draft; Save
persists them.

Authentication precedes lookup. League members may read; commissioner,
co-commissioners, and league `admin_ids` may save. The HTTP authentication layer
also blocks writes from read-only impersonation sessions. Saving requires a
Head-to-Head format. The current league season, format, and team count are
checked again in the Mongo update filter. Writes record an audit entry.

Periods have inclusive date-only boundaries. Generation uses UTC date
arithmetic, includes a single-day season and the final day, honors the chosen
weekly start day with an initial partial period, merges the first N periods,
and advances monthly periods by calendar months. Configured ranges are limited
to 366 days. Editing rejects reversed dates, out-of-range dates, and overlaps
within or between sections. Gaps are visible warnings. Empty period lists are
allowed and shown explicitly. Brackets need a nonblank name, a team count
within league capacity, enough elimination rounds, and at least one playoff
period per round. Opponents must be between 1 and team count minus 1.

The calendar is a **persisted plan**, not the live matchup table. Saving does
not generate opponents, replace existing matches, apply bracket results, or
change the scoring engine's time windows. Those flows still use League Setup's
existing configuration and `/api/matchups/generate-schedule`. The old scheduler
strategy dropdown had no effect; it was removed instead of persisting a false
promise. Division/conference mixes remain in League Structure. Connecting
arbitrary edited periods to live scoring, versioning concurrent administrator
edits, and selecting historical saved seasons are remaining product gaps.

## Focused validation

- Frontend: `yarn test --watch=false --runInBand calendar.test.js`; `yarn lint`.
- Backend: `tests/test_scheduler_calendar.py`, `tests/test_matchups_router.py`.
  Set `MONGO_URL`, `DB_NAME`, `PYTHONPATH`, and `REACT_APP_BACKEND_URL` explicitly
  to an isolated disposable Mongo/API environment before invoking pytest.
- Browser/API: `scheduler.spec.ts` and `scheduler-generation.spec.ts` with the
  existing Playwright config, inside a distinct disposable Compose network at
  `http://web`, with `H2H_ISOLATED=1`. Use a writable `--output` directory outside
  the read-only source mount.

Coverage includes save/reload, league/season isolation, stale-season rejection,
permissions, invalid payloads and unchanged persisted state, failed-save draft
retention, loading/retry/empty states, calendar generation and editing, bracket
creation/removal/reset, keyboard dialog invocation/Escape/focus return, and a
390px mobile viewport. Live generation tests cover odd-team byes, multiple
opponents, unique pairings, equal full-cycle totals, placeholders, repeated
generation, and failure preservation. Generated-matchup reads must retain Mongo
ObjectIds until live scoring captures competition snapshots; serialization
comes afterward for list/current-week/results endpoints.

No native mobile implementation or screen-reader audit is covered by these web
tests. Tests do not authorize running against shared preview data.

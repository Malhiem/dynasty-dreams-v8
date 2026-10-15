# Combined opponent scheduler

League Administration → Schedules → **Opponent Schedule** is the live opponent
scheduler. It combines weekly capacity and season opponent requirements in one
constraint model. The existing calendar editor remains a separate date/bracket
planning surface; arbitrary edited calendar periods do not change live scoring
windows. Live schedules use League Setup's season start/end, scoring-period
length and playoff configuration.

## Mandatory rules

- Exactly K distinct opponents per team per scoring period, for W periods.
- No self-matchups and no repeated team pair within one period.
- Division/conference/all-opponent requirements support Minimum, Exact and
  Maximum, either as a season total **per team** or games **per opponent**.
- Conference totals include division games. “Same conference, other division”
  is an explicit disjoint group used by legacy settings.
- Completed, in-progress, other non-scheduled and explicitly `locked` /
  `is_locked` regular-season games are fixed, including home/away orientation.
- Calendar capacity and playoff start must accommodate the requested season.

Every actual team and synthetic open slot must have a division and conference
before group rules can be used. A division cannot span conferences. Standard
all-opponent schedules can use open-slot placeholders without structure.

The scheduler never clamps requested opponents, silently drops requirements,
or overflows games into an already-full week. Odd team counts are supported
when N × K is even, such as seven teams playing twice weekly. Automatic byes
are not enabled: an odd N × K returns a specific capacity conflict.

Legacy `schedule_config` values migrate as **exact counts per opponent** for
division / other conference teams / outside conference. A legacy configuration
that underfills or overfills W × K is now rejected. Changing that legacy mix
clears the applied combined rule defaults; the generated schedule remains
unchanged until the administrator applies a new preview. The regular-season
form synchronizes both old matchup-count fields, preventing one entry point
from overriding the other.

## Generation and preferences

`services/combined_scheduler.py` uses OR-Tools CP-SAT, pinned to 9.12.4544 for
compatibility with the repository's protobuf 5.29.x dependency. Boolean
variables represent unordered team pairs within periods. Weekly degrees,
season group totals, per-opponent limits and locked games are solved together.

Prechecks report obvious capacity, structure and lock conflicts. Solver
`INFEASIBLE` is a proof that the constraints cannot fit together. `UNKNOWN`
returns `timeout`, explicitly stating that infeasibility has **not** been
proven. No candidate can be applied in either case. An independent validator
recounts weekly appearances, unique pairs, every requested requirement and
locked-game orientation before storing or activating a candidate.

After finding a valid arrangement, bounded preference optimization reduces
maximum pair repetition, nearby rematches and clustering of group games into
one half of the season. Euler orientation provides balanced home/away totals
when no fixed home/away results prevent it; further bounded optimization favors
alternating home designations for repeated pairs. Preferences never weaken
mandatory constraints and global preference optimality is not guaranteed.

Interactive limits are 100 teams, 52 periods, 200,000 pair-period variables and
10,000 regular-season games. Larger configurations return a size-limit result,
not an infeasibility claim. Each process runs at most two solvers concurrently,
with a one-second queue wait, 12 seconds for feasibility, up to four seconds for
opponent preferences and one second for home/away preferences. Worker/resource
limits should also be configured for the deployment's CPU budget.

## API and activation

All league-scoped endpoints authenticate before lookup and require the league
commissioner, co-commissioner or an explicit league administrator. Platform
admin status alone does not grant mutation access. Read-only impersonation is
blocked by the global authentication layer.

- `GET /api/leagues/{id}/schedule/rules`: canonical defaults, season, version,
  protected-game count and transaction capability.
- `POST /api/leagues/{id}/schedule/check`: cheap feasibility checks. A `ready`
  result still requires a complete validated preview.
- `POST /api/leagues/{id}/schedule/preview`: solves the settings and returns
  weekly matchups, requested/achieved totals for every team and a preview ID.
- `POST /api/leagues/{id}/schedule/apply`: accepts only that preview ID;
  administrators cannot submit arbitrary unvalidated matchup rows.

Example settings:

```json
{
  "weeks": 20,
  "games_per_week": 2,
  "seed": 1,
  "rules": [
    {"group":"division","scope":"per_opponent","comparison":"exact","value":2},
    {"group":"conference_other","scope":"per_opponent","comparison":"exact","value":1},
    {"group":"outside_conference","scope":"per_opponent","comparison":"exact","value":2}
  ]
}
```

For 24 teams in four six-team divisions and two conferences, this produces 40
games per team and 480 league matchups: 10 division games, six other-conference
team games and 24 outside-conference games per team. Each team has two distinct
opponents every period.

Previews expire after 30 minutes and have a TTL index. A fingerprint covers
season, relevant league settings, team identity/structure and existing game
results. Applying rejects changed or expired previews, revalidates in a Mongo
transaction, preserves protected results, replaces only the current season's
unprotected rows, records an immutable `schedule_versions` snapshot, advances
the league version and records an audit event. Existing historical seasons are
not deleted. A started playoff bracket is retained as a whole; unstarted
brackets are regenerated using existing League Setup settings.

Transactions detect competing Apply requests and conflicting changes to
existing league/team/result documents. A failed write rolls back deletions,
inserts, version updates and audit changes. An already-applied preview cannot
be reused. The old `/api/matchups/generate-schedule` entry point now delegates to
this same engine and activation path. The public wizard `/api/matchups/preview`
uses the same weekly engine without writing live games.

## Runtime prerequisite and isolated tests

**Applying requires MongoDB transactions: a replica set or sharded cluster.**
Standalone Mongo can generate previews but Apply returns 503 without changing
the existing schedule. Do not silently fall back to delete-then-insert, and do
not convert shared preview or production Mongo automatically.

For a fresh, disposable local test stack:

```sh
podman-compose -p dynasty-combined-e2e -f docker-compose.h2h.yml -f docker-compose.scheduler.yml up -d --build mongo backend web
podman-compose -p dynasty-combined-e2e -f docker-compose.h2h.yml -f docker-compose.scheduler.yml run --rm e2e bash -lc 'npm --prefix e2e run typecheck && npx playwright test --config=e2e/playwright.config.ts combined-scheduler.spec.ts scheduler-generation.spec.ts scheduler.spec.ts --trace=on'
```

The overlay initializes a private single-node replica set for tests and waits
for a writable primary before starting the API. It is not a production replica
set deployment guide. Browser tests must use `http://web` in the distinct
Compose network and `H2H_ISOLATED=1`. Backend pytest must receive explicit
disposable `MONGO_URL` and `DB_NAME`; never use ambient/shared configuration.

Focused backend files: `test_combined_scheduler.py`,
`test_combined_schedule_store.py`, `test_scheduler_calendar.py`,
`test_matchups_router.py`. HTTP regressions additionally cover the legacy
preview/generation contracts and the required security suites. Tests include
24-team rules, aggregate/inclusive conference counts, impossible constraints,
timeout classification, locks, atomic rollback, concurrent apply, stale teams /
settings / season / results, historical games, protected playoffs, version
history, permissions, desktop/mobile review and persistence.

Remaining boundaries: no automatic byes, historical-version restore UI,
administrator-editable individual opponent rows, or native Expo changes.
Calendar plan edits and bracket plans remain distinct from live scoring and
League Setup's actual playoff configuration. The UI identifies this distinction.

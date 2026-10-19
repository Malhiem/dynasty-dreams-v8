# Local E2E tests

This stack runs MongoDB, the API, and the React app in containers. Nginx serves the app and reverse-proxies `/api` to the API, so Playwright exercises same-origin cookie authentication.

## Prerequisites

Install Podman and `podman-compose`. The wrapper defaults to `podman-compose`; set `PODMAN_COMPOSE_CMD` if a compatible provider is preferred.

## Run

```sh
./e2e/run.sh
```

The script uses Compose project `dynasty-dreams-e2e` by default, removes its volumes before startup, runs the `e2e` service, then removes the stack and volumes. Override `E2E_PROJECT_NAME` to run an isolated stack.

## Playwright UI mode

Use UI mode to choose and run tests from Playwright's browser interface. Unlike `./e2e/run.sh`, these commands leave the stack running while the UI is open.

```sh
P=dynasty-dreams-e2e
C="podman-compose -p $P -f docker-compose.e2e.yml"

# Optional: begin with an empty E2E database.
$C down --volumes --remove-orphans

# Start the services Playwright needs.
$C up --detach --build mongo backend web

# Serve Playwright UI locally, then open http://127.0.0.1:9323.
$C run --rm --build -p 127.0.0.1:9323:9323 \
  e2e npx playwright test --config=e2e/playwright.config.ts \
  --ui --ui-host=0.0.0.0 --ui-port=9323
```

The browser tests run inside the Compose network, so their base URL is `http://web`; do not change it to `localhost`. The suite is TypeScript; run `cd e2e && npm run typecheck` to validate it. When finished, stop the UI with `Ctrl+C`, then remove the stack and its test data:

```sh
$C down --volumes --remove-orphans
```

The initial test logs in with the test-only admin account configured in `docker-compose.e2e.yml`. `E2E_MODE=true` disables background workers and marks payment endpoints unavailable with HTTP 503. It must never be used outside the E2E stack.

For browser debugging, the app is published only on `127.0.0.1:3000` while the stack is running.

## League Setup / Rotisserie acceptance coverage

`tests/league-scoring.spec.ts` exercises all five League Setup scoring buttons,
their H2H restriction message, and persistence through the league API. It also
checks the real Rotisserie endpoint with 12 uniquely ranked teams, each with two
contributing players: goals alone, assists alone, then both categories. Each
category must award 12 through 1 points; combined totals must sum those awards
and sort the leader first. Separate tests cover category-rank columns, playoff
availability in setup/standings/the bracket API, and season-completion champion.

The typed fixture uses the existing authenticated league creation API and the
`mongodb` dev dependency to seed only `mongo/dynasty_dreams_e2e` inside Compose.
It refuses to run unless `E2E_BASE_URL=http://web`. Every test creates a unique
league; only that new league's auto-created team is replaced. Fixture data stays
available for debugging in the disposable volume.

Weekly allocation is explicitly `test.fixme`: the Rotisserie endpoint currently
has no period parameter or historical team-stat source. The numeric test proves
current roster aggregate calculations, **not** season-long ownership history or
weekly accumulation. It does not mock missing behavior or treat it as passing.
Tied-category policy and rate-stat aggregation are outside this focused fixture.
The acceptance tests intentionally fail while the corresponding functionality
is missing; do not convert observed failures to expected failures.

To run through the installed provider and retain failure evidence (from the repo
root in WSL):

```sh
podman compose -p dynasty-dreams-e2e -f docker-compose.e2e.yml up -d --build mongo backend web
podman compose -p dynasty-dreams-e2e -f docker-compose.e2e.yml build e2e
RUN=roto-e2e-$(date +%s)
podman compose -p dynasty-dreams-e2e -f docker-compose.e2e.yml run --name "$RUN" \
  -e PLAYWRIGHT_JSON_OUTPUT_FILE=/work/results.json e2e bash -lc \
  'npm --prefix e2e run typecheck && npx playwright test --config=e2e/playwright.config.ts league-scoring.spec.ts --trace=on --reporter=list,json'

# Run these even when Playwright exits 1. Keep the runner and volume until reviewed.
mkdir -p /tmp/"$RUN"
podman cp "$RUN":/work/results.json /tmp/"$RUN"/results.json
podman cp "$RUN":/work/e2e/test-results /tmp/"$RUN"/test-results
podman logs "$RUN" > /tmp/"$RUN"/runner.log 2>&1
```

Omit `league-scoring.spec.ts` to include the existing login, invite, and schedule
regressions. Avoid `./e2e/run.sh` while investigating failures: it removes volumes.

## Optional Rotisserie playoffs (revised acceptance criteria)

`rotisserie-playoffs.spec.ts` replaces the obsolete unconditional no-playoffs test.
It checks the main toggle, available condensed format, and saving/reloading an
eight-team elimination bracket with projected matchup counts 4/2/1. Three explicit
blocked scenarios cover disabled-season scheduling, condensed scoring/bonuses,
and actual scored elimination progression/champion declaration. Projection alone
does not satisfy actual progression. Fixtures set Rotisserie through the API;
these tests do not demonstrate that the scoring-format UI saves successfully.
Run with the documented evidence-preserving Compose command, substituting
`rotisserie-playoffs.spec.ts` for the spec filter.


### Mobile recovery and worker regression coverage

The draft paging fixture keeps strict salary rules enabled and seeds a known feasible completion before draft creation. Its normal clicks, actual pick, reload, and negative salary checks run at default, 320px, 430px and landscape sizes. `draft-write-recovery.spec.ts` injects failures before and after commit and checks authoritative reconciliation without duplicate advancement. `mobile-calendar-style.spec.ts` records actual computed contrast for native fields in both themes and enlarged text. These are browser checks, not physical-device or screen-reader certification.

`mobile-worker-browser.spec.ts` requires `MOBILE_WORKER_BROWSER_ISOLATED=1` and a secure test origin, and otherwise records an explicit skip. In the disposable `http://web` Compose network, the dedicated Chromium harness supplies `--unsafely-treat-insecure-origin-as-secure=http://web` only for that origin. Never use that flag for production browsing. Keep one worker and avoid overlapping mutating suites. The worker tests verify private cache isolation and current HTML/offline-asset handling; they do not represent actual home-screen installation on Safari/Android.

From the repository root, `node frontend/scripts/service-worker.test.cjs` runs the worker-source cache/network policy regressions without a database. The bounded fixture transaction worker remains test-only and is not evidence of production worker startup.


### Controlled service-worker browser checks

Inside the disposable E2E runner/Compose network, with `E2E_BASE_URL=http://web H2H_ISOLATED=1`, run `npx playwright test --config=playwright.worker.config.ts`. This dedicated configuration starts a loopback-only HTTP proxy inside the runner, giving Chromium a genuinely trustworthy localhost origin for service-worker APIs. Fixture/auth API contexts still use `http://web`; only browser cookies are scoped to localhost. No host ports, production settings or browser security overrides are required. The normal suite leaves these two lifecycle checks explicitly skipped unless the dedicated harness is selected. This is controlled Chromium coverage, not physical Safari installation or a full two-deployment asset migration test.

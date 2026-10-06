# H2H acceptance suite

The 31 original cases are identified by `H2H-01` through `H2H-31`. `H2H-32` covers cross-format isolation and `H2H-33` observes the unresolved tied-playoff rule. `support/h2h-cases.ts` contains explicit criteria attached automatically to every variant. Specs are split into core scoring, lifecycle, and browser UI. The delivered acceptance matrix contains the latest results and exact evidence links.

## Run against an isolated stack

From the existing Dynasty Dreams repository in WSL, with Podman Compose installed:

```sh
podman compose -p dynasty-h2h-review -f docker-compose.h2h.yml build backend web e2e
podman compose -p dynasty-h2h-review -f docker-compose.h2h.yml up -d mongo backend web
podman compose -p dynasty-h2h-review -f docker-compose.h2h.yml run --name h2h-review-run e2e bash -lc 'npm --prefix e2e run typecheck && npx playwright test --config=e2e/playwright.config.ts h2h- --trace=on --reporter=list,json'
```

The test command currently exits nonzero because acceptance defects are intentionally asserted. Run these evidence commands even after a failure; do not use the normal `run.sh` cleanup wrapper:

```sh
mkdir -p h2h-evidence
podman cp h2h-review-run:/work/results.json h2h-evidence/results.json
podman cp h2h-review-run:/work/e2e/test-results h2h-evidence/test-results
podman logs h2h-review-run > h2h-evidence/runner.log 2>&1
```

Use a unique Compose project and runner name for an independent run. The supplied Compose file has no host web port, declares its own Mongo volume, and sets `H2H_ISOLATED=1` plus `E2E_BASE_URL=http://web`. The fixture refuses other environments. Source inputs are limited to newly created leagues and their players. No production URLs, global data resets, source scoring patches, or outbound stat provider are used.

## Interpretation

The browser tests cover League Setup and matchup week selection. Other tests use Playwright's authenticated HTTP client against the actual backend and database. `simulate-week` is the current commissioner simulation endpoint; it is not proof of automatic scheduled finalization. Tests intentionally fail when that endpoint uses season values, inactive roster stats, or points for Categories. Missing H2H category ledgers and recompute are explicit skipped/NOT IMPLEMENTED cases, with probe evidence where available. Automatic closure is blocked by existing E2E worker disablement. Never count skipped variants as passes.

The ranking comparator currently uses wins, PF+live points, then team ID. No-playoff completion currently returns no champion without an existing award. A tied Categories playoff leaves the next round TBD. The suite records these facts without inventing a champion or tie-advancement policy.

Fixtures use the valid creation enum `head_to_head`, then the existing update API for `h2h-points`/`h2h-categories`; the UI persistence test independently starts at Rotisserie and clicks the requested H2H format. Four regular weeks meet the current API minimum; playoffs use weeks 5–7. Inputs deliberately reverse initial ranking for qualification and distinguish Points winners from category-majority winners.

The existing test-only payment/startup adapters are required by the inherited container architecture. They are preserved, not authored by this task. This patch adds only E2E tests, documentation and isolated Compose configuration; it does not repair application logic.

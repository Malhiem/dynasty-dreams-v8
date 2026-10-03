# E2E Test Guide

## Scope

This directory owns Playwright tests executed inside the Podman Compose network. Tests target `http://web`, never `localhost`. Preserve the serial suite configuration: tests share the seeded E2E admin and mutate one isolated database.

## Structure

- `tests/` contains concise TypeScript scenarios and their business assertions.
- `pages/<page>/` contains one page object plus separate `*.selectors.ts` and `*.actions.ts` files. Page objects compose actions; selectors contain stable locator contracts only.
- `support/` is for typed API fixtures or cross-page workflows. Do not put API setup into page objects.

## Practices

- Use TypeScript and run `npm run typecheck` after structural changes.
- Prefer `getByRole` and `getByLabel` when they uniquely describe user-visible controls. Use `getByTestId` for stable, deliberate test contracts. Never use CSS classes, positional locators, `nth()`, or `waitForTimeout()` as test synchronization.
- Keep locators scoped to their page object. Add a frontend test ID only when accessible locators are ambiguous or unstable.
- Keep assertions visible in specs. Page actions should navigate or perform user interactions and return meaningful data only when needed by the scenario.
- Make generated user names and league names unique. Use API helpers only for setup that would make the UI scenario unnecessarily slow; close contexts they create.

## Commands

```sh
npm run typecheck
./e2e/run.sh
```

For Playwright UI mode and the persistent-stack workflow, follow `e2e/README.md`. The default wrapper removes E2E volumes before and after a run.

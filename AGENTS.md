# Dynasty Dreams V7 Agent Guide

## Mission and scope

Dynasty Dreams is a Mongo-backed fantasy-sports product with a FastAPI/Socket.IO API, React web client, Expo mobile client, and containerized Playwright E2E suite. Make the smallest focused change that satisfies the request. Inspect the affected code, its callers, and relevant tests before editing.

Keep code modular, flat, and descriptive. Prefer existing patterns and a single source of truth over new frameworks, duplicate state, or speculative abstractions. Document public or non-obvious contracts and consequential design decisions; do not add boilerplate or line-by-line comments.

## Repository map

- `backend/` — Python FastAPI API. Keep HTTP routes in `routes/`, business logic in `services/`, shared policy in `utils/`, and tests in `backend/tests/`. Avoid adding feature logic to `server.py`, which composes the application.
- `frontend/` — React 19 SPA using CRA/CRACO and Yarn 1. Preserve the established page family (`src/pages/` or `src/lovable/pages/`) and colocated component patterns.
- `mobile/` — Separate Expo/React Native client. Do not treat it as the web client.
- `e2e/` and `docker-compose.e2e.yml` — Playwright browser tests run inside the Compose network.
- `SECURITY.md` — source of truth for endpoint, Socket.IO, admin, and incident-handling security requirements. Read it before backend/API or socket work.
- `e2e/README.md` — operational guide for clean-stack and Playwright UI E2E runs.

## Security and data safety

- For league-scoped reads, authenticate first, load the resource second, and verify membership third. Use the established authorization helpers.
- Socket.IO access is deny-by-default: require JWT authentication and explicitly allow any new rooms/events.
- Backend pytest setup can clean Mongo data. **Never run `backend` tests against ambient or shared configuration.** First provide an explicitly isolated, disposable `MONGO_URL` and `DB_NAME`; use Compose to start that isolated dependency when needed.
- Do not use `E2E_MODE=true` outside the E2E Compose stack. It intentionally disables workers and payment behavior.
- Never commit secrets, local environment files, generated artifacts, IDE state, or agent temporary files.
`frontend` uses Yarn 1. Its lint command is a limited `.tsx` size-ratchet check, not a full correctness/type check. There is no unified root validation command; do not invent canonical formatter, type-check, or mobile-test commands without project configuration.

For browser E2E, Playwright runs in the Compose network and reaches the application at `http://web`, not `localhost`. Use `e2e/README.md` for the persistent-stack and Playwright UI workflow. The default E2E runner removes volumes before and after a run.

## Change discipline

- Test observable behavior and business rules, not trivial implementation details.
- Keep unrelated local changes intact. Do not revert, reformat, or overwrite work you did not create.
- Keep frontend source files within the repository's established size limits; split new complexity into focused components or modules.
- Update the relevant documentation when public behavior, setup, security posture, or operational workflow changes.

# Mobile web cache and update contract

The service worker caches public app assets and an offline HTML shell. Every API request and all mutations use the network; no authenticated league, team, chat or account response is served from a shared URL-keyed worker cache. Offline shell availability does not promise offline private data or queued writes.

Navigation checks the network for current HTML before falling back to the offline shell. Hashed static assets can be reused offline. Missing assets return an explicit unavailable response, never HTML disguised as JavaScript. Activation removes legacy Dynasty Dreams API/shell caches and preserves unrelated origin caches. Logout purge messages also remove legacy API cache versions. Registration checks worker updates without the HTTP cache. Existing edits are not discarded by a forced page reload.

Run `node frontend/scripts/service-worker.test.cjs` from the repository root for isolated policy regressions. These tests execute the actual worker source with simulated cache/network events. They do not certify physical-device installation, Safari lifecycle behavior, or deployment headers. Those require the physical-device acceptance matrix.

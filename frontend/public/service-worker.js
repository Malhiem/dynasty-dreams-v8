/* eslint-env serviceworker */
/* global self, caches, fetch, Response */
/**
 * Iter 231av — DynastyDreams service worker.
 *
 * Minimal offline shell built on the plain SW API (no Workbox runtime
 * dependency — keeps the bundle lean and the behaviour transparent).
 *
 * Strategies:
 *   • Cache-first for the static app shell (HTML / JS / CSS / images
 *     produced by the CRA build + the PWA icons + manifest).
 *   • Stale-while-revalidate for **safe** API GETs that are expensive
 *     to refetch on every navigation but tolerate brief staleness:
 *       - /api/matchups/...
 *       - /api/leagues/.../standings
 *       - /api/teams/...
 *       - /api/players?...
 *     The cached copy is returned immediately; in parallel we fire a
 *     network refresh that quietly replaces the cache for the next
 *     visit. Pairs naturally with the pull-to-refresh hook (iter
 *     231at/au): a finger-drag bumps the page's `refreshTick`, which
 *     forces a new request, and SWR keeps the cache warm.
 *   • Network-only for every mutating verb (POST / PUT / PATCH /
 *     DELETE) — we never want to silently re-play a trade proposal
 *     from cache or hand a stale optimistic response to the writer.
 *   • Network-only for `/api/auth/*`, `/api/admin/*`, websockets, and
 *     any request that opts out via `?nocache=1`.
 *
 * Versioning: a new release bumps `SW_VERSION`, which is part of every
 * cache name. The `activate` step deletes any cache whose name doesn't
 * start with the current version so we never serve assets from a
 * stale build.
 */

const SW_VERSION = "v1";
const SHELL_CACHE = `dd-shell-${SW_VERSION}`;
const API_CACHE = `dd-api-${SW_VERSION}`;

// Files that make up the bare-minimum offline shell. CRA hashes JS/CSS
// filenames at build time so we can't pre-list them; instead we cache
// them lazily on first fetch (cache-first below). This list just
// pre-warms the navigations the user is most likely to hit cold.
const SHELL_PRELOAD = [
  "/",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
];

// SWR'd API path prefixes. Order matters: more specific first.
const SWR_PATTERNS = [
  /^\/api\/matchups\//,
  /^\/api\/leagues\/[^/]+\/standings/,
  /^\/api\/leagues\/[^/]+\/teams/,
  /^\/api\/teams\/[^/]+$/,
  /^\/api\/players(\?|$)/,
  /^\/api\/users\/me\/week-at-a-glance/,
];

// API paths that must NEVER be cached (auth state, admin-only data,
// websocket upgrades).
const NEVER_CACHE = [
  /^\/api\/auth\//,
  /^\/api\/admin\//,
  /^\/api\/client-errors/,
  /^\/api\/socket\.io/,
];


self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_PRELOAD).catch(() => undefined))
      .then(() => self.skipWaiting()),
  );
});


self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => !k.endsWith(`-${SW_VERSION}`))
          .map((k) => caches.delete(k)),
      );
      await self.clients.claim();
    })(),
  );
});


function isAppShell(url) {
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith("/api/")) return false;
  // HMR + dev-server live-reload chatter — never cache.
  if (url.pathname.startsWith("/sockjs-node")) return false;
  if (url.pathname.includes("hot-update")) return false;
  return true;
}


function isSwrApi(url) {
  if (!url.pathname.startsWith("/api/")) return false;
  if (NEVER_CACHE.some((re) => re.test(url.pathname))) return false;
  return SWR_PATTERNS.some((re) => re.test(url.pathname + url.search));
}


async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) {
    // Refresh in the background so the next navigation gets the
    // latest build without the user waiting.
    fetch(request)
      .then((res) => res && res.ok && cache.put(request, res.clone()))
      .catch(() => undefined);
    return cached;
  }
  try {
    const res = await fetch(request);
    if (res && res.ok && res.type !== "opaque") {
      cache.put(request, res.clone()).catch(() => undefined);
    }
    return res;
  } catch {
    // Last-ditch: serve the cached "/" navigation so the SPA renders
    // its offline-aware shell instead of the browser's network error
    // page.
    const fallback = await cache.match("/");
    if (fallback) return fallback;
    throw new Error("offline");
  }
}


async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((res) => {
      if (res && res.ok && res.type !== "opaque") {
        cache.put(request, res.clone()).catch(() => undefined);
      }
      return res;
    })
    .catch(() => undefined);
  // If we have a cached copy, return it instantly; the network
  // refresh runs in the background. If we don't, await the network.
  return cached || network || new Response("offline", { status: 503 });
}


self.addEventListener("fetch", (event) => {
  const { request } = event;
  // Network-only for every mutating verb.
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }

  // Bypass cache when the caller explicitly asks for fresh data
  // (handy for the upcoming "force refresh" branch on PTR).
  if (url.searchParams.has("nocache")) return;

  if (isAppShell(url)) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  if (isSwrApi(url)) {
    event.respondWith(staleWhileRevalidate(request, API_CACHE));
    return;
  }
  // Everything else falls through to the network — fine because the
  // app already runs there today.
});


// Listen for `{ type: 'SKIP_WAITING' }` from the page so a user can
// opt into the new SW immediately (the registration helper sends it).
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

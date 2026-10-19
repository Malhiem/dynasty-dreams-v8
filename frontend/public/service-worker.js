/* eslint-env serviceworker */
/* global self, caches, fetch, Response */
// Cache only the public app shell. Authenticated API reads always reauthorize
// on the network; URL-keyed caches cannot distinguish shared-device accounts.
const SW_VERSION = "v2";
const SHELL_CACHE = `dd-shell-${SW_VERSION}`;
const SHELL_PRELOAD = ["/", "/manifest.json", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"];

async function purgePrivateCaches() {
  const keys = await caches.keys();
  await Promise.all(keys.filter(key => key.startsWith("dd-api-")).map(key => caches.delete(key)));
}

self.addEventListener("install", event => {
  event.waitUntil(caches.open(SHELL_CACHE)
    .then(cache => cache.addAll(SHELL_PRELOAD).catch(() => undefined))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    await purgePrivateCaches();
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith("dd-shell-") && key !== SHELL_CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

function unavailable() {
  return new Response("This resource is unavailable offline. Reconnect and retry.", {
    status: 504, headers: {"Content-Type": "text/plain; charset=utf-8"},
  });
}

function keep(event, cache, request, response) {
  if (response?.ok && response.type !== "opaque") {
    event.waitUntil(cache.put(request, response.clone()).catch(() => undefined));
  }
}

async function navigation(event) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(event.request, {cache: "no-cache"});
    keep(event, cache, event.request, response);
    return response;
  } catch {
    return await cache.match(event.request) || await cache.match("/") || unavailable();
  }
}

async function asset(event) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(event.request);
  if (cached) return cached;
  try {
    const response = await fetch(event.request);
    keep(event, cache, event.request, response);
    return response;
  } catch {
    // Returning HTML for a missing JS chunk produces a broken app on update.
    return unavailable();
  }
}

self.addEventListener("fetch", event => {
  const {request} = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.searchParams.has("nocache")) return;
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(navigation(event));
  } else if (url.pathname.startsWith("/static/") || SHELL_PRELOAD.includes(url.pathname) && url.pathname !== "/") {
    event.respondWith(asset(event));
  }
});

self.addEventListener("message", event => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "PURGE_API_CACHE") event.waitUntil(purgePrivateCaches());
});

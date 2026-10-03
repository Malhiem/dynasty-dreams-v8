"""Iter 231av — Minimal offline-first service worker.

User asked: "A minimal Workbox service worker (cache-first for the app
shell, stale-while-revalidate for /api/matchups + /api/leagues/*/
standings, network-only for writes) would let users open
DynastyDreams on the subway and see their last roster + scores
instantly — then PTR forces a fresh pull when they're back on signal."

Rather than ship the Workbox runtime (~30 KB gzipped) we hand-rolled
the equivalent strategies on the plain SW API. The behaviour is
identical and the bytes are smaller.

Artefacts:
  • `public/service-worker.js` — the SW itself. Versioned cache
    names, install/activate lifecycle, fetch handler that fans out
    to cache-first vs SWR vs network-only depending on the URL.
  • `src/lib/registerServiceWorker.js` — production-only registration
    helper. Skips dev to keep CRA hot-reload happy. Posts
    `SKIP_WAITING` on update so a new build activates on next nav.
  • `src/index.js` — calls `registerServiceWorker()` after first
    render.
"""
from tests.source_tree import read_source
from pathlib import Path
import json


SW = Path("/app/frontend/public/service-worker.js")
REGISTER = Path("/app/frontend/src/lib/registerServiceWorker.js")
INDEX_JS = Path("/app/frontend/src/index.js")


def test_service_worker_versions_its_caches():
    src = read_source(SW)
    # Single source of truth for the version number — referenced by
    # both cache names AND the activate-time pruning step so a new
    # build never accidentally serves yesterday's assets.
    assert 'const SW_VERSION = "v1";' in src
    assert "const SHELL_CACHE = `dd-shell-${SW_VERSION}`;" in src
    assert "const API_CACHE = `dd-api-${SW_VERSION}`;" in src
    # Activate prunes any cache that doesn't match the current
    # version suffix.
    assert "!k.endsWith(`-${SW_VERSION}`)" in src
    assert "caches.delete(k)" in src


def test_service_worker_writes_are_network_only():
    src = read_source(SW)
    # Bail out for every non-GET so trade proposals + roster moves
    # always hit the live backend.
    assert 'if (request.method !== "GET") return;' in src


def test_service_worker_auth_admin_websocket_are_never_cached():
    src = read_source(SW)
    # Auth + admin endpoints must never be cached (security + RBAC).
    # Socket.IO upgrades also need to bypass the SW. Patterns are
    # regex literals in the source so the slashes are escaped.
    for forbidden in (
        r"/^\/api\/auth\//",
        r"/^\/api\/admin\//",
        r"/^\/api\/client-errors/",
        r"/^\/api\/socket\.io/",
    ):
        assert forbidden in src


def test_service_worker_swr_covers_matchups_and_standings():
    src = read_source(SW)
    # The two endpoints the user called out explicitly + the three
    # next-most-pulled (teams, players, week-at-a-glance) all go
    # through stale-while-revalidate. Patterns are regex literals.
    for pattern in (
        r"/^\/api\/matchups\//",
        r"/^\/api\/leagues\/[^/]+\/standings/",
        r"/^\/api\/leagues\/[^/]+\/teams/",
        r"/^\/api\/teams\/[^/]+$/",
        r"/^\/api\/players(\?|$)/",
    ):
        assert pattern in src
    # Personalized user data must bypass cache, including week-at-a-glance.
    assert r"/^\/api\/users\/me(\/|$|\?)/" in src
    assert "week-at-a-glance" not in src.split("const SWR")[1].split("];", 1)[0]
    # The strategy itself must return the cached copy immediately and
    # fire the network refresh in the background.
    assert "return cached || network" in src


def test_service_worker_app_shell_is_cache_first_with_offline_fallback():
    src = read_source(SW)
    assert "async function cacheFirst" in src
    # When the network is unreachable we serve the cached `/` so the
    # SPA renders its offline-aware shell instead of the browser's
    # network-error page.
    assert 'await cache.match("/")' in src
    # Background refresh on cache hit so the next nav gets fresh
    # bytes without the user waiting.
    assert "fetch(request)" in src
    assert "cache.put(request, res.clone())" in src


def test_service_worker_honours_nocache_opt_out():
    """The pull-to-refresh hook (iter 231at/au) — or any caller that
    needs guaranteed-fresh data — can append `?nocache=1` to bypass
    the SW entirely. The SW must NOT intercept those requests."""
    src = read_source(SW)
    assert 'url.searchParams.has("nocache")' in src


def test_register_helper_skips_development():
    src = read_source(REGISTER)
    # No SW in dev — HMR/hot-reload would fight a stale cache.
    assert 'env.NODE_ENV === "development"' in src
    # Registers under the root scope so /api/ + /static/ + / all
    # resolve through the SW.
    assert 'register(SW_URL, { scope: "/" })' in src
    # Update flow: post SKIP_WAITING when a new SW finishes installing
    # so the next navigation runs the new build.
    assert '{ type: "SKIP_WAITING" }' in src
    # Fails gracefully — registration in sandboxed iframes / Safari
    # Private mode rejects, and we don't want the app to crash there.
    assert ".catch(() => {" in src


def test_index_js_calls_register_after_render():
    src = read_source(INDEX_JS)
    assert 'import registerServiceWorker from "@/lib/registerServiceWorker";' in src
    # The call must come AFTER `root.render` so the SW install +
    # cache warm-up doesn't fight the initial paint.
    render_idx = src.find("root.render(")
    register_idx = src.find("registerServiceWorker()")
    assert render_idx >= 0 and register_idx >= 0
    assert register_idx > render_idx


def test_manifest_still_serves_under_sw_scope():
    """Manifest.json must remain reachable so the OS install banner
    keeps working after the SW is live."""
    data = json.loads(read_source(Path("/app/frontend/public/manifest.json")))
    assert data["scope"] == "/"
    assert data["start_url"] == "/"

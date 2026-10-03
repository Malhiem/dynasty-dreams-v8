/**
 * Iter 231av — Service worker registration.
 *
 * Registered exactly once after the first render so the SW install +
 * cache warm-up doesn't fight the initial paint. Skips registration
 * entirely in development (`process.env.NODE_ENV === 'development'`)
 * so hot-reload + HMR keep working without a stale SW intercepting
 * `/static/js/bundle.js`.
 *
 * Updates: the browser already serves the latest SW after a navigation
 * if the bytes changed. When a new SW is `waiting` we post a
 * `SKIP_WAITING` message so it activates immediately — this means the
 * very next reload runs the new build without an extra cycle.
 */

const SW_URL = "/service-worker.js";

export function registerServiceWorker() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;
  // CRA dev-server hot-reload + service workers don't mix. Only
  // register in production builds.
  const env = (typeof process !== "undefined" && process.env) || {};
  if (env.NODE_ENV === "development") return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register(SW_URL, { scope: "/" })
      .then((reg) => {
        // If a new SW is already waiting (page was refreshed but the
        // user hasn't navigated yet), activate it now.
        if (reg.waiting) {
          reg.waiting.postMessage({ type: "SKIP_WAITING" });
        }
        // Watch for future updates over the lifetime of this tab.
        reg.addEventListener("updatefound", () => {
          const nw = reg.installing;
          if (!nw) return;
          nw.addEventListener("statechange", () => {
            if (nw.state === "installed" && navigator.serviceWorker.controller) {
              // A new SW has installed and an old one is in control —
              // tell it to take over so the new build is live on the
              // next navigation.
              nw.postMessage({ type: "SKIP_WAITING" });
            }
          });
        });
      })
      .catch(() => {
        // Registration failed (private mode, sandboxed iframe, etc.) —
        // app still works online, just no offline cache.
      });
  });
}

export default registerServiceWorker;

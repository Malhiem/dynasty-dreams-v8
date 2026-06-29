/**
 * Iter 231aq — `<GlobalErrorBoundary />`
 *
 * Sits directly above `<BrowserRouter>` so any uncaught render-path
 * exception (or unhandled promise rejection / `window.onerror`)
 * lands here instead of the React dev overlay. The fallback UI tells
 * the user the app went sideways and offers a one-tap refresh.
 *
 * Side-effect: every captured error is POSTed to
 * `POST /api/client-errors` so we hear about crashes before users
 * tell us. The POST is fire-and-forget — never blocks the fallback
 * render, never throws on network failure.
 *
 * This is a class component because that's the only React surface
 * for `componentDidCatch` / `getDerivedStateFromError`. We layer the
 * global `window.onerror` + `unhandledrejection` listeners on top so
 * non-React crashes (e.g. inside setTimeout callbacks) are also
 * captured.
 */
import React from "react";

// `process` isn't typed in `.tsx` (no `@types/node` in CRA TS configs).
// Accessing via `globalThis` lets us read CRA-injected env vars
// (`REACT_APP_*`) without adding the node types dep.
const _ENV: any = (globalThis as any).process?.env || {};

const CLIENT_ERR_ENDPOINT =
  (_ENV.REACT_APP_BACKEND_URL || "") + "/api/client-errors";

// Lightweight breadcrumb ring — captures the last 20 user clicks +
// navigations so the report has context beyond the bare stack. Kept
// outside the component so it survives a re-mount.
const breadcrumbs: Array<{ ts: string; kind: string; detail: string }> = [];
const BREADCRUMB_LIMIT = 20;

function pushBreadcrumb(kind: string, detail: string) {
  breadcrumbs.push({ ts: new Date().toISOString(), kind, detail: detail.slice(0, 240) });
  if (breadcrumbs.length > BREADCRUMB_LIMIT) breadcrumbs.shift();
}

if (typeof window !== "undefined") {
  // Wire breadcrumbs once. Subsequent imports of this module are
  // memoised so we never double-bind.
  if (!(window as any).__ddBreadcrumbsBound) {
    (window as any).__ddBreadcrumbsBound = true;
    try {
      window.addEventListener(
        "click",
        (ev) => {
          const target = ev.target as HTMLElement | null;
          if (!target) return;
          const id = target.getAttribute("data-testid") || target.tagName.toLowerCase();
          pushBreadcrumb("click", id);
        },
        { capture: true, passive: true },
      );
      // History pushState — many SPAs override this; we wrap it.
      const origPush = history.pushState;
      history.pushState = function (this: History, ...args: any[]) {
        try {
          pushBreadcrumb("nav", String(args[2] || location.pathname));
        } catch { /* noop */ }
        return origPush.apply(this, args as any);
      } as typeof history.pushState;
      window.addEventListener("popstate", () => pushBreadcrumb("nav", location.pathname));
    } catch {
      /* swallow — breadcrumbs are an enhancement, never a requirement */
    }
  }
}

async function postError(payload: Record<string, unknown>) {
  try {
    // `keepalive: true` lets the request complete even if the page
    // unloads during the crash (e.g. a refresh-on-error reload).
    await fetch(CLIENT_ERR_ENDPOINT, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    });
  } catch {
    /* ignore — best-effort telemetry */
  }
}

function snapshotEnvelope(extra: Record<string, unknown>): Record<string, unknown> {
  let url = "";
  let userAgent = "";
  try { url = window.location.href; } catch { /* noop */ }
  try { userAgent = navigator.userAgent; } catch { /* noop */ }
  return {
    url,
    user_agent: userAgent,
    app_version: _ENV.REACT_APP_BUILD_SHA || "dev",
    breadcrumbs: breadcrumbs.slice(),
    ...extra,
  };
}

// Wire the global listeners exactly once — outside the class so they
// fire even if the boundary itself hasn't mounted yet (e.g. the crash
// happened in an event handler before first render).
if (typeof window !== "undefined" && !(window as any).__ddGlobalErrBound) {
  (window as any).__ddGlobalErrBound = true;
  try {
    window.addEventListener("error", (ev) => {
      try {
        postError(
          snapshotEnvelope({
            message: ev.message || String(ev.error) || "window.onerror",
            stack: (ev.error && (ev.error as Error).stack) || undefined,
          }),
        );
      } catch {
        /* ignore */
      }
    });
    window.addEventListener("unhandledrejection", (ev) => {
      try {
        const reason: any = ev.reason;
        postError(
          snapshotEnvelope({
            message: (reason && (reason.message || String(reason))) || "unhandledrejection",
            stack: (reason && reason.stack) || undefined,
          }),
        );
      } catch {
        /* ignore */
      }
    });
  } catch {
    /* ignore */
  }
}

interface BoundaryState {
  hasError: boolean;
  message?: string;
}

export default class GlobalErrorBoundary extends React.Component<
  { children: React.ReactNode },
  BoundaryState
> {
  state: BoundaryState = { hasError: false };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { hasError: true, message: error?.message || "Something went sideways" };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Fire-and-forget — never await, never block the fallback.
    postError(
      snapshotEnvelope({
        message: error?.message || "componentDidCatch",
        stack: error?.stack,
        component_stack: info?.componentStack,
      }),
    );
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div
        className="min-h-screen flex items-center justify-center px-4 bg-[#0B0B0F] text-white"
        data-testid="global-error-boundary"
      >
        <div className="max-w-md w-full rounded-2xl border border-white/10 bg-[#141414] p-6 text-center shadow-xl">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#00D2FF]/10 text-[#00D2FF] text-2xl">
            ⚠
          </div>
          <h1 className="text-xl font-semibold mb-2">Something went sideways</h1>
          <p className="text-sm text-[#A1A1AA] mb-6 leading-relaxed">
            We hit an unexpected snag rendering this page. We&apos;ve logged the
            details so the team can dig in. Give it another try?
          </p>
          {this.state.message && (
            <pre
              className="text-[10px] text-[#71717A] bg-black/40 border border-white/5 rounded p-2 overflow-auto text-left mb-6"
              data-testid="global-error-boundary-message"
            >
              {this.state.message.slice(0, 280)}
            </pre>
          )}
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="w-full rounded-md bg-[#00D2FF] hover:bg-[#00D2FF]/90 text-[#0B0B0F] font-semibold py-2.5 transition-colors"
            data-testid="global-error-boundary-reload"
          >
            Refresh to retry
          </button>
          <button
            type="button"
            onClick={() => {
              try { window.location.href = "/dashboard"; } catch { /* noop */ }
            }}
            className="mt-2 w-full text-xs text-[#A1A1AA] hover:text-white py-1.5"
            data-testid="global-error-boundary-home"
          >
            Or go back to the dashboard
          </button>
        </div>
      </div>
    );
  }
}

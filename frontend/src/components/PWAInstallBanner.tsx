/**
 * Iter 231an — `<PWAInstallBanner />`
 *
 * A dismissible mobile-only banner that prompts the user to install
 * DynastyDreams to their home screen. Two flavours:
 *
 *   • Android / Chromium browsers fire the `beforeinstallprompt` event
 *     ahead of the install heuristic. We capture it and surface a tappable
 *     "Install app" CTA that calls `event.prompt()` on click — that
 *     produces the OS-native install dialog.
 *
 *   • iOS Safari has no such event. We detect Mobile Safari + non-
 *     standalone mode and render a manual hint: "Tap Share → Add to
 *     Home Screen" with the same dismiss + remember semantics.
 *
 * Dismissal is persisted to `localStorage.PWA_BANNER_DISMISSED_AT` with
 * a 30-day cool-down so we don't nag users who've already declined.
 * The banner never appears on desktop (≥768px) — desktop install is
 * handled by the browser's native omnibox affordance.
 *
 * Iter 231ap — Hardened against the "Script error." overlay reported by
 * the first user who tapped Install. Every storage / matchMedia /
 * prompt call is wrapped in try/catch so a Safari Private-mode
 * SecurityError or a stale BeforeInstallPromptEvent never escapes to
 * the global `window.onerror` handler (which surfaces as the dreaded
 * cross-origin "Script error." with no stack trace). The install
 * button is also disabled while pending to defeat the double-tap race
 * that throws `InvalidStateError` from `prompt()`.
 */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, Share, X } from "lucide-react";

const DISMISS_KEY = "PWA_BANNER_DISMISSED_AT";
const COOLDOWN_MS = 30 * 24 * 60 * 60 * 1000;

type BIPEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

// ── Defensive helpers ───────────────────────────────────────────────────
// Every browser-surface call below is wrapped because mobile Safari in
// Private mode + WebViews + cross-origin iframes will throw on the
// "obvious" APIs (localStorage, matchMedia, navigator). The component
// must never throw from those — it would take down the whole app.

function safeMatchMedia(query: string): boolean {
  try {
    return !!(typeof window !== "undefined" && window.matchMedia?.(query).matches);
  } catch {
    return false;
  }
}

function safeLocalStorageGet(key: string): string | null {
  try {
    return typeof window !== "undefined" ? window.localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function safeLocalStorageSet(key: string, value: string): void {
  try {
    if (typeof window !== "undefined") window.localStorage.setItem(key, value);
  } catch {
    /* ignore — quota exceeded, Safari Private, sandboxed iframe */
  }
}

function isIos(): boolean {
  try {
    return (
      typeof navigator !== "undefined" &&
      /iPad|iPhone|iPod/.test(navigator.userAgent) &&
      !(window as any).MSStream
    );
  } catch {
    return false;
  }
}

function isStandalone(): boolean {
  if (safeMatchMedia("(display-mode: standalone)")) return true;
  try {
    return (window.navigator as any).standalone === true;
  } catch {
    return false;
  }
}

function isMobileViewport(): boolean {
  return safeMatchMedia("(max-width: 767px)");
}

function wasRecentlyDismissed(): boolean {
  const raw = safeLocalStorageGet(DISMISS_KEY);
  if (!raw) return false;
  const ts = Number(raw);
  if (!Number.isFinite(ts)) return false;
  return Date.now() - ts < COOLDOWN_MS;
}

export default function PWAInstallBanner() {
  const [promptEvent, setPromptEvent] = useState<BIPEvent | null>(null);
  const [visible, setVisible] = useState(false);
  const [installing, setInstalling] = useState(false);
  // "android" = native prompt available; "ios" = manual hint.
  const [mode, setMode] = useState<"android" | "ios">("android");

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (isStandalone() || wasRecentlyDismissed() || !isMobileViewport()) return;
    } catch {
      return;
    }

    const onBIP = (e: Event) => {
      try {
        e.preventDefault();
        setPromptEvent(e as BIPEvent);
        setMode("android");
        setVisible(true);
      } catch {
        /* ignore */
      }
    };
    try {
      window.addEventListener("beforeinstallprompt", onBIP);
    } catch {
      /* ignore — addEventListener should never throw, but defensive */
    }

    // iOS fallback — no event, so check the UA once on mount.
    try {
      if (isIos() && !isStandalone()) {
        setMode("ios");
        setVisible(true);
      }
    } catch {
      /* ignore */
    }

    return () => {
      try {
        window.removeEventListener("beforeinstallprompt", onBIP);
      } catch {
        /* ignore */
      }
    };
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    safeLocalStorageSet(DISMISS_KEY, String(Date.now()));
    setVisible(false);
  };

  const install = async () => {
    // Defeat double-tap race: prompt() throws InvalidStateError on the
    // second call. Disabling the button while we await `userChoice`
    // is the deterministic guard.
    if (!promptEvent || installing) return;
    setInstalling(true);
    try {
      await promptEvent.prompt();
      const result = await promptEvent.userChoice;
      if (result.outcome === "dismissed") {
        safeLocalStorageSet(DISMISS_KEY, String(Date.now()));
      }
    } catch {
      // Swallow — every failure path here is recoverable: the user
      // can re-open the banner via the next page load (Chrome
      // re-fires `beforeinstallprompt` ~24h later) and we don't want
      // the dev overlay's cross-origin "Script error." surfacing for
      // what is effectively a no-op for the user.
      safeLocalStorageSet(DISMISS_KEY, String(Date.now()));
    } finally {
      setPromptEvent(null);
      setVisible(false);
      setInstalling(false);
    }
  };

  return (
    <div
      className="fixed left-3 right-3 bottom-3 z-[1000] md:hidden rounded-xl border border-[#00D2FF]/30 bg-[#0F0F14]/95 backdrop-blur-md p-3 shadow-lg shadow-[#00D2FF]/10"
      role="dialog"
      aria-label="Install DynastyDreams"
      data-testid="pwa-install-banner"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#00D2FF]/15 text-[#00D2FF]">
          {mode === "ios" ? <Share className="h-5 w-5" /> : <Download className="h-5 w-5" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white leading-tight">
            Install DynastyDreams
          </p>
          {mode === "ios" ? (
            <p className="text-xs text-[#A1A1AA] mt-0.5 leading-snug">
              Tap <Share className="inline h-3 w-3 align-text-bottom mx-0.5" /> Share →
              <span className="font-medium text-white"> Add to Home Screen</span> for a full-screen app.
            </p>
          ) : (
            <p className="text-xs text-[#A1A1AA] mt-0.5 leading-snug">
              Get the full-screen app on your home screen — no browser chrome.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss install banner"
          className="shrink-0 -mr-1 -mt-1 p-1 text-[#A1A1AA] hover:text-white"
          data-testid="pwa-install-banner-dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {mode === "android" && (
        <Button
          onClick={install}
          disabled={installing}
          className="mt-3 w-full bg-[#00D2FF] hover:bg-[#00D2FF]/90 text-[#0B0B0F] font-semibold disabled:opacity-60"
          data-testid="pwa-install-banner-install"
        >
          <Download className="h-4 w-4 mr-2" />
          {installing ? "Opening…" : "Install app"}
        </Button>
      )}
    </div>
  );
}

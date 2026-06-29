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

function isIos() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
}

function isStandalone() {
  // `display-mode: standalone` is what the manifest asks for.
  // Safari additionally exposes `navigator.standalone`.
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (window.navigator as any).standalone === true
  );
}

function isMobileViewport() {
  return window.matchMedia?.("(max-width: 767px)").matches;
}

function wasRecentlyDismissed() {
  const raw = localStorage.getItem(DISMISS_KEY);
  if (!raw) return false;
  const ts = Number(raw);
  if (!Number.isFinite(ts)) return false;
  return Date.now() - ts < COOLDOWN_MS;
}

export default function PWAInstallBanner() {
  const [promptEvent, setPromptEvent] = useState<BIPEvent | null>(null);
  const [visible, setVisible] = useState(false);
  // "android" = native prompt available; "ios" = manual hint.
  const [mode, setMode] = useState<"android" | "ios">("android");

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (isStandalone() || wasRecentlyDismissed() || !isMobileViewport()) return;

    const onBIP = (e: Event) => {
      e.preventDefault();
      setPromptEvent(e as BIPEvent);
      setMode("android");
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onBIP);

    // iOS fallback — no event, so check the UA once on mount.
    if (isIos() && !isStandalone()) {
      setMode("ios");
      setVisible(true);
    }

    return () => window.removeEventListener("beforeinstallprompt", onBIP);
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setVisible(false);
  };

  const install = async () => {
    if (!promptEvent) return;
    try {
      await promptEvent.prompt();
      const result = await promptEvent.userChoice;
      // Whichever way the user answers, hide the banner — `accepted`
      // removes the need; `dismissed` deserves the cool-down too.
      if (result.outcome === "dismissed") {
        localStorage.setItem(DISMISS_KEY, String(Date.now()));
      }
    } finally {
      setPromptEvent(null);
      setVisible(false);
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
          className="mt-3 w-full bg-[#00D2FF] hover:bg-[#00D2FF]/90 text-[#0B0B0F] font-semibold"
          data-testid="pwa-install-banner-install"
        >
          <Download className="h-4 w-4 mr-2" /> Install app
        </Button>
      )}
    </div>
  );
}

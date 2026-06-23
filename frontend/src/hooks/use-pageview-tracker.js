/**
 * Iter 218 — UX Analytics pageview tracker.
 *
 * Hook that fires a `POST /api/analytics-ux/pageview` whenever the
 * route changes. Lightweight, fire-and-forget. Session id is stored
 * in sessionStorage so a single visit groups multiple pageviews.
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import api from "@/lib/api";

function getOrCreateSessionId() {
  try {
    let sid = window.sessionStorage.getItem("ux_session_id");
    if (!sid) {
      sid = (crypto?.randomUUID?.() || Math.random().toString(36).slice(2)) + "-" + Date.now();
      window.sessionStorage.setItem("ux_session_id", sid);
    }
    return sid;
  } catch {
    return "anon-" + Date.now();
  }
}

function getDevice() {
  if (typeof navigator === "undefined") return "unknown";
  const ua = navigator.userAgent || "";
  if (/Mobi|Android/i.test(ua)) return "mobile";
  if (/Tablet|iPad/i.test(ua)) return "tablet";
  return "desktop";
}

export function usePageviewTracker() {
  const location = useLocation();
  const lastRef = useRef("");
  useEffect(() => {
    const path = location.pathname;
    if (lastRef.current === path) return;
    const ref_path = lastRef.current;
    lastRef.current = path;
    // Fire-and-forget; never block UX on this
    api.post("/analytics-ux/pageview", {
      path,
      ref_path,
      session_id: getOrCreateSessionId(),
      device: getDevice(),
      viewport: {
        w: typeof window !== "undefined" ? window.innerWidth : null,
        h: typeof window !== "undefined" ? window.innerHeight : null,
      },
    }).catch(() => {});
  }, [location.pathname]);
}

/** Convenience helper for feature-adoption events. */
export function trackEvent(eventName, props = {}) {
  api.post("/analytics-ux/event", { event_name: eventName, props }).catch(() => {});
}

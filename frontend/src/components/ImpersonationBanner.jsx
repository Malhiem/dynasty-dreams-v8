/**
 * Iter 216b — Impersonation banner.
 *
 * Renders a persistent red sticky banner across the top of the app
 * whenever the current auth cookie is a `type=impersonation` JWT
 * (i.e., `useAuth().user._impersonation_mode === 'read_only'`).
 *
 * Shows:
 *   "You are viewing as {target_email} — read-only · expires in MM:SS"
 *
 * With an "Exit view-as" button that calls
 * `POST /api/auth/impersonate-stop` to restore the admin's original
 * session.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import { Eye, LogOut, FlaskConical } from "lucide-react";

export default function ImpersonationBanner() {
  const { user, refreshUser } = useAuth();
  const [now, setNow] = useState(Date.now());
  const [exiting, setExiting] = useState(false);

  const mode = user?._impersonation_mode;
  const inImpersonation = Boolean(mode);
  const isSandbox = mode === "sandbox";
  const expiresAt = user && user._impersonation_expires_at
    ? new Date(user._impersonation_expires_at).getTime() : null;

  // Tick every second to drive the countdown (skip in sandbox — no timer).
  useEffect(() => {
    if (!inImpersonation || isSandbox) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [inImpersonation, isSandbox]);

  // Auto-refresh user when impersonation token expires so the banner
  // disappears once the JWT exp passes and the cookie becomes invalid.
  // Skipped in sandbox mode (12-hour expiry is effectively no-timer;
  // driving refreshUser on every tick is unnecessary).
  useEffect(() => {
    if (!inImpersonation || isSandbox || !expiresAt) return;
    if (expiresAt < now) {
      refreshUser?.();
    }
  }, [now, expiresAt, inImpersonation, isSandbox, refreshUser]);

  if (!inImpersonation) return null;

  const remaining = expiresAt ? Math.max(0, expiresAt - now) : 0;
  const mins = Math.floor(remaining / 60000);
  const secs = Math.floor((remaining % 60000) / 1000);
  const fmt = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;

  const exit = async () => {
    setExiting(true);
    try {
      await api.post("/auth/impersonate-stop");
      await refreshUser?.();
      toast.success("Exited impersonation");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to exit impersonation");
    } finally {
      setExiting(false);
    }
  };

  // Iter 232N.61 — Sandbox mode uses a distinct visual language
  // (fuchsia, flask icon, no countdown, "sandbox — writes allowed")
  // so admins immediately recognise they're in a debug session on a
  // test account and NOT a read-only view of a real user.
  const barClasses = isSandbox
    ? "sticky top-0 z-50 w-full bg-fuchsia-700 text-white shadow-lg border-b border-fuchsia-900"
    : "sticky top-0 z-50 w-full bg-rose-600 text-white shadow-lg border-b border-rose-800";
  const exitBtnClasses = isSandbox
    ? "flex items-center gap-1.5 bg-fuchsia-900 hover:bg-fuchsia-950 px-3 py-1 rounded text-xs font-semibold disabled:opacity-60"
    : "flex items-center gap-1.5 bg-rose-800 hover:bg-rose-900 px-3 py-1 rounded text-xs font-semibold disabled:opacity-60";

  return (
    <div
      className={barClasses}
      data-testid="impersonation-banner"
      data-mode={mode}
      role="alert"
    >
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between gap-4 text-sm">
        <div className="flex items-center gap-2 min-w-0">
          {isSandbox ? (
            <FlaskConical className="h-4 w-4 shrink-0" />
          ) : (
            <Eye className="h-4 w-4 shrink-0" />
          )}
          <span className="truncate">
            {isSandbox ? "Sandbox — acting as" : "You are viewing as"}{" "}
            <strong data-testid="impersonation-target">{user.email}</strong>
            {isSandbox ? (
              <span className="opacity-90"> · writes enabled · no expiry</span>
            ) : (
              <>
                {" "}— <span className="opacity-90">read-only · expires in</span>{" "}
                <span
                  className="font-mono tabular-nums"
                  data-testid="impersonation-countdown"
                >
                  {fmt}
                </span>
              </>
            )}
          </span>
          {user._impersonator_email && (
            <span className="text-xs opacity-80 truncate hidden sm:inline">
              · impersonator: {user._impersonator_email}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={exit}
          disabled={exiting}
          className={exitBtnClasses}
          data-testid="impersonation-exit-btn"
        >
          <LogOut className="h-3.5 w-3.5" />
          {exiting ? "Exiting…" : isSandbox ? "Return to admin" : "Exit view-as"}
        </button>
      </div>
    </div>
  );
}

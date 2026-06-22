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
import { Eye, LogOut } from "lucide-react";

export default function ImpersonationBanner() {
  const { user, refreshUser } = useAuth();
  const [now, setNow] = useState(Date.now());
  const [exiting, setExiting] = useState(false);

  const inImpersonation = user && user._impersonation_mode === "read_only";
  const expiresAt = user && user._impersonation_expires_at
    ? new Date(user._impersonation_expires_at).getTime() : null;

  // Tick every second to drive the countdown
  useEffect(() => {
    if (!inImpersonation) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [inImpersonation]);

  // Auto-refresh user when impersonation token expires so the banner
  // disappears once the JWT exp passes and the cookie becomes invalid.
  useEffect(() => {
    if (!inImpersonation || !expiresAt) return;
    if (expiresAt < now) {
      refreshUser?.();
    }
  }, [now, expiresAt, inImpersonation, refreshUser]);

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

  return (
    <div
      className="sticky top-0 z-50 w-full bg-rose-600 text-white shadow-lg border-b border-rose-800"
      data-testid="impersonation-banner"
      role="alert"
    >
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between gap-4 text-sm">
        <div className="flex items-center gap-2 min-w-0">
          <Eye className="h-4 w-4 shrink-0" />
          <span className="truncate">
            You are viewing as <strong data-testid="impersonation-target">{user.email}</strong> —{" "}
            <span className="opacity-90">read-only · expires in</span>{" "}
            <span className="font-mono tabular-nums" data-testid="impersonation-countdown">{fmt}</span>
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
          className="flex items-center gap-1.5 bg-rose-800 hover:bg-rose-900 px-3 py-1 rounded text-xs font-semibold disabled:opacity-60"
          data-testid="impersonation-exit-btn"
        >
          <LogOut className="h-3.5 w-3.5" />
          {exiting ? "Exiting…" : "Exit view-as"}
        </button>
      </div>
    </div>
  );
}

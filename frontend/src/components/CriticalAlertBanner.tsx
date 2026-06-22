// @ts-nocheck
/**
 * Iter 210 — Critical Alert Banner for the Admin Dashboard.
 *
 * Subscribes to the `platform_admins` Socket.IO room and renders any
 * currently-active critical alerts at the top of the AdminDashboard.
 * Fetches initial state from `GET /admin/platform/alerts` on mount.
 */
import { useEffect, useState } from "react";
import { useSocket } from "@/hooks/use-socket";
import { useAuth } from "@/contexts/AuthContext";
import { AlertTriangle, Activity } from "lucide-react";
import api from "@/lib/api";

interface AlertItem {
  id: string;
  severity: "critical" | "warning";
  title: string;
  detail: string;
  since: string;
}

export default function CriticalAlertBanner() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  // Initial fetch
  useEffect(() => {
    if (user?.role !== "admin") return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/admin/platform/alerts");
        if (!cancelled) setAlerts(data?.alerts || []);
      } catch { /* noop */ }
    })();
    return () => { cancelled = true; };
  }, [user?.role]);

  // Subscribe to live updates
  useSocket(
    user?.role === "admin" ? "platform_admins" : null,
    {
      critical_alerts: (payload: any) => {
        setAlerts(payload?.alerts || []);
      },
    },
    user?.id,
  );

  if (user?.role !== "admin" || alerts.length === 0) return null;

  const critical = alerts.filter((a) => a.severity === "critical");
  const warning = alerts.filter((a) => a.severity === "warning");

  return (
    <div className="space-y-2" data-testid="critical-alerts">
      {critical.map((a) => (
        <div
          key={a.id}
          className="rounded-lg border border-rose-500/60 bg-rose-950/40 text-rose-100 p-3 flex items-start gap-3"
          data-testid={`alert-critical-${a.id}`}
        >
          <AlertTriangle className="h-5 w-5 text-rose-300 mt-0.5 shrink-0 animate-pulse" />
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-sm">{a.title}</div>
            <div className="text-xs text-rose-200/80 mt-0.5">{a.detail}</div>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-rose-300 shrink-0">
            critical
          </span>
        </div>
      ))}
      {warning.map((a) => (
        <div
          key={a.id}
          className="rounded-lg border border-amber-500/60 bg-amber-950/30 text-amber-100 p-3 flex items-start gap-3"
          data-testid={`alert-warning-${a.id}`}
        >
          <Activity className="h-5 w-5 text-amber-300 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-sm">{a.title}</div>
            <div className="text-xs text-amber-200/80 mt-0.5">{a.detail}</div>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-amber-300 shrink-0">
            warning
          </span>
        </div>
      ))}
    </div>
  );
}
